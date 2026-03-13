#!/usr/bin/env python3
"""
tools/cmake_compiler.py
提供 CMake 配置和构建功能（cmake + 后续的构建命令，如 make）。
通常需要两步：cmake 生成构建系统，然后调用底层构建工具（如 make）。
本工具将这两个步骤合并，也可分别调用。
"""

import subprocess
import shlex
import os
from typing import Optional

tool_def = {
    "type": "function",
    "function": {
        "name": "cmake_build",
        "description": "使用 CMake 配置并构建项目（先运行 cmake，然后运行构建命令，默认是 make）",
        "parameters": {
            "type": "object",
            "properties": {
                "source_dir": {
                    "type": "string",
                    "description": "包含 CMakeLists.txt 的源目录"
                },
                "build_dir": {
                    "type": "string",
                    "description": "构建目录（存放生成的文件），默认为源目录下的 build 子目录",
                    "default": ""
                },
                "generator": {
                    "type": "string",
                    "description": "CMake 生成器，如 'Unix Makefiles'、'Ninja' 等，默认自动选择"
                },
                "cmake_options": {
                    "type": "string",
                    "description": "传递给 cmake 的额外选项，如 '-DCMAKE_BUILD_TYPE=Release'"
                },
                "build_target": {
                    "type": "string",
                    "description": "要构建的目标（传递给构建工具），默认不指定"
                },
                "build_args": {
                    "type": "string",
                    "description": "传递给构建工具（如 make）的额外参数，如 '-j4'"
                },
                "timeout": {
                    "type": "integer",
                    "description": "总构建超时时间（秒），默认 300",
                    "default": 300
                }
            },
            "required": ["source_dir"]
        }
    }
}

def execute(source_dir: str, build_dir: str = "", generator: Optional[str] = None,
            cmake_options: Optional[str] = "", build_target: Optional[str] = "",
            build_args: Optional[str] = "", timeout: int = 300) -> str:
    """
    执行 CMake 配置和构建，返回合并的输出。
    """
    # 确定构建目录
    if not build_dir:
        build_dir = os.path.join(source_dir, "build")
    os.makedirs(build_dir, exist_ok=True)

    # 检查源目录是否存在
    if not os.path.isdir(source_dir):
        return f"Error: Source directory '{source_dir}' does not exist."

    # ---- 第一步：cmake 配置 ----
    cmake_cmd = ["cmake", source_dir]
    if generator:
        cmake_cmd.extend(["-G", generator])
    if cmake_options:
        cmake_cmd.extend(shlex.split(cmake_options))

    try:
        # 运行 cmake
        result_cmake = subprocess.run(
            cmake_cmd,
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=timeout // 2,  # 分配一半时间给 cmake
            check=False
        )
        output = "=== CMake Output ===\n" + result_cmake.stdout
        if result_cmake.stderr:
            output += "\n" + result_cmake.stderr
        if result_cmake.returncode != 0:
            return f"CMake configuration failed (return code {result_cmake.returncode}):\n{output}"

        # ---- 第二步：构建 ----
        # 检测使用什么构建工具（基于生成器，但简单起见，假设 make 或 ninja）
        # 这里简化：直接调用 cmake --build
        build_cmd = ["cmake", "--build", "."]
        if build_target:
            build_cmd.extend(["--target", build_target])
        if build_args:
            # -- 之后传递参数给构建工具
            build_cmd.append("--")
            build_cmd.extend(shlex.split(build_args))

        result_build = subprocess.run(
            build_cmd,
            cwd=build_dir,
            capture_output=True,
            text=True,
            timeout=timeout // 2,
            check=False
        )
        output += "\n\n=== Build Output ===\n" + result_build.stdout
        if result_build.stderr:
            output += "\n" + result_build.stderr
        if result_build.returncode != 0:
            output = f"Build failed (return code {result_build.returncode}):\n{output}"
        return output.strip()

    except subprocess.TimeoutExpired:
        return f"CMake build timed out after {timeout} seconds."
    except FileNotFoundError:
        return "CMake command not found. Please ensure CMake is installed and in PATH."
    except Exception as e:
        return f"Unexpected error during CMake build: {e}"