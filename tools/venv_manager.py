#!/usr/bin/env python3
"""
tools/venv_manager.py
Python虚拟环境管理工具。支持创建、列出、删除虚拟环境，以及在虚拟环境中执行Python代码（交互式和一次性执行）。
"""

import os
import sys
import time
import uuid
import queue
import shlex
import signal
import threading
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Optional, Any, List

# 全局会话存储（用于交互式会话）
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

# 虚拟环境存储目录
VENVS_DIR = Path(__file__).parent.parent / "venvs"

tool_def = {
    "type": "function",
    "function": {
        "name": "venv_manager",
        "description": "管理Python虚拟环境，支持创建、列出、删除虚拟环境，以及在虚拟环境中执行Python代码。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "delete", "run", "interact", "send", "stop"],
                    "description": "操作类型：create-创建虚拟环境，list-列出所有虚拟环境，delete-删除虚拟环境，run-在虚拟环境中执行一次性代码，interact-启动虚拟环境交互式会话，send-向交互式会话发送输入，stop-停止交互式会话"
                },
                "env_name": {
                    "type": "string",
                    "description": "虚拟环境名称（用于create、delete、run、interact操作）"
                },
                "python_version": {
                    "type": "string",
                    "description": "Python版本（如'3.8'、'3.9'，用于create操作），默认为当前Python版本"
                },
                "requirements": {
                    "type": "string",
                    "description": "要安装的Python包列表（逗号分隔）或requirements.txt内容，用于create操作"
                },
                # run 操作参数
                "code": {
                    "type": "string",
                    "description": "要执行的Python代码（用于run操作）"
                },
                "timeout": {
                    "type": "number",
                    "description": "执行超时时间（秒），默认10.0",
                    "default": 10.0
                },
                # interact 操作参数
                "interactive_timeout": {
                    "type": "number",
                    "description": "交互式会话每次等待的超时（秒），默认4.0",
                    "default": 4.0
                },
                # send 操作参数
                "session_id": {
                    "type": "string",
                    "description": "会话ID（用于send、stop操作）"
                },
                "input_data": {
                    "type": "string",
                    "description": "发送给会话的输入（用于send操作）"
                }
            },
            "required": ["action"]
        }
    }
}

def _ensure_venvs_dir():
    """确保虚拟环境目录存在"""
    VENVS_DIR.mkdir(parents=True, exist_ok=True)

def _get_venv_path(env_name: str) -> Path:
    """获取虚拟环境路径"""
    return VENVS_DIR / env_name

def _get_python_executable(venv_path: Path) -> Path:
    """获取虚拟环境中的Python可执行文件路径"""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "python.exe"
    else:
        return venv_path / "bin" / "python"

def _get_pip_executable(venv_path: Path) -> Path:
    """获取虚拟环境中的pip可执行文件路径"""
    if sys.platform == "win32":
        return venv_path / "Scripts" / "pip.exe"
    else:
        return venv_path / "bin" / "pip"

def _venv_exists(env_name: str) -> bool:
    """检查虚拟环境是否存在"""
    venv_path = _get_venv_path(env_name)
    python_exe = _get_python_executable(venv_path)
    return venv_path.exists() and python_exe.exists()

def _create_session_id() -> str:
    """生成唯一会话ID"""
    sess_id = uuid.uuid4()
    while str(sess_id) in _sessions.keys():
        sess_id = uuid.uuid4()
    return str(sess_id)

def _reader_thread(process: subprocess.Popen, q: queue.Queue, stop_event: threading.Event):
    """读取进程的stdout和stderr并放入队列"""
    def _read_stream(stream, stream_name):
        try:
            for line in iter(stream.readline, b''):
                if stop_event.is_set():
                    break
                q.put((stream_name, line))
        except Exception:
            pass
        finally:
            try:
                stream.close()
            except:
                pass

    t_out = threading.Thread(target=_read_stream, args=(process.stdout, 'stdout'))
    t_err = threading.Thread(target=_read_stream, args=(process.stderr, 'stderr'))
    t_out.daemon = True
    t_err.daemon = True
    t_out.start()
    t_err.start()

    process.wait()
    stop_event.set()
    t_out.join()
    t_err.join()
    q.put(('EOF', None))

def _terminate_process(session: Dict[str, Any]):
    """终止进程并清理"""
    process = session['process']
    stop_event = session['stop_event']
    if not stop_event.is_set():
        stop_event.set()
    try:
        if sys.platform == "win32":
            process.terminate()
        else:
            process.terminate()
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception:
        pass

def _collect_output(q: queue.Queue, timeout: float) -> str:
    """收集队列中的输出"""
    items = []
    start = time.time()
    # 先非阻塞获取已有
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    # 再等待一段时间获取新输出
    remaining = timeout
    while remaining > 0:
        try:
            item = q.get(timeout=remaining)
            items.append(item)
            if item[0] == 'EOF':
                break
        except queue.Empty:
            break
        remaining = timeout - (time.time() - start)
    if not items:
        return ""
    lines = []
    for stream, data in items:
        if stream == 'EOF':
            lines.append("[进程已结束]")
            continue
        try:
            text = data.decode('utf-8', errors='replace')
        except:
            text = str(data)
        lines.append(f"[{stream}] {text}")
    return "\n".join(lines)

