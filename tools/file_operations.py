#!/usr/bin/env python3
"""
tools/file_operations.py
提供文件系统操作功能：列出目录内容、创建/删除文件/目录、复制/移动/重命名、压缩解压、查看文件详细信息。
支持 Windows 和 Linux 的路径差异。
"""

import os
import shutil
import stat
import time
import zipfile
import tarfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

# 工具定义
tool_def = {
    "type": "function",
    "function": {
        "name": "file_operations",
        "description": "执行文件系统操作：列出目录、创建/删除、复制/移动、重命名、压缩解压、查看信息、获取/修改工作目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "list",           # 列出目录内容
                        "mkdir",          # 创建目录
                        "touch",          # 创建空文件或更新修改时间
                        "remove",         # 删除文件或目录
                        "copy",           # 复制文件或目录
                        "move",           # 移动文件或目录
                        "rename",         # 重命名
                        "info",           # 查看文件/目录详细信息
                        "compress",       # 压缩文件/目录
                        "extract",        # 解压文件
                        "cd", "pwd"       # 修改和获取工作目录
                    ],
                    "description": "要执行的操作"
                },
                # 通用路径参数
                "path": {
                    "type": "string",
                    "description": "主要操作路径（源路径）"
                },
                "dest": {
                    "type": "string",
                    "description": "目标路径（用于复制、移动、重命名、压缩输出等）"
                },
                # list 操作特定参数
                "list_options": {
                    "type": "object",
                    "properties": {
                        "long": {
                            "type": "boolean",
                            "description": "是否显示详细信息",
                            "default": False
                        },
                        "recursive": {
                            "type": "boolean",
                            "description": "是否递归列出子目录",
                            "default": False
                        },
                        "all": {
                            "type": "boolean",
                            "description": "是否显示隐藏文件",
                            "default": False
                        }
                    },
                    "description": "list 操作的选项"
                },
                # remove 操作选项
                "recursive": {
                    "type": "boolean",
                    "description": "是否递归删除目录（用于 remove 操作）",
                    "default": False
                },
                # compress 操作选项
                "compress_format": {
                    "type": "string",
                    "enum": ["zip", "tar", "gztar", "bztar", "xztar"],
                    "description": "压缩格式（zip, tar, gztar, bztar, xztar）",
                    "default": "zip"
                }
            },
            "required": ["action"]
        }
    }
}

