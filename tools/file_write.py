#!/usr/bin/env python3
"""
tools/file_write.py
提供文件写入和修改功能，支持二进制和文本文件。包括覆盖写入、插入、删除等。
"""

import os
import base64
from typing import Optional, List, Tuple

tool_def = {
    "type": "function",
    "function": {
        "name": "file_write",
        "description": "对文件进行写入、插入、删除等修改操作。支持二进制和文本模式。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "操作的文件路径"
                },
                "mode": {
                    "type": "string",
                    "enum": ["binary", "text"],
                    "description": "操作模式：binary 或 text",
                    "default": "text"
                },
                "encoding": {
                    "type": "string",
                    "description": "文本文件的编码（仅在 mode=text 时使用），默认 utf-8",
                    "default": "utf-8"
                },
                "operation": {
                    "type": "string",
                    "enum": ["write", "insert", "delete"],
                    "description": "要执行的操作"
                },
                "data": {
                    "type": "string",
                    "description": "要写入的数据。对于二进制模式，应为 base64 编码的字符串；对于文本模式，直接是文本内容。用于 write 和 insert。"
                },
                "offset": {
                    "type": "integer",
                    "description": "二进制文件的插入位置（字节偏移量），用于 insert 操作（mode=binary）"
                },
                "insert_type": {
                    "type": "string",
                    "enum": ["char_index", "line_column"],
                    "description": "文本插入位置的指定方式：char_index 表示按字符索引，line_column 表示按行号和列号"
                },
                "char_index": {
                    "type": "integer",
                    "description": "字符索引（从0开始），用于 insert_type=char_index"
                },
                "line": {
                    "type": "integer",
                    "description": "行号（从1开始），用于 insert_type=line_column"
                },
                "column": {
                    "type": "integer",
                    "description": "列号（从0开始，即该行第几个字符），用于 insert_type=line_column"
                },
                "delete_type": {
                    "type": "string",
                    "enum": ["bytes", "chars", "lines"],
                    "description": "删除的类型：bytes（二进制字节范围）、chars（文本字符范围）、lines（文本行范围）"
                },
                "start_byte": {
                    "type": "integer",
                    "description": "删除字节范围的起始位置（包含），用于 delete_type=bytes"
                },
                "end_byte": {
                    "type": "integer",
                    "description": "删除字节范围的结束位置（不包含），用于 delete_type=bytes"
                },
                "start_char": {
                    "type": "integer",
                    "description": "删除字符范围的起始位置（包含），用于 delete_type=chars"
                },
                "end_char": {
                    "type": "integer",
                    "description": "删除字符范围的结束位置（不包含），用于 delete_type=chars"
                },
                "line_numbers": {
                    "type": "string",
                    "description": "要删除的行号，格式同 read_lines（单个、列表、范围或'all'），用于 delete_type=lines"
                }
            },
            "required": ["file_path", "operation"]
        }
    }
}

def _parse_line_numbers(line_numbers_str: str) -> List[int]:
    """解析行号字符串，返回整数列表"""
    if line_numbers_str == "all":
        return []
    result = []
    parts = line_numbers_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            start, end = map(int, part.split('-'))
            result.extend(range(start, end+1))
        else:
            result.append(int(part))
    return sorted(set(result))

def _validate_file_exists(file_path: str) -> Tuple[bool, str]:
    """检查文件是否存在，若不存在则返回错误"""
    if not os.path.isfile(file_path):
        return False, f"错误：文件 {file_path} 不存在"
    return True, ""

