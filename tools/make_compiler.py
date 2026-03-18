#!/usr/bin/env python3
"""
tools/make_compiler.py
提供 make 命令的调用，支持指定目标、目录和额外选项。
"""

import subprocess
import shlex
import os
from typing import Optional

tool_def = {
    "type": "function",
    "function": {
        "name": "make_build",
        "description": "使用 make 构建项目或获取 make 版本和帮助，可指定目标、工作目录和额外选项",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["build", "version", "help"],
                    "description": "操作类型：build-构建；version-获取版本；help-获取帮助。默认为 build。",
                    "default": "build"
                },
                "target": {
                    "type": "string",
                    "description": "构建目标（如 all, clean, install），默认不指定调用默认目标"
                },
                "directory": {
                    "type": "string",
                    "description": "运行 make 的工作目录（包含 Makefile 的目录），默认当前目录",
                    "default": "."
                },
                "options": {
                    "type": "string",
                    "description": "额外的 make 选项，如 '-j4'，用引号包围"
                },
                "timeout": {
                    "type": "integer",
                    "description": "构建超时时间（秒），默认 120",
                    "default": 120
                }
            },
            "required": []
        }
    }
}

def execute(action: str = "build", target: Optional[str] = None, directory: str = ".",
            options: Optional[str] = "", timeout: int = 120) -> str:
    """
    执行 make 命令，返回输出。
    """
    if action == "version":
        try:
            result = subprocess.run(["make", "--version"], capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            return output.strip() if result.returncode == 0 else f"获取版本失败：{output}"
        except FileNotFoundError:
            return "错误：找不到 make 命令。"
        except Exception as e:
            return f"执行出错：{e}"
    elif action == "help":
        try:
            result = subprocess.run(["make", "--help"], capture_output=True, text=True, timeout=10, check=False)
            output = result.stdout + (result.stderr if result.stderr else "")
            return output.strip() if result.returncode == 0 else f"获取帮助失败：{output}"
        except FileNotFoundError:
            return "错误：找不到 make 命令。"
        except Exception as e:
            return f"执行出错：{e}"
    elif action == "build":
        cmd = ["make"]
        if options:
            cmd.extend(shlex.split(options))
        if target:
            cmd.append(target)

        # 检查工作目录是否存在
        if not os.path.isdir(directory):
            return f"Error: Directory '{directory}' does not exist."

        try:
            result = subprocess.run(
                cmd,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            output_text = result.stdout
            if result.stderr:
                if output_text:
                    output_text += "\n" + result.stderr
                else:
                    output_text = result.stderr
            if result.returncode != 0:
                output_text = f"Make failed (return code {result.returncode}):\n{output_text}"
            return output_text.strip() or "Make finished with no output."
        except subprocess.TimeoutExpired:
            return f"Make timed out after {timeout} seconds."
        except FileNotFoundError:
            return "Make command not found. Please ensure make is installed and in PATH."
        except Exception as e:
            return f"Unexpected error during make: {e}"
    else:
        return f"错误：未知操作 {action}。"