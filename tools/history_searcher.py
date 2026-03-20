#!/usr/bin/env python3
"""
tools/history_searcher.py
聊天记录搜索工具。支持关键字搜索、消息计数、获取指定消息范围。
"""

import os
import json
import glob
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 固定路径
MEMORY_DIR = Path(__file__).parent.parent / "memory"

tool_def = {
    "type": "function",
    "function": {
        "name": "history_search",
        "description": "搜索或查询已保存的聊天记录文件或工具调用记录。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["search", "count", "get", "list", "tool_stat", "tool_read"],
                    "description": "操作类型：search-聊天记录关键字搜索，count-统计聊天记录消息数量，get-获取聊天记录指定消息，list-列出聊天记录文件，tool_stat-统计工具结果文件，tool_read-读取工具结果文件内容"
                },
                "session_id": {
                    "type": "string",
                    "description": "会话/工具调用结果标识（时间戳'YYYYMMDD_hhmmss'或文件前缀名'session_YYYYMMDD_hhmmss'/'tool_YYYYMMDD_hhmmss'）。对于聊天记录相关功能，若不提供，则搜索所有会话"
                },
                "start_time": {
                    "type": "string",
                    "description": "起始时间戳，格式 YYYYMMDD_hhmmss。限定会话文件的保存时间范围，不提供则默认到最早一条"
                },
                "end_time": {
                    "type": "string",
                    "description": "结束时间戳，格式 YYYYMMDD_hhmmss。限定会话文件的保存时间范围，不提供则默认到最晚一条"
                },
                "roles": {
                    "type": "string",
                    "description": "要包含的角色，逗号分隔，如 'user,agent,tool,system'。默认 user,agent,tool",
                    "default": "user,agent,tool"
                },
                "include_tool_args": {
                    "type": "boolean",
                    "description": "对于 tool 消息，是否包含调用参数（arguments）, 默认包含。",
                    "default": True
                },
                "include_reasoning": {
                    "type": "boolean",
                    "description": "对于 agent 消息，是否包含 reasoning_content, 默认不包含。",
                    "default": False
                },
                # search 专用
                "keyword": {
                    "type": "string",
                    "description": "要搜索的关键字（用于 search）"
                },
                # count 专用
                "count_role": {
                    "type": "string",
                    "description": "要统计的角色（用于 count，若提供则只统计该角色，否则统计所有消息）"
                },
                # get 专用
                "message_start": {
                    "type": "integer",
                    "description": "起始消息编号（从1开始，用于 get）"
                },
                "message_end": {
                    "type": "integer",
                    "description": "结束消息编号（包含，用于 get），不提供则只返回 message_start 单条"
                },
                "range_type": {
                    "type": "string",
                    "enum": ["line", "char"],
                    "description": "范围类型：line-按行，char-按字符，用于 tool_read",
                    "default": "line"
                },
                "start": {
                    "type": "integer",
                    "description": "起始位置（行号或字符位置，从1开始），用于 tool_read"
                },
                "end": {
                    "type": "integer",
                    "description": "结束位置（包含，可选，若省略则只返回 start 对应的单行/单字符），用于 tool_read"
                }
            },
            "required": ["action"]
        }
    }
}

def _normalize_session_id(session_id: str) -> str:
    """将输入标准化为纯时间戳（去掉前缀）"""
    if session_id.startswith("session_"):
        return session_id[8:]
    if session_id.endswith(".json"):
        return session_id[:-5]
    session_id.strip()
    return session_id

