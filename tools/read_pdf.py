#!/usr/bin/env python3
"""
tools/read_pdf.py
读取 PDF 文件并支持多种操作：
- extract_text: 提取文本内容
- get_page_count: 获取PDF总页数
- get_text_stats: 获取文字统计信息（页数、字符数、单词数）
"""

import sys
import traceback

tool_def = {
    "type": "function",
    "function": {
        "name": "read_pdf",
        "description": "读取 PDF 文件并执行指定操作。支持提取文本、获取页数、获取文字统计信息。如果 PDF 是扫描件且未经过 OCR，可能无法提取文本。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["extract_text", "get_page_count", "get_text_stats"],
                    "description": "操作类型：extract_text-提取文本内容；get_page_count-获取PDF页数；get_text_stats-获取页数、字符数、单词数统计"
                },
                "file_path": {
                    "type": "string",
                    "description": "要读取的 PDF 文件的完整路径，例如 '/home/user/docs/article.pdf'"
                },
                "max_pages": {
                    "type": "integer",
                    "description": "仅对 extract_text 有效：最多读取的页数（从第一页开始）。默认读取全部。",
                    "minimum": 1
                }
            },
            "required": ["action", "file_path"]
        }
    }
}


def execute(action: str, file_path: str, max_pages: int = None) -> str:
    """
    执行 PDF 操作。
    :param action: 操作类型
    :param file_path: PDF 文件路径
    :param max_pages: 最大读取页数（仅用于 extract_text）
    :return: 操作结果字符串
    """
    # 尝试导入 fitz（PyMuPDF）
    try:
        import fitz
    except ImportError:
        return "错误：未找到 PyMuPDF 库。"

    # 检查文件是否存在且可读
    try:
        with open(file_path, 'rb'):
            pass
    except FileNotFoundError:
        return f"错误：文件不存在 - {file_path}"
    except Exception as e:
        return f"错误：无法访问文件 - {e}"

    # 打开 PDF
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        return f"错误：无法打开 PDF 文件 - {e}"

    total_pages = len(doc)

    # 根据 action 分发
    if action == "get_page_count":
        doc.close()
        return f"PDF 总页数：{total_pages}"

    elif action == "get_text_stats":
        # 统计所有页的字符数和单词数
        char_count = 0
        word_count = 0
        for page_num in range(total_pages):
            page = doc.load_page(page_num)
            text = page.get_text()
            char_count += len(text)
            # 简单单词统计：按空白分割（粗略，适用于英文等）
            words = text.split()
            word_count += len(words)
        doc.close()
        return f"PDF 统计信息：页数 {total_pages}，字符数 {char_count}，单词数 {word_count}"

    elif action == "extract_text":
        # 确定要读取的页码范围
        if max_pages is not None:
            pages_to_read = min(max_pages, total_pages)
        else:
            pages_to_read = total_pages

        text_parts = []
        for page_num in range(pages_to_read):
            page = doc.load_page(page_num)
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)

        doc.close()

        if not text_parts:
            return "该 PDF 未包含可提取的文本（可能是扫描件或图片）。"

        return "\n".join(text_parts)

    else:
        doc.close()
        return f"错误：未知的操作类型 '{action}'，可用操作：extract_text, get_page_count, get_text_stats"