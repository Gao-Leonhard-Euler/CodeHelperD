#!/usr/bin/env python3
"""
tools/java_debugger.py
提供 Java 编译（javac）和调试（jdb）功能。支持编译 Java 源文件，启动 jdb 调试会话并交互，获取帮助和版本信息。
"""

import os
import sys
import time
import uuid
import queue
import shlex
import threading
import subprocess
import locale
from typing import Dict, Optional, Any, List

# 全局会话存储（用于调试会话）
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

tool_def = {
    "type": "function",
    "function": {
        "name": "java_debugger",
        "description": "Java 编译和调试工具。支持 javac 编译，jdb 调试会话管理，获取帮助和版本信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["compile", "debug", "send", "close", "list", "javac_help", "jdb_help", "version"],
                    "description": "操作类型：compile-编译Java源文件；debug-启动jdb调试会话；send-向会话发送命令；close-关闭会话；list-列出会话；javac_help-获取javac帮助；jdb_help-获取jdb帮助；version-获取java/javac/jdb版本信息。"
                },
                # compile 参数
                "source_files": {
                    "type": "string",
                    "description": "要编译的Java源文件路径，多个文件用空格分隔（compile操作必需）"
                },
                "classpath": {
                    "type": "string",
                    "description": "编译时的类路径（可选）"
                },
                "output_dir": {
                    "type": "string",
                    "description": "编译输出目录（可选，默认与源文件同目录或当前目录）"
                },
                "compile_options": {
                    "type": "string",
                    "description": "额外的javac编译选项，如 '-g -deprecation'"
                },
                # debug 参数
                "main_class": {
                    "type": "string",
                    "description": "要调试的主类（debug操作必需）"
                },
                "debug_classpath": {
                    "type": "string",
                    "description": "调试时的类路径（可选）"
                },
                "sourcepath": {
                    "type": "string",
                    "description": "调试时的源文件路径（可选）"
                },
                "program_args": {
                    "type": "string",
                    "description": "传递给主类的参数（可选）"
                },
                "jdb_options": {
                    "type": "string",
                    "description": "额外的jdb启动选项，如 '-dbgtrace'"
                },
                "timeout_per_step": {
                    "type": "number",
                    "description": "每次交互的超时时间（秒），默认5.0",
                    "default": 5.0
                },
                # send/close 参数
                "session_id": {
                    "type": "string",
                    "description": "会话ID（用于send和close操作）"
                },
                "command": {
                    "type": "string",
                    "description": "要发送给jdb的命令（用于send操作）"
                }
            },
            "required": ["action"]
        }
    }
}

def _decode_bytes(data: bytes) -> str:
    """尝试多种编码严格解码，成功则返回；全部失败则使用 UTF-8 并替换无法解析的字符"""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    encodings = ['gb2312', 'gbk', locale.getpreferredencoding()]
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')

def _run_command(cmd: List[str], timeout: float = 30.0, capture_output: bool = True, env: Optional[Dict] = None) -> str:
    """运行命令并返回输出"""
    try:
        if env is not None:
            full_env = os.environ.copy()
            full_env.update(env)
        else:
            full_env = None
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=False,
            errors='replace',
            timeout=timeout,
            check=False,
            env=full_env
        )
        output = _decode_bytes(result.stdout)
        if result.stderr:
            if output:
                output += "\n" + result.stderr
            else:
                output = result.stderr
        if result.returncode != 0:
            output = f"命令执行失败（返回码 {result.returncode}）：\n{output}"
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"命令执行超时（{timeout}秒）"
    except FileNotFoundError:
        return f"错误：找不到命令 {' '.join(cmd)}，请确保Java相关命令已在PATH中。"
    except Exception as e:
        return f"执行出错：{e}"

def _create_session_id() -> str:
    """生成唯一会话ID"""
    sess_id = uuid.uuid4()
    while str(sess_id) in _sessions:
        sess_id = uuid.uuid4()
    return str(sess_id)

def _reader_thread(process: subprocess.Popen, q: queue.Queue, stop_event: threading.Event):
    """读取进程的 stdout 和 stderr 并放入队列"""
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
    """终止进程并清理资源"""
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
    """收集队列中的输出，最多等待 timeout 秒"""
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
        text = _decode_bytes(data)
        lines.append(f"[{stream}] {text.rstrip()}")
    return "\n".join(lines)