def _parse_time_range(start: Optional[str], end: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """验证时间格式，返回可比较的字符串（直接字符串比较即可，因为格式固定）"""
    pattern = r"^\d{8}_\d{6}$"
    if start and not re.match(pattern, start):
        raise ValueError(f"起始时间格式错误，应为 YYYYMMDD_hhmmss，实际为 {start}")
    if end and not re.match(pattern, end):
        raise ValueError(f"结束时间格式错误，应为 YYYYMMDD_hhmmss，实际为 {end}")
    return start, end

def _get_session_files(session_id: Optional[str] = None,
                       start: Optional[str] = None,
                       end: Optional[str] = None) -> List[Path]:
    """获取符合条件的会话文件列表"""
    if session_id:
        sess = _normalize_session_id(session_id)
        path = MEMORY_DIR / f"session_{sess}.json"
        if path.exists():
            return [path]
        return []
    else:
        # 收集所有 session_*.json
        files = glob.glob(str(MEMORY_DIR / "session_*.json"))
        if not files:
            return []
        # 提取时间戳并过滤
        result = []
        for f in files:
            basename = os.path.basename(f)
            # 格式 session_YYYYMMDD_hhmmss.json
            match = re.match(r"session_(\d{8}_\d{6})\.json", basename)
            if match:
                ts = match.group(1)
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                result.append(Path(f))
        return sorted(result)

def _parse_roles(roles_str: str) -> List[str]:
    """解析角色字符串，返回角色列表"""
    if not roles_str:
        return []
    roles = [r.strip().lower() for r in roles_str.split(",")]
    # 将 agent 映射为 assistant（JSON 中 role 为 'assistant'）
    roles = ["assistant" if r == "agent" else r for r in roles]
    return roles

def _message_text(msg: Dict[str, Any],
                  include_tool_args: bool,
                  include_reasoning: bool) -> str:
    """根据选项获取消息的文本表示（用于搜索时的内容匹配）"""
    role = msg.get("role", "")
    parts = []

    if role == "user":
        parts.append(msg.get("content", ""))
    elif role == "assistant":
        if include_reasoning and "reasoning_content" in msg:
            parts.append(msg["reasoning_content"])
        if "content" in msg and msg["content"]:
            parts.append(msg["content"])
        if "tool_calls" in msg and include_tool_args:
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "{}")
                parts.append(f"[ToolCall: {name}({args})]")
    elif role == "tool":
        if include_tool_args:
            parts.append(msg.get("content", ""))
        # 也可不包含参数，但通常工具结果就是 content
        # 如果不想包含，但题目说默认包括，所以默认包括。
    elif role == "system":
        parts.append(msg.get("content", ""))
    return " ".join(parts)

def _format_message_output(msg: Dict[str, Any],
                           msg_index: int,
                           include_tool_args: bool,
                           include_reasoning: bool) -> str:
    """将单条消息格式化为可读输出（用于 get 操作）"""
    role = msg.get("role", "unknown")
    lines = [f"[{msg_index}] {role}:"]
    if role == "user":
        lines.append(msg.get("content", ""))
    elif role == "assistant":
        if include_reasoning and "reasoning_content" in msg:
            lines.append(f"  reasoning: {msg['reasoning_content']}")
        if "content" in msg and msg["content"]:
            lines.append(f"  content: {msg['content']}")
        if "tool_calls" in msg:
            if include_tool_args:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    args = func.get("arguments", "{}")
                    lines.append(f"  tool_call: {name}({args})")
            else:
                lines.append(f"  tool_calls present")
    elif role == "tool":
        lines.append(f"  result: {msg.get('content', '')}")
    elif role == "system":
        lines.append(msg.get("content", ""))
    return "\n".join(lines)