def _install_requirements(venv_path: Path, requirements: str) -> str:
    """在虚拟环境中安装包"""
    pip_exe = _get_pip_executable(venv_path)
    if not pip_exe.exists():
        return "警告：虚拟环境中未找到pip，无法安装包。"
    
    # 判断requirements是包列表还是requirements.txt内容
    # 如果是简单的包列表（如"requests,pandas,numpy"），直接安装
    # 否则当作requirements.txt内容写入临时文件
    if '\n' in requirements or '==' in requirements or '>=' in requirements or 'requirements' in requirements.lower():
        # 可能是requirements.txt内容
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(requirements)
            req_file = f.name
        
        try:
            cmd = [str(pip_exe), "install", "-r", req_file]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False
            )
            
            output = result.stdout
            if result.stderr:
                if output:
                    output += "\n" + result.stderr
                else:
                    output = result.stderr
            
            if result.returncode != 0:
                return f"安装包失败（返回码 {result.returncode}）：\n{output}"
            
            return f"包安装成功：\n{output}"
        finally:
            os.unlink(req_file)
    else:
        # 简单的包列表
        packages = [pkg.strip() for pkg in requirements.split(',') if pkg.strip()]
        if not packages:
            return "没有提供有效的包名称。"
        
        cmd = [str(pip_exe), "install"] + packages
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60.0,
                check=False
            )
            
            output = result.stdout
            if result.stderr:
                if output:
                    output += "\n" + result.stderr
                else:
                    output = result.stderr
            
            if result.returncode != 0:
                return f"安装包失败（返回码 {result.returncode}）：\n{output}"
            
            return f"包安装成功：\n{output}"
        except subprocess.TimeoutExpired:
            return f"安装包超时（60秒）。"

