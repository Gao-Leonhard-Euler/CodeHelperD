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
import locale

# 工具定义（OpenAI 格式）
tool_def = {
    "type": "function",
    "function": {
        "name": "g_compile",
        "description": "使用 gcc 或 g++ 编译 C/C++ 源文件，或获取编译器版本/帮助信息，支持自定义编译选项。"
                       "编译时，若不指定输出路径，可执行文件默认生成在源文件目录，名称为 a.out (Linux/macOS) 或 a.exe (Windows)。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["compile", "version", "help"],
                    "description": "操作类型：compile-编译；version-获取编译器版本；help-获取编译器帮助。默认为 compile。",
                    "default": "compile"
                },
                "compiler": {
                    "type": "string",
                    "enum": ["gcc", "g++"],
                    "description": "编译器类型：gcc/g++，默认 g++",
                    "default": "g++"
                },
                "source": {
                    "type": "string",
                    "description": "源文件路径（可包含多个文件，用空格分隔）"
                },
                "output": {
                    "type": "string",
                    "description": "输出可执行文件路径（可选，不指定则生成默认名称）"
                },
                "options": {
                    "type": "string",
                    "description": "额外的编译选项，如 '-O2 -Wall -lm'，用引号包围"
                },
                "timeout": {
                    "type": "integer",
                    "description": "编译超时时间（秒），默认 60",
                    "default": 60
                }
            },
            "required": []
        }
    }
}


def _decode_bytes(data: bytes) -> str:
    """尝试多种编码严格解码，成功则返回；全部失败则使用 UTF-8 并替换无法解析的字符"""
    if not data:
        return ""
    if isinstance(data, str):
        return data
    encodings = ['gb2312', 'gbk', locale.getpreferredencoding()]
    for enc in encodings:
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')

def execute(action: str = "compile", compiler: Optional[str] = "g++", source: Optional[str] = None,
            output: Optional[str] = None, options: Optional[str] = "", timeout: int = 60) -> str:
    """
    执行编译命令，返回编译输出（stdout + stderr）。
    """
    # 构建命令列表
    if action == "version":
        if not compiler:
            return "错误：help 操作需要提供 compiler (gcc 或 g++)。"
        try:
            result = subprocess.run([compiler, "--version"], capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            return output.strip() if result.returncode == 0 else f"获取版本失败：{output}"
        except FileNotFoundError:
            return f"错误：找不到 {compiler}。"
        except Exception as e:
            return f"执行出错：{e}"
    elif action == "help":
        if not compiler:
            return "错误：help 操作需要提供 compiler (gcc 或 g++)。"
        try:
            result = subprocess.run([compiler, "--help"], capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            return output.strip() if result.returncode == 0 else f"获取帮助失败：{output}"
        except FileNotFoundError:
            return f"错误：找不到 {compiler}。"
        except Exception as e:
            return f"执行出错：{e}"
    elif action == "compile":
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
                text=False,
                errors='replace',
                timeout=timeout,
                check=False,
            )
            output = _decode_bytes(result.stdout)
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
    else:
        return f"错误：未知操作 {action}。"