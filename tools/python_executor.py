#!/usr/bin/env python3
"""
tools/python_executor.py
在当前主环境中执行 Python 代码。支持一次性执行（run）和启动交互式解释器（interact），并提供会话管理。
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
from typing import Dict, Optional, Any

# 全局会话存储
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()

tool_def = {
    "type": "function",
    "function": {
        "name": "python_executor",
        "description": "在当前主环境中运行 Python 代码。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "interact", "send", "stop", "list", "version", "help"],
                    "description": "操作类型：run-运行一次代码；interact-启动交互式解释器；send-向会话发送输入；stop-停止会话；list-列出活跃会话；version-获取版本；help-获取帮助。"
                },
                "code": {
                    "type": "string",
                    "description": "要执行的 Python 代码（用于 run 操作）或 help 要求（用于 help 操作，若输入 '-env' 则执行 'python --help-env'，默认为空）"
                },
                "timeout": {
                    "type": "number",
                    "description": "一次性执行的超时时间（秒），默认 4.0"
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID（用于 send、stop 操作）"
                },
                "input_data": {
                    "type": "string",
                    "description": "发送给会话的输入（用于 send 操作）"
                },
                "interactive_timeout": {
                    "type": "number",
                    "description": "交互式会话每次等待超时（秒），默认 4.0"
                }
            },
            "required": ["action"]
        }
    }
}

def _create_session_id() -> str:
    """生成唯一会话ID"""
    sess_id=uuid.uuid4()
    while sess_id in _sessions.keys():
        sess_id=uuid.uuid4()
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

def execute(action: str,
            code: Optional[str] = None,
            timeout: float = 4.0,
            session_id: Optional[str] = None,
            input_data: Optional[str] = None,
            interactive_timeout: float = 4.0) -> str:
    """
    执行 Python 代码管理操作。
    """
    global _sessions

    # 一次性执行
    if action == "run":
        if not code:
            return "错误：run 操作需要提供 code。"

        # 使用当前 Python 解释器执行
        python_exe = sys.executable
        cmd = [python_exe, "-c", code]

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # 使用字节流，避免编码问题
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            return f"启动进程失败：{e}"

        # 等待完成或超时
        try:
            stdout, stderr = process.communicate(timeout=timeout)
            return_code = process.returncode
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            return f"执行超时（{timeout}秒），部分输出：\nSTDOUT:\n{stdout.decode('utf-8', errors='replace')}\nSTDERR:\n{stderr.decode('utf-8', errors='replace')}"

        # 解码输出
        out_text = stdout.decode('utf-8', errors='replace')
        err_text = stderr.decode('utf-8', errors='replace')

        if return_code != 0:
            return f"执行失败（返回码 {return_code}）：\nSTDOUT:\n{out_text}\nSTDERR:\n{err_text}"
        else:
            if out_text or err_text:
                return f"执行成功：\nSTDOUT:\n{out_text}\nSTDERR:\n{err_text}"
            else:
                return "执行成功，无输出。"

    # 启动交互式解释器
    elif action == "interact":
        python_exe = sys.executable
        # 使用 -i 启动交互模式，并禁用提示符重定向（默认就是交互）
        cmd = [python_exe, "-i"]

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
            'timeout_per_step': interactive_timeout
        }

        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 获取启动输出（通常是 Python 版本信息和提示符）
        initial = _collect_output(q, timeout=0.5)
        if initial:
            return f"交互式会话 {sess_id} 已启动，初始输出：\n{initial}"
        else:
            return f"交互式会话 {sess_id} 已启动。"

    # 向会话发送输入
    elif action == "send":
        if not session_id:
            return "错误：send 操作需要提供 session_id。"
        with _lock:
            session = _sessions.get(session_id)
        if not session:
            return f"错误：会话 {session_id} 不存在。"

        process = session['process']
        q = session['queue']
        stop_event = session['stop_event']
        step_timeout = interactive_timeout  # 使用传入或默认

        if stop_event.is_set() or process.poll() is not None:
            return f"会话 {session_id} 已结束。"

        # 发送输入前，先收集已有输出（作为历史）
        existing = _collect_output(q, timeout=0)  # 不等待

        # 发送输入
        try:
            if input_data is not None:
                # 确保以换行结尾？用户可能已经包含换行，我们按原样发送
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

    # 停止会话
    elif action == "stop":
        if not session_id:
            return "错误：stop 操作需要提供 session_id。"
        with _lock:
            session = _sessions.pop(session_id, None)
        if not session:
            return f"会话 {session_id} 不存在。"

        _terminate_process(session)
        return f"会话 {session_id} 已停止。"

    # 列出会话
    elif action == "list":
        with _lock:
            if not _sessions:
                return "当前无活跃会话。"
            lines = ["活跃 Python 交互式会话："]
            for sid, sess in _sessions.items():
                proc = sess['process']
                status = "运行中" if proc.poll() is None else f"已退出 (代码 {proc.returncode})"
                lines.append(f"  {sid}: {status}")
            return "\n".join(lines)

    # 获取版本
    elif action == "version":
        try:
            result = subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=5, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            if result.returncode != 0:
                return f"获取版本失败：{output}"
            return output.strip()
        except Exception as e:
            return f"执行出错：{e}"

    #获取帮助
    elif action == "help":
        try:
            result = subprocess.run([sys.executable, ("--help" if not code else ("--help"+code))], capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            if result.returncode != 0:
                return f"获取帮助失败：{output}"
            return output.strip()
        except Exception as e:
            return f"执行出错：{e}"
    else:
        return f"错误：未知操作 {action}。"