def _format_size(size_bytes: int) -> str:
    """将字节数转换为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"

def _get_file_info(file_path: Path, long_format: bool = False) -> str:
    """获取单个文件/目录的详细信息字符串"""
    stat_info = file_path.stat()
    size = stat_info.st_size
    mtime = datetime.fromtimestamp(stat_info.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    if long_format:
        mode_str = stat.filemode(stat_info.st_mode)
        return f"{mode_str} {stat_info.st_nlink:2d} {stat_info.st_uid} {stat_info.st_gid} {_format_size(size):>8} {mtime} {file_path.name}"
    else:
        return file_path.name

def _list_directory(path: Path, long: bool = False, recursive: bool = False, all: bool = False) -> str:
    """列出目录内容，支持递归和详细信息"""
    if not path.is_dir():
        return f"错误：{path} 不是一个目录"

    result_lines = []
    if recursive:
        # 递归列出所有子目录内容
        for root, dirs, files in os.walk(path):
            # 过滤隐藏文件（如果需要）
            if not all:
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                files = [f for f in files if not f.startswith('.')]
            root_path = Path(root)
            result_lines.append(f"\n{root_path}:")
            for name in dirs + files:
                full = root_path / name
                result_lines.append(_get_file_info(full, long))
    else:
        # 单层列出
        try:
            items = list(path.iterdir())
        except PermissionError:
            return f"错误：没有权限访问目录 {path}"
        if not all:
            items = [i for i in items if not i.name.startswith('.')]
        # 排序：目录在前，文件在后，按名称字母序
            items.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
        for item in items:
            result_lines.append(_get_file_info(item, long))
    return "\n".join(result_lines)

def _safe_remove(path: Path, recursive: bool = False) -> str:
    """安全删除文件或目录"""
    try:
        if path.is_file() or path.is_symlink():
            path.unlink()
            return f"已删除文件 {path}"
        elif path.is_dir():
            if recursive:
                shutil.rmtree(path)
                return f"已递归删除目录 {path}"
            else:
                # 尝试删除空目录
                path.rmdir()
                return f"已删除空目录 {path}"
        else:
            return f"错误：{path} 不是文件或目录"
    except OSError as e:
        return f"删除失败：{e}"

def execute(action: str, path: str = None, dest: Optional[str] = None,
            list_options: Optional[Dict[str, Any]] = None,
            recursive: bool = False,
            compress_format: str = "zip") -> str:
    """
    执行文件操作。
    """
    # 获取当前工作目录
    if action == "pwd":
        return f"当前工作目录：{os.getcwd()}"
    
    # 解析路径
    src_path = Path(path)
    dest_path = Path(dest) if dest else None

    # 处理 list 操作
    if action == "list":
        opts = list_options or {}
        long = opts.get("long", False)
        rec = opts.get("recursive", False)
        all_files = opts.get("all", False)
        if not src_path.exists():
            return f"错误：路径 {src_path} 不存在"
        return _list_directory(src_path, long, rec, all_files)

    # 创建目录
    elif action == "mkdir":
        try:
            src_path.mkdir(parents=True, exist_ok=True)
            return f"已创建目录 {src_path}"
        except Exception as e:
            return f"创建目录失败：{e}"

    # 创建空文件或更新修改时间
    elif action == "touch":
        try:
            src_path.touch(exist_ok=True)
            return f"已更新文件 {src_path}"
        except Exception as e:
            return f"创建文件失败：{e}"

    # 删除
    elif action == "remove":
        if not src_path.exists():
            return f"错误：路径 {src_path} 不存在"
        return _safe_remove(src_path, recursive)

    # 复制
    elif action == "copy":
        if not src_path.exists():
            return f"错误：源路径 {src_path} 不存在"
        if dest_path is None:
            return "错误：复制操作需要指定目标路径 dest"
        try:
            if src_path.is_dir():
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
                return f"已复制目录 {src_path} 到 {dest_path}"
            else:
                shutil.copy2(src_path, dest_path)
                return f"已复制文件 {src_path} 到 {dest_path}"
        except Exception as e:
            return f"复制失败：{e}"

    # 移动
    elif action == "move":
        if not src_path.exists():
            return f"错误：源路径 {src_path} 不存在"
        if dest_path is None:
            return "错误：移动操作需要指定目标路径 dest"
        try:
            shutil.move(str(src_path), str(dest_path))
            return f"已移动 {src_path} 到 {dest_path}"
        except Exception as e:
            return f"移动失败：{e}"

    # 重命名（与 move 类似，但要求在同一文件系统内）
    elif action == "rename":
        if not src_path.exists():
            return f"错误：源路径 {src_path} 不存在"
        if dest_path is None:
            return "错误：重命名操作需要指定新路径 dest"
        try:
            src_path.rename(dest_path)
            return f"已重命名 {src_path} 为 {dest_path}"
        except Exception as e:
            return f"重命名失败：{e}"

    # 查看详细信息
    elif action == "info":
        if not src_path.exists():
            return f"错误：路径 {src_path} 不存在"
        stat_info = src_path.stat()
        info_lines = [
            f"路径: {src_path.absolute()}",
            f"类型: {'目录' if src_path.is_dir() else '文件'}",
            f"大小: {_format_size(stat_info.st_size)} ({stat_info.st_size} 字节)",
            f"修改时间: {datetime.fromtimestamp(stat_info.st_mtime)}",
            f"访问时间: {datetime.fromtimestamp(stat_info.st_atime)}",
            f"创建时间: {datetime.fromtimestamp(stat_info.st_ctime)}",
            f"权限: {oct(stat_info.st_mode)[-3:]}",
            f"所有者 UID: {stat_info.st_uid}",
            f"组 GID: {stat_info.st_gid}",
        ]
        return "\n".join(info_lines)

    # 压缩
    elif action == "compress":
        if not src_path.exists():
            return f"错误：源路径 {src_path} 不存在"
        if dest_path is None:
            # 自动生成压缩文件名
            base_name = src_path.name
            if compress_format == "zip":
                dest_path = src_path.with_suffix(".zip")
            elif compress_format == "tar":
                dest_path = src_path.with_suffix(".tar")
            elif compress_format == "gztar":
                dest_path = src_path.with_suffix(".tar.gz")
            elif compress_format == "bztar":
                dest_path = src_path.with_suffix(".tar.bz2")
            elif compress_format == "xztar":
                dest_path = src_path.with_suffix(".tar.xz")
            else:
                return f"错误：不支持的压缩格式 {compress_format}"
        try:
            # shutil.make_archive 要求 base_name 不带扩展名
            if compress_format == "zip":
                shutil.make_archive(str(dest_path.with_suffix('')), 'zip', root_dir=src_path.parent, base_dir=src_path.name)
            else:
                # tar 格式
                shutil.make_archive(str(dest_path.with_suffix('')), compress_format, root_dir=src_path.parent, base_dir=src_path.name)
            return f"已压缩 {src_path} 到 {dest_path}"
        except Exception as e:
            return f"压缩失败：{e}"

    # 解压
    elif action == "extract":
        if not src_path.exists():
            return f"错误：压缩文件 {src_path} 不存在"
        if dest_path is None:
            dest_path = src_path.parent / src_path.stem  # 解压到同名目录
        try:
            if src_path.suffix == '.zip' or zipfile.is_zipfile(src_path):
                with zipfile.ZipFile(src_path, 'r') as zf:
                    zf.extractall(dest_path)
                return f"已解压 {src_path} 到 {dest_path}"
            elif tarfile.is_tarfile(src_path):
                with tarfile.open(src_path, 'r') as tf:
                    tf.extractall(dest_path)
                return f"已解压 {src_path} 到 {dest_path}"
            else:
                return f"错误：不支持的文件格式或不是有效的压缩文件 {src_path}"
        except Exception as e:
            return f"解压失败：{e}"
    
    # 修改当前工作目录
    elif action == "cd":
        if not src_path.exists():
            return f"错误：路径 {src_path} 不存在"
        if not src_path.is_dir():
            return f"错误：{src_path} 不是目录"
        try:
            os.chdir(str(src_path))
            return f"已切换到目录：{os.getcwd()}"
        except PermissionError:
            return f"错误：没有权限进入目录 {src_path}"
        except Exception as e:
            return f"切换目录失败：{e}"
    
    else:
        return f"错误：未知操作 '{action}'"