def execute(action: str,
            session_id: Optional[str] = None,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None,
            roles: str = "user,agent,tool",
            include_tool_args: bool = True,
            include_reasoning: bool = False,
            keyword: Optional[str] = None,
            count_role: Optional[str] = None,
            message_start: Optional[int] = None,
            message_end: Optional[int] = None,
            range_type: str = "line",
            start: Optional[int] = None,
            end: Optional[int] = None) -> str:
    """
    执行历史记录搜索/统计/获取操作。
    """
    if action not in ["tool_stat", "tool_read"]:
        # 参数预处理
        try:
            start, end = _parse_time_range(start_time, end_time)
        except ValueError as e:
            return f"参数错误：{e}"

    # 获取会话文件列表
    files = _get_session_files(session_id, start, end)
    if not files:
        return "未找到符合条件的聊天记录。"

    # 解析角色过滤
    allowed_roles = _parse_roles(roles)

    if action == "search":
        if not keyword:
            return "错误：search 操作需要提供 keyword。"
        results = []
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    messages = json.load(fp)
            except Exception as e:
                continue  # 跳过损坏文件
            # 遍历消息
            for idx, msg in enumerate(messages, start=1):
                role = msg.get("role", "")
                if allowed_roles and role not in allowed_roles:
                    continue
                text = _message_text(msg, include_tool_args, include_reasoning)
                if keyword in text:
                    filename = f.name
                    results.append(f"{filename} 消息 #{idx}")
        if results:
            return "找到包含关键字的记录：\n" + "\n".join(results)
        else:
            return "未找到包含关键字的记录。"

    elif action == "count":
        total = 0
        role_count = {} if count_role else None
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    messages = json.load(fp)
            except:
                continue
            if count_role:
                role_map = {"agent": "assistant", "user": "user", "tool": "tool"}
                target = role_map.get(count_role.lower(), count_role.lower())
                cnt = sum(1 for msg in messages if msg.get("role") == target)
                total += cnt
            else:
                total += len(messages)
        if count_role:
            return f"角色 '{count_role}' 的消息总数：{total}"
        else:
            return f"总消息条数：{total}"

    elif action == "get":
        if not session_id:
            return "错误：get 操作必须指定 session_id。"
        if message_start is None:
            return "错误：get 操作需要 message_start。"
        if len(files) == 0:
            return "指定的会话不存在。"
        # 只有一个文件
        f = files[0]
        try:
            with open(f, "r", encoding="utf-8") as fp:
                messages = json.load(fp)
        except Exception as e:
            return f"读取会话失败：{e}"
        total = len(messages)
        start_idx = message_start
        end_idx = message_end if message_end is not None else message_start
        if start_idx < 1 or start_idx > total:
            return f"起始编号 {start_idx} 超出范围 (1-{total})"
        if end_idx < start_idx or end_idx > total:
            return f"结束编号 {end_idx} 超出范围 (1-{total})"

        output = []
        for idx in range(start_idx, end_idx + 1):
            msg = messages[idx-1]
            role = msg.get("role", "")
            if allowed_roles and role not in allowed_roles:
                continue
            output.append(_format_message_output(msg, idx, include_tool_args, include_reasoning))
        if output:
            return "\n---\n".join(output)
        else:
            return "指定范围内没有符合角色过滤的消息。"
    elif action == "list":
        # 获取符合条件的会话文件列表
        files = _get_session_files(session_id, start, end)
        if not files:
            return "未找到符合条件的会话。"
        result_lines = [f"找到 {len(files)} 个会话："]
        for f in files:
            # 提取时间戳
            basename = f.name
            match = re.match(r"session_(\d{8}_\d{6})\.json", basename)
            ts = match.group(1) if match else "未知"
            # 读取消息数量（可选）
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    msgs = json.load(fp)
                msg_count = len(msgs)
            except Exception:
                msg_count = "?"
            result_lines.append(f"  {ts} - {msg_count} 条消息 - {f.name}")
        return "\n".join(result_lines)
    elif action == "tool_stat":
        if not session_id:
            return "错误：tool_stat 操作需要提供 session_id。"
        # 规范化文件名
        fname = session_id.strip()
        if not fname.endswith(".txt"):
            fname = fname + ".txt"
        if not fname.startswith("tool_"):
            fname = "tool_" + fname
        file_path = MEMORY_DIR / fname
        if not file_path.exists():
            return f"文件不存在：{fname}"
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                content = fp.read()
            lines = content.splitlines()
            line_count = len(lines)
            char_count = len(content)
            return f"文件 {fname} 统计信息：\n行数：{line_count}\n字符数：{char_count}"
        except Exception as e:
            return f"读取文件失败：{e}"

    # 新增：处理工具结果文件读取
    elif action == "tool_read":
        if not session_id:
            return "错误：tool_read 操作需要提供 session_id。"
        if start is None:
            return "错误：tool_read 操作需要提供 start 参数。"
        # 规范化文件名
        fname = session_id.strip()
        if not fname.endswith(".txt"):
            fname = fname + ".txt"
        if not fname.startswith("tool_"):
            fname = "tool_" + fname
        file_path = MEMORY_DIR / fname
        if not file_path.exists():
            return f"文件不存在：{fname}"
        try:
            with open(file_path, "r", encoding="utf-8") as fp:
                content = fp.read()
        except Exception as e:
            return f"读取文件失败：{e}"

        range_type = range_type or "line"
        if range_type == "line":
            lines = content.splitlines()
            total_lines = len(lines)
            s = start
            e = end if end is not None else s
            if s < 1 or s > total_lines:
                return f"起始行号 {s} 超出范围 (1-{total_lines})"
            if e < s or e > total_lines:
                return f"结束行号 {e} 超出范围 (1-{total_lines})"
            result_lines = lines[s-1:e]
            return "\n".join(result_lines)
        elif range_type == "char":
            total_chars = len(content)
            s = start
            e = end if end is not None else s
            if s < 1 or s > total_chars:
                return f"起始字符位置 {s} 超出范围 (1-{total_chars})"
            if e < s or e > total_chars:
                return f"结束字符位置 {e} 超出范围 (1-{total_chars})"
            # 转换为 0-based 索引，切片包含 end
            return content[s-1:e]
        else:
            return f"未知的 range_type：{range_type}"
    else:
        return f"错误：未知操作 {action}"