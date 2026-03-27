#!/usr/bin/env python3
"""
tools/__init__.py
动态加载所有工具模块，并编译 C++ 高性能工具（如果存在）。
"""

import os
import sys
import subprocess
import importlib
import pkgutil
import platform
from typing import List, Dict, Any, Callable

# ==================== 编译 C++ 工具 ====================

def _compile_cpp_tools():
    """扫描 tools/utils/cpp_bridge/ 下的 .cpp 文件，用 g++ -O3 编译为可执行文件。"""
    cpp_dir = os.path.join(os.path.dirname(__file__), 'utils', 'cpp_bridge')
    if not os.path.isdir(cpp_dir):
        return

    # 检查 g++ 是否可用
    try:
        subprocess.run(['g++', '--version'], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Warning: g++ not found. C++ tools will not be compiled.", file=sys.stderr)
        return

    # 确定可执行文件后缀（Windows 需 .exe）
    exe_suffix = '.exe' if platform.system() == 'Windows' else ''

    for fname in os.listdir(cpp_dir):
        if not fname.endswith('.cpp'):
            continue
        src = os.path.join(cpp_dir, fname)
        base = fname[:-4]  # 去掉 .cpp
        out = os.path.join(cpp_dir, base + exe_suffix)

        # 若已编译且源文件未更新，则跳过
        if os.path.exists(out) and os.path.getmtime(out) >= os.path.getmtime(src):
            continue

        cmd = ['g++', '-O3', '-std=c++17', '-o', out, src]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print(f"Compiled {fname} -> {os.path.basename(out)}")
            if result.stderr:
                print(f"  compiler warnings: {result.stderr.strip()}")
        except subprocess.CalledProcessError as e:
            print(f"Failed to compile {fname}: {e.stderr}", file=sys.stderr)

# 启动时立即编译
_compile_cpp_tools()

# ==================== 动态加载工具模块 ====================

# 存储工具定义和调用函数的全局变量
_tools: List[Dict[str, Any]] = []          # OpenAI 格式的工具列表
_tool_map: Dict[str, Callable] = {}        # 名称到执行函数的映射

def _load_tools():
    """遍历当前包目录，导入每个非隐藏模块，并提取 tool_def 和 execute 函数。"""
    global _tools, _tool_map
    package_dir = os.path.dirname(__file__)

    for importer, modname, ispkg in pkgutil.iter_modules([package_dir]):
        # 跳过 __init__ 和以下划线开头的模块（内部模块）
        if modname == "__init__" or modname.startswith("_"):
            continue

        full_modname = f"tools.{modname}"
        try:
            module = importlib.import_module(full_modname)
        except Exception as e:
            print(f"Warning: Failed to import module {full_modname}: {e}", file=sys.stderr)
            continue

        # 检查模块是否提供了工具定义和执行函数
        if not (hasattr(module, "tool_def") and hasattr(module, "execute")):
            # 不是工具模块，跳过
            continue

        tool_def = module.tool_def
        func_name = tool_def.get("function", {}).get("name")
        if not func_name:
            print(f"Warning: Module {modname} has tool_def but missing function name", file=sys.stderr)
            continue

        _tools.append(tool_def)
        _tool_map[func_name] = module.execute

# 执行加载
_load_tools()

# ==================== 导出接口 ====================

def get_tools() -> List[Dict[str, Any]]:
    """返回所有工具定义的列表（OpenAI 格式）。"""
    return _tools.copy()   # 返回副本，避免外部修改

def call_tool(name: str, args: Dict[str, Any]) -> str:
    """
    调用指定名称的工具，传入参数字典，返回字符串结果。
    若工具不存在，抛出 ValueError。
    """
    if name not in _tool_map:
        raise ValueError(f"Tool '{name}' not found. Available: {list(_tool_map.keys())}")
    # 执行函数，预期返回可转换为字符串的结果
    result = _tool_map[name](**args)
    # 确保返回字符串（工具函数可能返回其他类型）
    if not isinstance(result, str):
        result = str(result)
    return result

# 可选：打印已加载的工具列表
if __name__ == "__main__":
    print("Loaded tools:", list(_tool_map.keys()))

def refresh_tools():
    """重新加载所有工具模块，更新工具列表和映射"""
    global _tools, _tool_map
    _tools.clear()
    _tool_map.clear()
    _load_tools()