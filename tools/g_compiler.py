#!/usr/bin/env python3
"""
tools/g_compiler.py
提供 gcc/g++ 编译功能，支持自定义编译选项。
当未指定输出路径时，可执行文件默认生成在源文件所在目录，名称为 a.out (Linux/macOS) 或 a.exe (Windows)。
"""

import subprocess
import shlex
import os
import platform
from typing import Optional

# 工具定义（OpenAI 格式）
tool_def = {
    "type": "function",
    "function": {
        "name": "g_compile",
        "description": "使用 gcc 或 g++ 编译 C/C++ 源文件，支持自定义编译选项。"
                       "若不指定输出路径，可执行文件默认生成在源文件目录，名称为 a.out (Linux/macOS) 或 a.exe (Windows)。",
        "parameters": {
            "type": "object",
            "properties": {
                "compiler": {
                    "type": "string",
                    "enum": ["gcc", "g++"],
                    "description": "编译器类型：gcc 用于 C，g++ 用于 C++"
                },
                "source": {
                    "type": "string",
                    "description": "源文件路径（可包含多个文件，用空格分隔）"
                },
                "output": {
                    "type": "string",
                    "description": "输出可执行文件路径（可选，若不指定则自动生成默认名称）"
                },
                "options": {
                    "type": "string",
                    "description": "额外的编译选项，如 '-O2 -Wall -lm'，注意用引号包围"
                },
                "timeout": {
                    "type": "integer",
                    "description": "编译超时时间（秒），默认 60",
                    "default": 60
                }
            },
            "required": ["compiler", "source"]
        }
    }
}

def execute(compiler: str, source: str, output: Optional[str] = None,
            options: Optional[str] = "", timeout: int = 60) -> str:
    """
    执行编译命令，返回编译输出（stdout + stderr）。
    """
    # 构建命令列表
    cmd = [compiler]
    if options:
        # 将选项字符串拆分成列表（安全处理引号）
        cmd.extend(shlex.split(options))

    # 处理默认输出路径
    if output is None:
        # 取源文件列表中的第一个文件作为参考目录
        first_source = source.split()[0] if source else ""
        if first_source:
            source_dir = os.path.dirname(first_source) or "."   # 若没有目录部分则为当前目录
        else:
            source_dir = "."
        # 根据操作系统确定默认可执行文件名
        if platform.system() == "Windows":
            default_exe = "a.exe"
        else:
            default_exe = "a.out"
        output = os.path.join(source_dir, default_exe)

    if output:
        cmd.extend(["-o", output])

    # 源文件（可能包含空格，需正确拆分）
    cmd.extend(shlex.split(source))

    try:
        # 执行编译，捕获输出
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8', # 强制使用UTF-8解码
            errors='replace', # 无法解码的字符替换
            timeout=timeout,
            check=False  # 不抛出异常，让调用者处理返回码
        )
        # 合并 stdout 和 stderr 作为结果
        output_text = result.stdout
        if result.stderr:
            if output_text:
                output_text += "\n" + result.stderr
            else:
                output_text = result.stderr
        if result.returncode != 0:
            output_text = f"Compilation failed (return code {result.returncode}):\n{output_text}"
        else:
            output_text = f"Compilation successful. Output: {output}\n" + output_text
        return output_text.strip() or "Compilation finished with no output."
    except subprocess.TimeoutExpired:
        return f"Compilation timed out after {timeout} seconds."
    except FileNotFoundError as e:
        return f"Compiler not found: {e}. Please ensure {compiler} is installed and in PATH."
    except Exception as e:
        return f"Unexpected error during compilation: {e}"