def execute(file_path: str, operation: str, mode: str = "text", encoding: str = "utf-8",
            data: Optional[str] = None, offset: Optional[int] = None,
            insert_type: Optional[str] = None, char_index: Optional[int] = None,
            line: Optional[int] = None, column: Optional[int] = None,
            delete_type: Optional[str] = None,
            start_byte: Optional[int] = None, end_byte: Optional[int] = None,
            start_char: Optional[int] = None, end_char: Optional[int] = None,
            line_numbers: Optional[str] = None) -> str:
    """
    执行文件写入/修改操作。
    """
    # 对于 insert 和 delete，文件必须存在
    if operation != "write":
        ok, err = _validate_file_exists(file_path)
        if not ok:
            return err

    try:
        if mode == "binary":
            # 二进制模式
            if operation == "write":
                if data is None:
                    return "错误：write 操作需要 data 参数"
                try:
                    binary_data = base64.b64decode(data)
                except Exception as e:
                    return f"错误：data 不是有效的 base64 编码：{e}"
                with open(file_path, "wb") as f:
                    f.write(binary_data)
                return f"成功写入 {len(binary_data)} 字节到 {file_path}"

            elif operation == "insert":
                if data is None:
                    return "错误：insert 操作需要 data 参数"
                if offset is None:
                    return "错误：insert 操作需要 offset 参数（字节偏移量）"
                try:
                    binary_data = base64.b64decode(data)
                except Exception as e:
                    return f"错误：data 不是有效的 base64 编码：{e}"
                with open(file_path, "rb") as f:
                    original = f.read()
                file_size = len(original)
                if offset < 0 or offset > file_size:
                    return f"错误：offset {offset} 超出文件范围 [0, {file_size}]"
                new_content = original[:offset] + binary_data + original[offset:]
                with open(file_path, "wb") as f:
                    f.write(new_content)
                return f"成功在偏移量 {offset} 处插入 {len(binary_data)} 字节"

            elif operation == "delete":
                if delete_type != "bytes":
                    return "错误：二进制模式仅支持 delete_type=bytes"
                if start_byte is None or end_byte is None:
                    return "错误：delete 操作需要 start_byte 和 end_byte 参数"
                with open(file_path, "rb") as f:
                    original = f.read()
                file_size = len(original)
                if start_byte < 0 or start_byte >= file_size:
                    return f"错误：start_byte {start_byte} 超出文件范围 [0, {file_size-1}]"
                if end_byte <= start_byte or end_byte > file_size:
                    return f"错误：end_byte {end_byte} 必须大于 start_byte 且不超过文件大小 {file_size}"
                new_content = original[:start_byte] + original[end_byte:]
                with open(file_path, "wb") as f:
                    f.write(new_content)
                return f"成功删除字节范围 [{start_byte}:{end_byte})，剩余 {len(new_content)} 字节"

            else:
                return f"错误：不支持的操作 '{operation}' for binary mode"

        else:  # text mode
            # 读取原文件内容（如果文件存在）
            if os.path.isfile(file_path):
                with open(file_path, "r", encoding=encoding) as f:
                    original = f.read()
            else:
                original = ""

            if operation == "write":
                if data is None:
                    return "错误：write 操作需要 data 参数"
                with open(file_path, "w", encoding=encoding) as f:
                    f.write(data)
                return f"成功写入文本到 {file_path}（编码：{encoding}）"

            elif operation == "insert":
                if data is None:
                    return "错误：insert 操作需要 data 参数"
                if insert_type is None:
                    return "错误：insert 操作需要指定 insert_type"

                if insert_type == "char_index":
                    if char_index is None:
                        return "错误：insert_type=char_index 需要 char_index 参数"
                    pos = char_index
                    if pos < 0 or pos > len(original):
                        return f"错误：char_index {pos} 超出范围 [0, {len(original)}]"
                elif insert_type == "line_column":
                    if line is None or column is None:
                        return "错误：insert_type=line_column 需要 line 和 column 参数"
                    lines = original.splitlines(keepends=True)
                    if line < 1 or line > len(lines):
                        return f"错误：行号 {line} 超出范围 [1, {len(lines)}]"
                    line_content = lines[line-1]
                    if column < 0 or column > len(line_content):
                        return f"错误：列号 {column} 超出该行范围 [0, {len(line_content)}]"
                    pos = sum(len(lines[i]) for i in range(line-1)) + column
                else:
                    return f"错误：不支持的 insert_type '{insert_type}'"

                new_content = original[:pos] + data + original[pos:]
                with open(file_path, "w", encoding=encoding) as f:
                    f.write(new_content)
                return f"成功在位置 {pos} 插入文本（编码：{encoding}）"

            elif operation == "delete":
                if delete_type is None:
                    return "错误：delete 操作需要指定 delete_type"

                if delete_type == "chars":
                    if start_char is None or end_char is None:
                        return "错误：delete_type=chars 需要 start_char 和 end_char 参数"
                    if start_char < 0 or start_char >= len(original):
                        return f"错误：start_char {start_char} 超出范围 [0, {len(original)-1}]"
                    if end_char <= start_char or end_char > len(original):
                        return f"错误：end_char {end_char} 必须大于 start_char 且不超过字符总数 {len(original)}"
                    new_content = original[:start_char] + original[end_char:]

                elif delete_type == "lines":
                    if line_numbers is None:
                        return "错误：delete_type=lines 需要 line_numbers 参数"
                    lines = original.splitlines(keepends=True)
                    line_nums = _parse_line_numbers(line_numbers)
                    if not line_nums:  # all lines
                        new_content = ""
                    else:
                        keep_lines = []
                        for i, ln in enumerate(lines, start=1):
                            if i not in line_nums:
                                keep_lines.append(ln)
                        new_content = ''.join(keep_lines)
                else:
                    return f"错误：不支持的 delete_type '{delete_type}' for text mode"

                with open(file_path, "w", encoding=encoding) as f:
                    f.write(new_content)
                return f"成功删除指定内容，新文件大小 {len(new_content)} 字符"

            else:
                return f"错误：不支持的操作 '{operation}' for text mode"

    except Exception as e:
        return f"执行文件操作时发生错误：{str(e)}"