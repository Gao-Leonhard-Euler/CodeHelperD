#!/usr/bin/env python3
"""
tools/file_read.py
提供文件读取功能，支持二进制和文本文件。
"""

import os
import base64
from typing import Optional, List

tool_def = {
    "type": "function",
    "function": {
        "name": "file_read",
        "description": "读取文件信息或内容，支持二进制和文本模式。可获取文件大小（文本包括字符数和行号）、全文、指定字节/字符范围内容、指定行内容。可以进行关键词位置查找。",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "要读取的文件路径"
                },
                "mode": {
                    "type": "string",
                    "enum": ["binary", "text"],
                    "description": "读取模式：binary 表示二进制文件，text 表示文本文件",
                    "default": "text"
                },
                "encoding": {
                    "type": "string",
                    "description": "文本文件的编码（仅在 mode=text 时使用），默认 utf-8",
                    "default": "utf-8"
                },
                "operation": {
                    "type": "string",
                    "enum": ["size", "read_all", "read_bytes", "read_chars", "read_lines", "search"],
                    "description": "要执行的操作"
                },
                "start_byte": {
                    "type": "integer",
                    "description": "读取字节范围的起始位置（包含），用于 read_bytes"
                },
                "end_byte": {
                    "type": "integer",
                    "description": "读取字节范围的结束位置（不包含），用于 read_bytes；若不提供则读到文件末尾"
                },
                "start_char": {
                    "type": "integer",
                    "description": "读取字符范围的起始位置（包含），用于 read_chars"
                },
                "num_chars": {
                    "type": "integer",
                    "description": "要读取的字符数，用于 read_chars；若不提供则从 start_char 读到末尾"
                },
                "line_numbers": {
                    "type": "string",
                    "description": "要读取的行号，格式：单个数字（如 '5'）、逗号分隔列表（如 '1,3,5'）、范围（如 '1-10'）或 'all'。用于 read_lines"
                },
                "keyword": {
                    "type": "string",
                    "description": "要搜索的关键词，用于 search 操作"
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "是否区分大小写，默认为 True",
                    "default": True
                },
                "max_matches": {
                    "type": "integer",
                    "description": "最大返回的匹配数量，默认 100",
                    "default": 100
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

def execute(file_path: str, operation: str, mode: str = "text", encoding: str = "utf-8",
            start_byte: Optional[int] = None, end_byte: Optional[int] = None,
            start_char: Optional[int] = None, num_chars: Optional[int] = None,
            line_numbers: Optional[str] = None,
            keyword: Optional[str] = None, case_sensitive: bool = True,
            max_matches: Optional[int] = 100) -> str:
    """
    执行文件读取操作。
    """
    if not os.path.isfile(file_path):
        return f"错误：文件 {file_path} 不存在"

    try:
        if mode == "binary":
            with open(file_path, "rb") as f:
                data = f.read()
                file_size = len(data)
                if operation == "size":
                    return f"文件大小：{file_size} 字节"
                elif operation == "read_all":
                    encoded = base64.b64encode(data).decode('ascii')
                    return f"文件内容（base64）：{encoded}"
                elif operation == "read_bytes":
                    if start_byte is None:
                        return "错误：read_bytes 需要 start_byte 参数"
                    if start_byte < 0 or start_byte >= file_size:
                        return f"错误：start_byte {start_byte} 超出文件范围 [0, {file_size-1}]"
                    end = end_byte if end_byte is not None else file_size
                    if end > file_size:
                        end = file_size
                    if end <= start_byte:
                        return "错误：end_byte 必须大于 start_byte"
                    chunk = data[start_byte:end]
                    encoded = base64.b64encode(chunk).decode('ascii')
                    return f"读取字节 [{start_byte}:{end}) 的 base64 编码：{encoded}"
                elif operation == "search":
                    if keyword is None:
                        return "错误：search 操作需要 keyword 参数"
                    # base64 解码 keyword
                    try:
                        keyword_bytes = base64.b64decode(keyword)
                    except Exception:
                        return "错误：keyword 必须是一个有效的 base64 字符串"
                    # 确定搜索范围
                    file_size = len(data)
                    search_start = start_byte if start_byte is not None else 0
                    search_end = end_byte if end_byte is not None else file_size
                    if search_start < 0 or search_start >= file_size:
                        return f"错误：start_byte {search_start} 超出文件范围 [0, {file_size-1}]"
                    if search_end > file_size:
                        search_end = file_size
                    if search_end <= search_start:
                        return "错误：搜索范围无效，end_byte 必须大于 start_byte"
                    # 在指定范围内搜索（始终精确匹配，忽略 case_sensitive）
                    search_data = data[search_start:search_end]
                    positions = []
                    pos = 0
                    max_cnt = max_matches if max_matches is not None else 100
                    while True:
                        found = search_data.find(keyword_bytes, pos)
                        if found == -1 or len(positions) >= max_cnt:
                            break
                        # 转换为全局字节偏移
                        global_pos = search_start + found
                        positions.append(global_pos)
                        pos = found + len(keyword_bytes)  # 继续在子串中搜索
                    if not positions:
                        return f"未找到关键词（base64: {keyword}）"
                    result_str = f"找到 {len(positions)} 处匹配" + (f" (仅显示前{max_cnt}个)" if len(positions) >= max_cnt else "") + "：\n"
                    for i, byte_pos in enumerate(positions, 1):
                        result_str += f"{i}. 字节偏移 {byte_pos}\n"
                    return result_str
                else:
                    return f"错误：不支持的操作 '{operation}' for binary mode"
        else:  # text mode
            with open(file_path, "r", encoding=encoding) as f:
                content = f.read()
                lines = content.splitlines(keepends=True)
                char_count = len(content)
                line_count = len(lines)
                file_size = os.path.getsize(file_path)

                if operation == "size":
                    return f"文件大小：{file_size} 字节，字符数：{char_count}，行数：{line_count}"
                elif operation == "read_all":
                    return f"文件内容：\n{content}"
                elif operation == "read_chars":
                    if start_char is None:
                        return "错误：read_chars 需要 start_char 参数"
                    if start_char < 0 or start_char >= char_count:
                        return f"错误：start_char {start_char} 超出范围 [0, {char_count-1}]"
                    if num_chars is None:
                        result = content[start_char:]
                    else:
                        if num_chars < 0:
                            return "错误：num_chars 必须非负"
                        result = content[start_char:start_char+num_chars]
                    return f"读取字符：\n{result}"
                elif operation == "read_lines":
                    if line_numbers is None:
                        return "错误：read_lines 需要 line_numbers 参数"
                    line_nums = _parse_line_numbers(line_numbers)
                    if not line_nums:  # all lines
                        result = content
                    else:
                        selected = []
                        for ln in line_nums:
                            if 1 <= ln <= line_count:
                                selected.append(lines[ln-1])
                            else:
                                return f"错误：行号 {ln} 超出范围 [1, {line_count}]"
                        result = ''.join(selected)
                    return f"读取的行：\n{result}"
                elif operation == "search":
                    if keyword is None:
                        return "错误：search 操作需要 keyword 参数"
                    # 构建行起始偏移表（始终需要，用于行列转换）
                    line_starts = []
                    current_offset = 0
                    for line in lines:
                        line_starts.append(current_offset)
                        current_offset += len(line)

                    # 确定搜索范围：优先行范围，否则字符范围，否则全文件
                    target_lines_set = None
                    char_range = None
                    if line_numbers is not None:
                        # 解析行号
                        try:
                            line_nums = _parse_line_numbers(line_numbers)
                        except:
                            return "错误：line_numbers 格式无效"
                        target_lines_set = set(line_nums) if line_nums != [] else None  # [] 表示 "all"
                    elif start_char is not None:
                        # 字符范围
                        if start_char < 0 or start_char >= char_count:
                            return f"错误：start_char {start_char} 超出范围 [0, {char_count-1}]"
                        if num_chars is not None and num_chars < 0:
                            return "错误：num_chars 必须非负"
                        range_end = char_count if num_chars is None else min(start_char + num_chars, char_count)
                        char_range = (start_char, range_end)

                    # 准备搜索字符串（大小写处理）
                    if not case_sensitive:
                        search_content = content.lower()
                        search_keyword = keyword.lower()
                    else:
                        search_content = content
                        search_keyword = keyword

                    positions = []
                    pos = 0
                    max_cnt = max_matches if max_matches is not None else 100
                    while True:
                        found = search_content.find(search_keyword, pos)
                        if found == -1 or len(positions) >= max_cnt:
                            break
                        # 检查匹配是否在指定范围内
                        accept = False
                        if target_lines_set is not None:
                            # 计算所在行号
                            for idx, start_off in enumerate(line_starts):
                                next_start = line_starts[idx+1] if idx+1 < len(line_starts) else char_count
                                if start_off <= found < next_start:
                                    line_no = idx + 1
                                    break
                            else:
                                line_no = len(line_starts)  # 防呆
                            if target_lines_set is None or line_no in target_lines_set:
                                accept = True
                        elif char_range is not None:
                            if char_range[0] <= found < char_range[1]:
                                accept = True
                        else:
                            accept = True  # 无范围限制

                        if accept:
                            positions.append(found)
                        pos = found + len(search_keyword)  # 继续搜索

                    if not positions:
                        return f"未找到关键词 '{keyword}'"

                    # 转换为行列信息并构建结果
                    result_str = f"找到 {len(positions)} 处匹配" + (f" (仅显示前{max_cnt}个)" if len(positions) >= max_cnt else "") + "：\n"
                    for i, char_pos in enumerate(positions, 1):
                        # 定位行号
                        line_no = None
                        col_no = None
                        for idx, start_off in enumerate(line_starts):
                            next_start = line_starts[idx+1] if idx+1 < len(line_starts) else char_count
                            if start_off <= char_pos < next_start:
                                line_no = idx + 1
                                col_no = char_pos - start_off + 1
                                break
                        if line_no is None:
                            line_no = len(line_starts)
                            col_no = char_pos - line_starts[-1] + 1
                        result_str += f"{i}. 字符位置 {char_pos} (第{line_no}行，第{col_no}列)\n"
                    return result_str
                else:
                    return f"错误：不支持的操作 '{operation}' for text mode"
    except Exception as e:
        return f"读取文件时发生错误：{str(e)}"