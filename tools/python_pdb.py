#!/usr/bin/env python3
"""
tools/python_pdb.py
提供 Python 调试器 pdb 的会话管理：创建会话（指定脚本）、发送命令、关闭会话、列出会话以及获取帮助信息。
"""

import os
import sys
import time
import uuid
import queue
import shlex
import threading
import subprocess
from typing import Dict, Optional, Any

# 全局会话存储
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

tool_def = {
    "type": "function",
    "function": {
        "name": "python_pdb",
        "description": "使用 pdb 调试 Python 脚本。支持创建会话、发送命令、关闭会话、列出会话以及获取 pdb 帮助信息。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "send", "close", "list", "help"],
                    "description": "操作类型：create-创建新调试会话；send-向会话发送命令；close-关闭会话；list-列出所有会话；help-获取 pdb 帮助信息。"
                },
                "script_path": {
                    "type": "string",
                    "description": "要调试的 Python 脚本路径（create 必需）"
                },
                "script_args": {
                    "type": "string",
                    "description": "传递给脚本的命令行参数，默认为空（create 可选）"
                },
                "initial_commands": {
                    "type": "string",
                    "description": "启动 pdb 后自动执行的命令，可多行，每行一个命令（create 操作可选）"
                },
                "timeout_per_step": {
                    "type": "number",
                    "description": "每次命令执行的超时时间（秒），默认 5.0",
                    "default": 5.0
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID（用于 send 和 close 操作）"
                },
                "command": {
                    "type": "string",
                    "description": "要发送给 pdb 的命令（用于 send 操作）"
                }
            },
            "required": ["action"]
        }
    }
}

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
        try:
            text = data.decode('utf-8', errors='replace')
        except:
            text = str(data)
        lines.append(f"[{stream}] {text.rstrip()}")
    return "\n".join(lines)

def execute(action: str,
            script_path: Optional[str] = None,
            script_args: str = "",
            initial_commands: Optional[str] = None,
            timeout_per_step: float = 5.0,
            session_id: Optional[str] = None,
            command: Optional[str] = None) -> str:
    """
    执行 pdb 调试操作。
    """
    global _sessions

    # 创建新会话
    if action == "create":
        if not script_path:
            return "错误：create 操作需要提供 script_path。"

        if not os.path.isfile(script_path):
            return f"错误：脚本文件 {script_path} 不存在。"

        # 构建命令：python -m pdb 脚本 [参数]
        python_exe = sys.executable
        cmd = [python_exe, "-m", "pdb", script_path]
        if script_args:
            # 使用 shlex 分割参数
            try:
                args_list = shlex.split(script_args, posix=(sys.platform != "win32"))
            except Exception as e:
                return f"参数解析失败：{e}"
            cmd.extend(args_list)

        # 启动进程
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
            return "错误：找不到 python 解释器。"
        except Exception as e:
            return f"启动 pdb 失败：{e}"

        sess_id = _create_session_id()
        q = queue.Queue()
        stop_event = threading.Event()
        session = {
            'process': process,
            'queue': q,
            'stop_event': stop_event,
            'timeout_per_step': timeout_per_step,
            'script_path': script_path,
            'script_args': script_args
        }

        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 获取启动输出（如 pdb 提示符、脚本输出等）
        initial = _collect_output(q, timeout=0.5)
        # 如果提供了初始命令，则依次发送
        if initial_commands:
            # 将多行命令按行分割并发送
            for line in initial_commands.splitlines():
                line = line.strip()
                if not line:
                    continue
                # 发送命令（需要换行）
                try:
                    process.stdin.write((line + '\n').encode('utf-8', errors='replace'))
                    process.stdin.flush()
                except Exception as e:
                    return f"发送初始命令失败：{e}"
                # 短暂等待输出
                time.sleep(0.1)
            # 收集执行初始命令后的输出
            after_cmds = _collect_output(q, timeout=timeout_per_step)
            if after_cmds:
                if initial:
                    initial += "\n" + after_cmds
                else:
                    initial = after_cmds

        if initial:
            return f"调试会话 {sess_id} 已创建。初始输出：\n{initial}"
        else:
            return f"调试会话 {sess_id} 已创建。"

    # 发送命令
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

        # 发送命令前收集已有输出（如之前的提示符）
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

    # 关闭会话
    elif action == "close":
        if not session_id:
            return "错误：close 操作需要提供 session_id。"
        with _lock:
            session = _sessions.pop(session_id, None)
        if not session:
            return f"会话 {session_id} 不存在。"

        _terminate_process(session)
        return f"调试会话 {session_id} 已关闭。"

    # 列出会话
    elif action == "list":
        with _lock:
            if not _sessions:
                return "当前无活跃调试会话。"
            lines = ["活跃调试会话："]
            for sid, sess in _sessions.items():
                proc = sess['process']
                status = "运行中" if proc.poll() is None else f"已退出 (代码 {proc.returncode})"
                lines.append(f"  {sid}: python -m pdb {sess.get('script_path', '')} - {status}")
            return "\n".join(lines)

    # 获取帮助信息
    elif action == "help":
        python_exe = sys.executable
        cmd = [python_exe, "-m", "pdb", "-h"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            if result.returncode != 0:
                return f"获取帮助失败：\n{output}"
            return output.strip() or "无输出"
        except subprocess.TimeoutExpired:
            return "获取帮助超时。"
        except Exception as e:
            return f"执行出错：{e}"

    else:
        return f"错误：未知操作 {action}。"