def execute(action: str,
            env_name: Optional[str] = None,
            python_version: Optional[str] = None,
            requirements: Optional[str] = None,
            code: Optional[str] = None,
            timeout: float = 10.0,
            interactive_timeout: float = 4.0,
            session_id: Optional[str] = None,
            input_data: Optional[str] = None) -> str:
    """
    执行虚拟环境管理操作。
    """
    global _sessions

    # 确保虚拟环境目录存在
    _ensure_venvs_dir()

    # 创建虚拟环境
    if action == "create":
        if not env_name:
            return "错误：create操作需要提供env_name。"
        
        if _venv_exists(env_name):
            return f"虚拟环境 '{env_name}' 已存在。"
        
        venv_path = _get_venv_path(env_name)
        
        # 首先尝试使用 venv 模块
        venv_success = False
        venv_output = ""
        
        try:
            cmd = [sys.executable, "-m", "venv", str(venv_path)]
            if python_version:
                # 注意：venv模块不支持直接指定Python版本
                venv_output += f"注意：venv模块不支持直接指定Python版本，将使用当前Python版本 {sys.version.split()[0]}。\n"
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False
            )
            
            if result.returncode == 0:
                venv_success = True
                venv_output += "使用venv模块创建虚拟环境成功。\n"
            else:
                venv_output += f"venv模块创建失败（返回码 {result.returncode}）：\n{result.stderr}\n"
        except Exception as e:
            venv_output += f"venv模块创建时发生错误：{str(e)}\n"
        
        # 如果venv失败，尝试使用virtualenv
        if not venv_success:
            venv_output += "正在尝试使用virtualenv...\n"
            try:
                # 检查是否安装了virtualenv
                result = subprocess.run(
                    [sys.executable, "-m", "virtualenv", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5.0,
                    check=False
                )
                
                if result.returncode == 0:
                    # 使用virtualenv
                    cmd = [sys.executable, "-m", "virtualenv", str(venv_path)]
                    if python_version:
                        cmd.extend(["-p", f"python{python_version}"])
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=30.0,
                        check=False
                    )
                    
                    if result.returncode == 0:
                        venv_success = True
                        venv_output += "使用virtualenv创建虚拟环境成功。\n"
                    else:
                        venv_output += f"virtualenv创建失败（返回码 {result.returncode}）：\n{result.stderr}\n"
                else:
                    venv_output += "virtualenv未安装。请安装python3-venv或virtualenv包。\n"
            except Exception as e:
                venv_output += f"virtualenv创建时发生错误：{str(e)}\n"
        
        if not venv_success:
            return f"创建虚拟环境失败：\n{venv_output}"
        
        # 检查是否创建成功
        python_exe = _get_python_executable(venv_path)
        if not python_exe.exists():
            return f"创建虚拟环境似乎成功，但找不到Python可执行文件：{python_exe}"
        
        final_output = f"虚拟环境 '{env_name}' 创建成功。路径：{venv_path}\n{venv_output}"
        
        # 安装requirements（如果提供）
        if requirements:
            install_result = _install_requirements(venv_path, requirements)
            final_output += f"\n{install_result}"
        
        return final_output

    # 列出虚拟环境
    elif action == "list":
        envs = []
        for item in VENVS_DIR.iterdir():
            if item.is_dir():
                python_exe = _get_python_executable(item)
                if python_exe.exists():
                    envs.append(item.name)
        
        if not envs:
            return "当前没有虚拟环境。"
        
        result = ["虚拟环境列表："]
        for env in sorted(envs):
            venv_path = _get_venv_path(env)
            python_exe = _get_python_executable(venv_path)
            # 获取Python版本
            try:
                result_ver = subprocess.run(
                    [str(python_exe), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=2.0,
                    check=False
                )
                version = result_ver.stdout.strip() if result_ver.returncode == 0 else "未知版本"
            except:
                version = "未知版本"
            
            result.append(f"  {env} - {version} - {venv_path}")
        
        return "\n".join(result)

    # 删除虚拟环境
    elif action == "delete":
        if not env_name:
            return "错误：delete操作需要提供env_name。"
        
        if not _venv_exists(env_name):
            return f"虚拟环境 '{env_name}' 不存在。"
        
        venv_path = _get_venv_path(env_name)
        try:
            shutil.rmtree(venv_path)
            return f"虚拟环境 '{env_name}' 已删除。"
        except Exception as e:
            return f"删除虚拟环境失败：{str(e)}"

    # 在虚拟环境中执行一次性代码
    elif action == "run":
        if not env_name:
            return "错误：run操作需要提供env_name。"
        
        if not _venv_exists(env_name):
            return f"虚拟环境 '{env_name}' 不存在，请先创建。"
        
        if not code:
            return "错误：run操作需要提供code。"
        
        venv_path = _get_venv_path(env_name)
        python_exe = _get_python_executable(venv_path)
        
        cmd = [str(python_exe), "-c", code]
        
        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                check=False
            )
            
            output = process.stdout
            if process.stderr:
                if output:
                    output += "\n" + process.stderr
                else:
                    output = process.stderr
            
            if process.returncode != 0:
                return f"执行失败（返回码 {process.returncode}）：\n{output}"
            
            if output:
                return f"执行成功：\n{output}"
            else:
                return "执行成功，无输出。"
                
        except subprocess.TimeoutExpired:
            return f"执行超时（{timeout}秒）。"
        except Exception as e:
            return f"执行时发生错误：{str(e)}"

    # 启动虚拟环境交互式会话
    elif action == "interact":
        if not env_name:
            return "错误：interact操作需要提供env_name。"
        
        if not _venv_exists(env_name):
            return f"虚拟环境 '{env_name}' 不存在，请先创建。"
        
        venv_path = _get_venv_path(env_name)
        python_exe = _get_python_executable(venv_path)
        
        cmd = [str(python_exe), "-i"]  # 交互模式
        
        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            return f"启动交互式解释器失败：{e}"

        sess_id = _create_session_id()
        q = queue.Queue()
        stop_event = threading.Event()
        session = {
            'process': process,
            'queue': q,
            'stop_event': stop_event,
            'timeout_per_step': interactive_timeout,
            'env_name': env_name,
            'python_exe': str(python_exe)
        }

        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 获取启动输出
        initial = _collect_output(q, timeout=0.5)
        if initial:
            return f"交互式会话 {sess_id} 已启动（虚拟环境：{env_name}），初始输出：\n{initial}"
        else:
            return f"交互式会话 {sess_id} 已启动（虚拟环境：{env_name}）。"

    # 向交互式会话发送输入
    elif action == "send":
        if not session_id:
            return "错误：send操作需要提供session_id。"
        with _lock:
            session = _sessions.get(session_id)
        if not session:
            return f"错误：会话 {session_id} 不存在。"

        process = session['process']
        q = session['queue']
        stop_event = session['stop_event']
        step_timeout = interactive_timeout

        if stop_event.is_set() or process.poll() is not None:
            return f"会话 {session_id} 已结束。"

        # 发送输入前，先收集已有输出
        existing = _collect_output(q, timeout=0)

        # 发送输入
        try:
            if input_data is not None:
                process.stdin.write(input_data.encode('utf-8', errors='replace'))
                process.stdin.flush()
        except Exception as e:
            return f"写入输入失败：{e}"

        # 收集新输出直到超时
        new_output = _collect_output(q, timeout=step_timeout)

        # 合并输出
        combined = existing
        if new_output:
            if combined:
                combined += "\n" + new_output
            else:
                combined = new_output

        if not combined:
            return "（无输出）"
        return combined

    # 停止交互式会话
    elif action == "stop":
        if not session_id:
            return "错误：stop操作需要提供session_id。"
        with _lock:
            session = _sessions.pop(session_id, None)
        if not session:
            return f"会话 {session_id} 不存在。"

        _terminate_process(session)
        return f"交互式会话 {session_id} 已停止。"

    else:
        return f"错误：未知操作 '{action}'。"