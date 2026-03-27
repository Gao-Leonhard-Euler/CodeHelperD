#!/usr/bin/env python3
"""
tools/debugger.py
提供 gdb 调试会话管理：创建、发送命令、关闭、列出会话。
支持自定义 gdb 启动参数，并可获取 gdb --help 信息。
支持编码参数，解决Windows中文乱码问题。
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
        "name": "debugger",
        "description": "使用 gdb 调试二进制程序。支持创建会话、发送命令、关闭会话和列出会话。支持编码参数解决中文乱码问题。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "send", "close", "list"],
                    "description": "操作类型：create-创建新调试会话；send-向会话发送命令；close-关闭会话；list-列出所有会话。"
                },
                "gdb_args": {
                    "type": "string",
                    "description": "gdb 启动参数（如 '-q ./a.out'），默认为空。可通过 '--help' 获取帮助。"
                },
                "encoding": {
                    "type": "string",
                    "enum": ["auto", "utf-8", "gbk", "ascii", "latin-1", "cp1252", "cp437", "gb2312", "gb18030"],
                    "description": "输出编码：auto（根据平台自动选择，Windows用gbk，其他用utf-8）,utf-8,gbk,ascii,latin-1等。默认auto。",
                    "default": "auto"
                },
                "timeout_per_step": {
                    "type": "number",
                    "description": "每次命令执行的超时时间（秒），默认 5.0",
                    "default": 5.0
                },
                "session_id": {
                    "type": "string",
                    "description": "会话 ID（用于 send 和 close）"
                },
                "command": {
                    "type": "string",
                    "description": "发给 gdb 的命令（用于 send）"
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

def _collect_output(q: queue.Queue, timeout: float, encoding: str = 'utf-8') -> str:
    """收集队列中的输出，最多等待 timeout 秒，使用指定编码解码"""
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
            text = data.decode(encoding, errors='replace')
        except:
            text = str(data)
        # 去掉末尾换行以便整洁
        lines.append(f"[{stream}] {text.rstrip()}")
    return "\n".join(lines)

def _resolve_encoding(encoding: str) -> str:
    """解析编码参数，auto根据平台选择"""
    if encoding == 'auto':
        # 根据平台自动选择编码
        if sys.platform == 'win32':
            return 'gbk'  # Windows控制台默认编码
        else:
            return 'utf-8'  # Linux/Mac通常使用UTF-8
    return encoding

def execute(action: str,
            gdb_args: str = "",
            encoding: str = 'auto',
            timeout_per_step: float = 5.0,
            session_id: Optional[str] = None,
            command: Optional[str] = None) -> str:
    """
    执行调试器操作。
    """
    global _sessions

    # 解析编码
    resolved_encoding = _resolve_encoding(encoding)

    # 创建新会话
    if action == "create":
        # 确定 gdb 可执行文件路径
        gdb_cmd = "gdb"
        if sys.platform == "win32":
            # 尝试常见路径或直接使用 gdb.exe（需在 PATH 中）
            gdb_cmd = "gdb.exe"

        # 构建完整命令
        if gdb_args:
            # 使用 shlex 分割参数，考虑引号
            try:
                args_list = shlex.split(gdb_args, posix=(sys.platform != "win32"))
            except Exception as e:
                return f"参数解析失败：{e}"
            cmd = [gdb_cmd] + args_list
        else:
            cmd = [gdb_cmd]

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
            return f"错误：找不到 gdb 可执行文件，请确保已安装并加入 PATH。"
        except Exception as e:
            return f"启动 gdb 失败：{e}"

        sess_id = _create_session_id()
        q = queue.Queue()
        stop_event = threading.Event()
        session = {
            'process': process,
            'queue': q,
            'stop_event': stop_event,
            'timeout_per_step': timeout_per_step,
            'gdb_args': gdb_args,
            'encoding': resolved_encoding
        }

        t = threading.Thread(target=_reader_thread, args=(process, q, stop_event))
        t.daemon = True
        t.start()
        session['thread'] = t

        with _lock:
            _sessions[sess_id] = session

        # 获取启动输出（如 gdb 版本信息、帮助等）
        initial = _collect_output(q, timeout=0.5, encoding=resolved_encoding)
        if initial:
            return f"编码: {resolved_encoding}\n调试会话 {sess_id} 已创建。初始输出：\n{initial}"
        else:
            return f"编码: {resolved_encoding}\n调试会话 {sess_id} 已创建。"

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
        session_encoding = session.get('encoding', 'utf-8')

        if stop_event.is_set() or process.poll() is not None:
            return f"会话 {session_id} 已结束。"

        # 发送命令前收集已有输出（如之前的提示符）
        existing = _collect_output(q, timeout=0, encoding=session_encoding)

        # 发送命令（需添加换行符，使用会话编码）
        try:
            cmd_bytes = (command + '\n').encode(session_encoding, errors='replace')
            process.stdin.write(cmd_bytes)
            process.stdin.flush()
        except Exception as e:
            return f"写入命令失败：{e}"

        # 收集新输出直到超时
        new_output = _collect_output(q, timeout=step_timeout, encoding=session_encoding)

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
                lines.append(f"  {sid}: gdb {sess.get('gdb_args', '')} - {status}")
            return "\n".join(lines)

    else:
        return f"错误：未知操作 {action}。"