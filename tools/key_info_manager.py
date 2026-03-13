#!/usr/bin/env python3
"""
tools/key_info_manager.py
管理长期记忆文件 memory/key_info.txt 的内容，提供读取、追加、替换、删除等操作。
"""

import os
from pathlib import Path

# 固定路径
KEY_INFO_PATH = Path(__file__).parent.parent / "memory" / "key_info.txt"

tool_def = {
    "type": "function",
    "function": {
        "name": "key_info_manage",
        "description": "管理长期记忆文件 key_info.txt 的内容。该文件用于存储需要长期保留的关键信息，每次对话会自动加载其内容作为系统消息。支持读取、追加、替换或删除行内容（行号从1开始）。",
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "append", "replace", "delete"],
                    "description": "操作类型：read-读取全部内容，append-追加内容，replace-替换指定行或全文，delete-删除指定行或全文"
                },
                "content": {
                    "type": "string",
                    "description": "要添加或替换的文本内容（用于 append 和 replace 操作）"
                },
                "line_start": {
                    "type": "integer",
                    "description": "起始行号（从1开始），用于 replace 或 delete 的行范围操作"
                },
                "line_end": {
                    "type": "integer",
                    "description": "结束行号（包含），默认为 line_start，用于 replace 或 delete 的行范围操作"
                },
                "all": {
                    "type": "boolean",
                    "description": "若为 true，则 replace 或 delete 作用于整个文件，忽略 line_start/line_end",
                    "default": False
                }
            },
            "required": ["operation"]
        }
    }
}

def _ensure_file_exists():
    """确保文件存在，若不存在则创建空文件"""
    KEY_INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not KEY_INFO_PATH.exists():
        KEY_INFO_PATH.write_text("", encoding="utf-8")

def _read_lines() -> list:
    """读取文件所有行（带换行符）"""
    _ensure_file_exists()
    with open(KEY_INFO_PATH, "r", encoding="utf-8") as f:
        return f.readlines()

def _write_lines(lines: list):
    """写入行列表到文件"""
    with open(KEY_INFO_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)

def execute(operation: str, content: str = None, line_start: int = None,
            line_end: int = None, all: bool = False) -> str:
    """
    执行关键信息管理操作。
    """
    # 确保文件存在
    _ensure_file_exists()

    if operation == "read":
        text = KEY_INFO_PATH.read_text(encoding="utf-8")
        if not text:
            return "当前关键信息为空。"
        return f"当前关键信息内容：\n{text}"

    elif operation == "append":
        if content is None:
            return "错误：append 操作需要提供 content。"
        with open(KEY_INFO_PATH, "a", encoding="utf-8") as f:
            f.write(content + "\n" if not content.endswith("\n") else content)
        return f"已追加内容到关键信息文件。\n新内容：\n{content}"

    elif operation == "replace":
        if all:
            if content is None:
                return "错误：全文替换需要提供 content。"
            KEY_INFO_PATH.write_text(content, encoding="utf-8")
            return f"已全文替换关键信息文件。\n新内容：\n{content}"
        else:
            if line_start is None:
                return "错误：replace 操作需要指定 line_start 或设置 all=True。"
            lines = _read_lines()
            total_lines = len(lines)
            if line_start < 1 or line_start > total_lines:
                return f"错误：line_start {line_start} 超出文件行数 {total_lines}。"
            end = line_end if line_end is not None else line_start
            if end < line_start or end > total_lines:
                return f"错误：line_end {end} 无效或超出文件行数。"
            # 替换指定行范围
            if content is None:
                content = ""  # 替换为空行
            # 将内容拆分为行（保留换行符？我们约定 content 不自动加换行，需要模型自己加）
            # 但为了简单，我们直接替换整行内容，并确保每行有换行符
            # 这里我们采用：将 content 作为新行的文本，不自动加换行，但原文件的行有换行符，我们需要处理
            # 更好的方式是：将 content 直接作为该行的新文本，如果 content 没有换行符，我们会添加一个换行符以保持文件格式。
            # 对于多行替换，我们允许 content 包含换行符，直接替换整个行范围。
            new_lines = lines[:line_start-1]
            # 将 content 拆分为行，并确保每行末尾有换行符（最后一行除外？但 writelines 不会自动加，需要 content 本身包含）
            # 我们要求调用者 content 已经包含所需换行符，或者我们按原样插入。
            # 简单起见，将 content 作为字符串插入，不处理换行符。
            if content:
                new_lines.append(content + "\n" if not content.endswith("\n") else content)
            else:
                # 删除这些行（如果 content 为空，则相当于删除行范围）
                pass
            new_lines.extend(lines[end:])
            _write_lines(new_lines)
            return f"已替换第 {line_start} 到 {end} 行。"

    elif operation == "delete":
        if all:
            KEY_INFO_PATH.write_text("", encoding="utf-8")
            return "已清空关键信息文件。"
        else:
            if line_start is None:
                return "错误：delete 操作需要指定 line_start 或设置 all=True。"
            lines = _read_lines()
            total_lines = len(lines)
            if line_start < 1 or line_start > total_lines:
                return f"错误：line_start {line_start} 超出文件行数 {total_lines}。"
            end = line_end if line_end is not None else line_start
            if end < line_start or end > total_lines:
                return f"错误：line_end {end} 无效或超出文件行数。"
            new_lines = lines[:line_start-1] + lines[end:]
            _write_lines(new_lines)
            return f"已删除第 {line_start} 到 {end} 行。"

    else:
        return f"错误：未知操作 '{operation}'。"