def execute(action: str,
            source_files: Optional[str] = None,
            classpath: Optional[str] = None,
            output_dir: Optional[str] = None,
            compile_options: Optional[str] = "",
            main_class: Optional[str] = None,
            debug_classpath: Optional[str] = None,
            sourcepath: Optional[str] = None,
            program_args: Optional[str] = "",
            jdb_options: Optional[str] = "",
            timeout_per_step: float = 5.0,
            session_id: Optional[str] = None,
            command: Optional[str] = None) -> str:
    """
    执行 Java 编译或调试操作。
    """
    global _sessions

    # ---------- 编译操作 ----------
    if action == "compile":
        if not source_files:
            return "错误：compile 操作需要提供 source_files。"

        # 构建 javac 命令
        cmd = ["javac"]
        if classpath:
            cmd.extend(["-classpath", classpath])
        if output_dir:
            cmd.extend(["-d", output_dir])
        if compile_options:
            cmd.extend(shlex.split(compile_options))
        # 添加源文件
        cmd.extend(shlex.split(source_files))

        return _run_command(cmd, timeout=60)

    # ---------- 调试会话操作 ----------
    elif action == "debug":
        if not main_class:
            return "错误：debug 操作需要提供 main_class。"

        # 构建 jdb 命令
        cmd = ["jdb"]
        if debug_classpath:
            cmd.extend(["-classpath", debug_classpath])
        if sourcepath:
            cmd.extend(["-sourcepath", sourcepath])
        if jdb_options:
            cmd.extend(shlex.split(jdb_options))
        cmd.append(main_class)
        if program_args:
            cmd.extend(shlex.split(program_args))

        # 启动 jdb 进程
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
        except FileNotFoundError:
            return "错误：找不到 jdb 命令，请确保 JDK 已安装且 jdb 在 PATH 中。"
        except Exception as e:
            return f"启动 jdb 失败：{e}"

        sess_id = _create_session_id()
        q = queue.Queue()
        stop_event = threading.Event()
        session = {
            'process': process,
            'queue': q,
            'stop_event': stop_event,
            'timeout_per_step': timeout_per_step,
            'main_class': main_class
        }

        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 获取启动输出（如 jdb 提示符）
        initial = _collect_output(q, timeout=0.5)
        if initial:
            return f"调试会话 {sess_id} 已创建。初始输出：\n{initial}"
        else:
            return f"调试会话 {sess_id} 已创建。"

    elif action == "send":
        if not session_id:
            return "错误：send 操作需要提供 session_id。"
        with _lock:
            session = _sessions.get(session_id)
        if not session:
            return f"错误：会话 {session_id} 不存在。"
        if command is None:
            return "错误：send 操作需要提供 command。"

        process = session['process']
        q = session['queue']
        stop_event = session['stop_event']
        step_timeout = timeout_per_step

        if stop_event.is_set() or process.poll() is not None:
            return f"会话 {session_id} 已结束。"

        # 发送命令前收集已有输出
        existing = _collect_output(q, timeout=0)

        # 发送命令（需添加换行符）
        try:
            cmd_bytes = (command + '\n').encode('utf-8', errors='replace')
            process.stdin.write(cmd_bytes)
            process.stdin.flush()
        except Exception as e:
            return f"写入命令失败：{e}"

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

    elif action == "close":
        if not session_id:
            return "错误：close 操作需要提供 session_id。"
        with _lock:
            session = _sessions.pop(session_id, None)
        if not session:
            return f"会话 {session_id} 不存在。"

        _terminate_process(session)
        return f"调试会话 {session_id} 已关闭。"

    elif action == "list":
        with _lock:
            if not _sessions:
                return "当前无活跃调试会话。"
            lines = ["活跃调试会话："]
            for sid, sess in _sessions.items():
                proc = sess['process']
                status = "运行中" if proc.poll() is None else f"已退出 (代码 {proc.returncode})"
                lines.append(f"  {sid}: jdb {sess.get('main_class', '')} - {status}")
            return "\n".join(lines)

    # ---------- 帮助信息 ----------
    elif action == "javac_help":
        return _run_command(["javac", "-help"], timeout=10)

    elif action == "jdb_help":
        return _run_command(["jdb", "-help"], timeout=10)

    # ---------- 版本信息 ----------
    elif action == "version":
        java_ver = _run_command(["java", "-version"], timeout=10)
        javac_ver = _run_command(["javac", "-version"], timeout=10)
        jdb_ver = _run_command(["jdb", "-version"], timeout=10)
        return f"{java_ver}\n\n{javac_ver}\n\n{jdb_ver}"

    else:
        return f"错误：未知操作 {action}。"