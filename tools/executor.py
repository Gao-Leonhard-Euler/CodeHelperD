#!/usr/bin/env python3
"""
tools/executor.py
执行可执行文件，支持交互式会话、超时控制和会话管理。
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
from typing import Dict, Optional, Any, List

# 全局会话存储
_sessions: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()  # 用于保护会话字典（虽然主线程单线程，但读取线程可能修改状态）

tool_def = {
    "type": "function",
    "function": {
        "name": "executor",
        "description": "执行程序并管理交互式会话。支持启动、发送输入、停止和列出会话。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["start", "send", "stop", "list"],
                    "description": "操作类型"
                },
                # start 参数
                "command": {
                    "type": "string",
                    "description": "要执行的程序，可带有参数（如 './a.out' 或 'python script.py'）"
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（可选）"
                },
                "env": {
                    "type": "object",
                    "description": "环境变量字典（可选）"
                },
                "timeout_per_step": {
                    "type": "number",
                    "description": "每次交互默认超时时间（秒），默认 2.0",
                    "default": 2.0
                },
                # send 参数
                "session_id": {
                    "type": "string",
                    "description": "会话标识"
                },
                "input_data": {
                    "type": "string",
                    "description": "发送给程序的输入"
                },
                "timeout": {
                    "type": "number",
                    "description": "本次交互的超时时间（覆盖默认）"
                },
                # stop 参数（只需要 session_id）
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
    """
    读取进程的 stdout 和 stderr，将数据放入队列。
    当进程结束或 stop_event 被设置时退出。
    """
    # 为了同时读取两个流，需要分别处理
    # 使用 select 或线程？这里为简单，为每个流创建单独的读取器？
    # 更简单：使用两个线程，但管理复杂。我们可以使用非阻塞读取。
    # 但为了跨平台，采用循环读取两个流，非阻塞方式。
    # 在 Unix 上可以使用 os.set_blocking，在 Windows 上可以使用 PeekNamedPipe？复杂。
    # 替代方案：使用两个队列，每个流一个线程。我们为每个会话启动两个读取线程，分别处理 stdout 和 stderr。
    # 这样代码更清晰。
    def _read_stream(stream, stream_name, q):
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

    t_out = threading.Thread(target=_read_stream, args=(process.stdout, 'stdout', q))
    t_err = threading.Thread(target=_read_stream, args=(process.stderr, 'stderr', q))
    t_out.daemon = True
    t_err.daemon = True
    t_out.start()
    t_err.start()

    # 等待进程结束
    process.wait()
    stop_event.set()  # 通知停止
    t_out.join()
    t_err.join()
    q.put(('EOF', None))  # 放入结束标记

def _terminate_process(session: Dict[str, Any]):
    """终止进程并清理资源"""
    process = session['process']
    stop_event = session['stop_event']
    if not stop_event.is_set():
        stop_event.set()
    # 终止进程
    try:
        if sys.platform == "win32":
            process.terminate()
        else:
            # 尝试先发送 SIGTERM，然后 SIGKILL 如果必要
            process.terminate()
        # 等待进程结束
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    except Exception:
        pass

def execute(action: str,
            command: Optional[str] = None,
            cwd: Optional[str] = None,
            env: Optional[Dict[str, str]] = None,
            timeout_per_step: float = 2.0,
            session_id: Optional[str] = None,
            input_data: Optional[str] = None,
            timeout: Optional[float] = None) -> str:
    """
    执行器主函数。
    """
    global _sessions

    # 启动新会话
    if action == "start":
        if not command:
            return "错误：start 操作需要提供 command。"

        # 解析命令
        try:
            args = shlex.split(command, posix=(sys.platform != "win32"))
        except Exception as e:
            return f"命令解析失败：{e}"

        # 准备环境变量
        env_dict = os.environ.copy()
        if env:
            env_dict.update(env)

        # 启动进程
        try:
            process = subprocess.Popen(
                args,
                cwd=cwd,
                env=env_dict,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,  # 使用字节流，避免编码问题
                bufsize=0,    # 无缓冲
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
        except Exception as e:
            return f"启动失败：{e}"

        # 创建会话记录
        sess_id = _create_session_id()
        q = queue.Queue()
        stop_event = threading.Event()
        session = {
            'process': process,
            'queue': q,
            'stop_event': stop_event,
            'timeout_per_step': timeout_per_step,
            'cwd': cwd,
            'command': command
        }

        # 启动读取线程
        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 初始可能有一些输出，立即返回
        output = _collect_output(session, timeout=0.1)  # 短超时获取启动输出
        if output:
            return f"会话 {sess_id} 已启动，初始输出：\n{output}"
        else:
            return f"会话 {sess_id} 已启动。"

    # 发送输入到会话
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
        step_timeout = timeout if timeout is not None else session.get('timeout_per_step', 2.0)

        if stop_event.is_set() or process.poll() is not None:
            return f"会话 {session_id} 已结束。"

        # 先清空已有输出（可选，但为了保持顺序，我们先收集已有输出作为历史）
        # 这里我们采用先读取所有现有输出，然后发送输入，再等待新输出。
        # 但更好的做法是：返回之前未读取的输出 + 新输出。为了简化，我们每次发送都返回从上次到现在的所有输出。
        # 实际上，每次调用 send 时，队列中可能堆积了之前的输出，我们需要将它们返回。
        # 所以我们先收集队列中现有所有输出（不阻塞），然后发送输入，再收集新输出直到超时。

        # 收集现有输出
        existing = []
        while True:
            try:
                item = q.get_nowait()
                existing.append(item)
            except queue.Empty:
                break

        # 发送输入
        try:
            if input_data is not None:
                process.stdin.write(input_data.encode('utf-8', errors='replace'))
                process.stdin.flush()
        except Exception as e:
            return f"写入输入失败：{e}"

        # 收集新输出直到超时
        new_output = []
        start_time = time.time()
        while time.time() - start_time < step_timeout:
            try:
                item = q.get(timeout=step_timeout - (time.time() - start_time))
                new_output.append(item)
                if item[0] == 'EOF':
                    # 进程结束
                    break
            except queue.Empty:
                break

        # 合并所有输出
        all_items = existing + new_output
        if not all_items:
            return "（无输出）"

        # 格式化输出
        output_lines = []
        for stream, data in all_items:
            if stream == 'EOF':
                output_lines.append("[进程已结束]")
                continue
            # 解码数据
            try:
                text = data.decode('utf-8', errors='replace')
            except:
                text = str(data)
            # 去掉末尾换行以便显示整洁，但保留
            output_lines.append(f"[{stream}] {text}")

        return "\n".join(output_lines)

    # 停止并删除会话
    elif action == "stop":
        if not session_id:
            return "错误：stop 操作需要提供 session_id。"
        with _lock:
            session = _sessions.pop(session_id, None)
        if not session:
            return f"会话 {session_id} 不存在。"

        _terminate_process(session)
        return f"会话 {session_id} 已停止。"

    # 列出活跃会话
    elif action == "list":
        with _lock:
            if not _sessions:
                return "当前无活跃会话。"
            lines = ["活跃会话："]
            for sid, sess in _sessions.items():
                proc = sess['process']
                status = "运行中" if proc.poll() is None else f"已退出 (代码 {proc.returncode})"
                lines.append(f"  {sid}: {sess['command']} - {status}")
            return "\n".join(lines)

    else:
        return f"错误：未知操作 {action}"

def _collect_output(session: Dict[str, Any], timeout: float = 0.1) -> str:
    """收集当前队列中的所有输出，最多等待 timeout 秒"""
    q = session['queue']
    items = []
    start = time.time()
    while True:
        remaining = timeout - (time.time() - start)
        if remaining<0:
            break
        try:
            item = q.get_nowait()
            items.append(item)
        except queue.Empty:
            try:
                # 收集新输出直到超时
                item = q.get(timeout=remaining)
                items.append(item)
            except queue.Empty:
                break
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