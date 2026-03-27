#!/usr/bin/env python3
"""
tools/web_sockets.py
网络套接字工具：支持创建和管理TCP/UDP套接字，发送和接收数据。
维护套接字会话列表，支持多个并发套接字连接。
"""

import socket
import json
import time
from typing import Dict, Any, Optional, Tuple, List
import threading

# 全局套接字管理器
_sockets: Dict[str, Dict[str, Any]] = {}
_socket_lock = threading.Lock()  # 用于线程安全的锁
_next_socket_id = 1

def _generate_socket_id() -> str:
    """生成唯一的套接字ID"""
    global _next_socket_id
    with _socket_lock:
        socket_id = f"socket_{_next_socket_id}"
        _next_socket_id += 1
        return socket_id

def _get_socket_info(sock_id: str) -> Optional[Dict[str, Any]]:
    """获取套接字信息"""
    with _socket_lock:
        return _sockets.get(sock_id)

def _set_socket_info(sock_id: str, info: Dict[str, Any]) -> None:
    """设置套接字信息"""
    with _socket_lock:
        _sockets[sock_id] = info

def _remove_socket(sock_id: str) -> bool:
    """移除套接字"""
    with _socket_lock:
        if sock_id in _sockets:
            del _sockets[sock_id]
            return True
        return False

def _create_tcp_socket(host: str, port: int, timeout: Optional[float] = None) -> Tuple[socket.socket, str]:
    """创建TCP套接字并连接"""
    try:
        # 创建TCP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if timeout is not None:
            sock.settimeout(timeout)
        
        # 连接
        sock.connect((host, port))
        
        # 获取本地和远程地址
        local_addr = sock.getsockname()
        remote_addr = sock.getpeername()
        
        return sock, f"TCP socket connected to {remote_addr[0]}:{remote_addr[1]} (local: {local_addr[0]}:{local_addr[1]})"
    except Exception as e:
        raise Exception(f"TCP connection failed: {e}")

def _create_udp_socket(bind_host: str = "0.0.0.0", bind_port: int = 0, timeout: Optional[float] = None) -> Tuple[socket.socket, str]:
    """创建UDP套接字"""
    try:
        # 创建UDP套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if timeout is not None:
            sock.settimeout(timeout)
        
        # 绑定到指定地址
        sock.bind((bind_host, bind_port))
        
        # 获取本地地址
        local_addr = sock.getsockname()
        
        return sock, f"UDP socket bound to {local_addr[0]}:{local_addr[1]}"
    except Exception as e:
        raise Exception(f"UDP socket creation failed: {e}")

# 工具定义（OpenAI格式）
tool_def = {
    "type": "function",
    "function": {
        "name": "web_sockets",
        "description": "网络套接字工具：支持创建和管理TCP/UDP套接字，发送和接收数据。维护套接字会话列表，支持多个并发套接字连接。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "close", "send", "receive", "list", "info"],
                    "description": "操作类型：create-创建套接字；close-关闭套接字；send-发送数据；receive-接收数据；list-列出所有套接字；info-获取套接字详细信息",
                    "default": "create"
                },
                "socket_type": {
                    "type": "string",
                    "enum": ["tcp", "udp"],
                    "description": "套接字类型：tcp 或 udp（仅用于create操作）",
                    "default": "tcp"
                },
                "host": {
                    "type": "string",
                    "description": "目标主机地址（create TCP时用于连接，send UDP时指定目标）"
                },
                "port": {
                    "type": "integer",
                    "description": "端口号（create TCP时用于连接，send UDP时指定目标端口）",
                    "minimum": 1,
                    "maximum": 65535
                },
                "bind_host": {
                    "type": "string",
                    "description": "绑定主机地址（create UDP时指定绑定地址，默认0.0.0.0）",
                    "default": "0.0.0.0"
                },
                "bind_port": {
                    "type": "integer",
                    "description": "绑定端口（create UDP时指定绑定端口，默认0表示随机端口）",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 65535
                },
                "socket_id": {
                    "type": "string",
                    "description": "套接字ID（用于close、send、receive、info操作）"
                },
                "data": {
                    "type": "string",
                    "description": "要发送的数据（用于send操作）"
                },
                "timeout": {
                    "type": "number",
                    "description": "超时时间（秒），用于create、send、receive操作，默认10.0",
                    "default": 10.0,
                    "minimum": 0.1
                },
                "buffer_size": {
                    "type": "integer",
                    "description": "接收缓冲区大小（字节，用于receive操作）",
                    "default": 4096,
                    "minimum": 1,
                    "maximum": 65536
                },
                "encoding": {
                    "type": "string",
                    "description": "数据编码（用于send和receive操作），如'utf-8'(默认)、'ascii'、'binary'",
                    "default": "utf-8"
                }
            },
            "required": ["action"]
        }
    }
}

def execute(
    action: str = "create",
    socket_type: str = "tcp",
    host: Optional[str] = None,
    port: Optional[int] = None,
    bind_host: str = "0.0.0.0",
    bind_port: int = 0,
    socket_id: Optional[str] = None,
    data: Optional[str] = None,
    timeout: float = 10.0,
    buffer_size: int = 4096,
    encoding: str = "utf-8"
) -> str:
    """
    执行套接字操作
    """
    try:
        if action == "create":
            return _handle_create(socket_type, host, port, bind_host, bind_port, timeout)
        
        elif action == "close":
            return _handle_close(socket_id)
        
        elif action == "send":
            return _handle_send(socket_id, data, host, port, timeout, encoding)
        
        elif action == "receive":
            return _handle_receive(socket_id, timeout, buffer_size, encoding)
        
        elif action == "list":
            return _handle_list()
        
        elif action == "info":
            return _handle_info(socket_id)
        
        else:
            return f"错误：未知操作 '{action}'"
    
    except Exception as e:
        return f"操作失败：{str(e)}"

def _handle_create(socket_type: str, host: Optional[str], port: Optional[int], 
                   bind_host: str, bind_port: int, timeout: float) -> str:
    """处理创建套接字"""
    if socket_type == "tcp":
        if not host:
            return "错误：创建TCP套接字需要指定host参数"
        if not port:
            return "错误：创建TCP套接字需要指定port参数"
        
        # 创建TCP套接字
        sock, message = _create_tcp_socket(host, port, timeout)
        
        # 生成套接字ID
        sock_id = _generate_socket_id()
        
        # 保存套接字信息
        _set_socket_info(sock_id, {
            "socket": sock,
            "type": "tcp",
            "host": host,
            "port": port,
            "local_addr": sock.getsockname(),
            "remote_addr": sock.getpeername(),
            "created": time.time(),
            "timeout": timeout
        })
        
        return f"创建TCP套接字成功！\n套接字ID: {sock_id}\n{message}"
    
    elif socket_type == "udp":
        # 创建UDP套接字
        sock, message = _create_udp_socket(bind_host, bind_port, timeout)
        
        # 生成套接字ID
        sock_id = _generate_socket_id()
        
        # 获取本地地址
        local_addr = sock.getsockname()
        
        # 保存套接字信息
        _set_socket_info(sock_id, {
            "socket": sock,
            "type": "udp",
            "bind_host": bind_host,
            "bind_port": bind_port,
            "local_addr": local_addr,
            "created": time.time(),
            "timeout": timeout,
            "last_target": None  # 记录上次发送的目标地址
        })
        
        return f"创建UDP套接字成功！\n套接字ID: {sock_id}\n{message}"
    
    else:
        return f"错误：不支持的套接字类型 '{socket_type}'"

def _handle_close(socket_id: Optional[str]) -> str:
    """处理关闭套接字"""
    if not socket_id:
        return "错误：关闭套接字需要指定socket_id参数"
    
    sock_info = _get_socket_info(socket_id)
    if not sock_info:
        return f"错误：找不到套接字 '{socket_id}'"
    
    try:
        # 关闭套接字
        sock_info["socket"].close()
        _remove_socket(socket_id)
        return f"套接字 '{socket_id}' 已成功关闭"
    except Exception as e:
        return f"关闭套接字时出错：{str(e)}"

def _handle_send(socket_id: Optional[str], data: Optional[str], host: Optional[str], 
                port: Optional[int], timeout: float, encoding: str) -> str:
    """处理发送数据"""
    if not socket_id:
        return "错误：发送数据需要指定socket_id参数"
    
    if not data:
        return "错误：发送数据需要指定data参数"
    
    sock_info = _get_socket_info(socket_id)
    if not sock_info:
        return f"错误：找不到套接字 '{socket_id}'"
    
    sock = sock_info["socket"]
    sock_type = sock_info["type"]
    
    try:
        # 设置超时
        sock.settimeout(timeout)
        
        if sock_type == "tcp":
            # TCP发送
            if encoding == "binary":
                # 二进制模式
                data_bytes = data.encode('latin-1') if isinstance(data, str) else data.encode()
            else:
                # 文本模式
                data_bytes = data.encode(encoding)
            
            bytes_sent = sock.send(data_bytes)
            return f"TCP数据发送成功！\n发送字节数: {bytes_sent}\n数据长度: {len(data_bytes)}字节"
        
        elif sock_type == "udp":
            # UDP发送需要目标地址
            if not host or not port:
                # 检查是否有上次发送的目标地址
                if "last_target" in sock_info and sock_info["last_target"]:
                    host, port = sock_info["last_target"]
                else:
                    return "错误：UDP发送需要指定host和port参数"
            
            # 准备数据
            if encoding == "binary":
                data_bytes = data.encode('latin-1') if isinstance(data, str) else data.encode()
            else:
                data_bytes = data.encode(encoding)
            
            # 发送UDP数据包
            bytes_sent = sock.sendto(data_bytes, (host, port))
            
            # 保存目标地址供下次使用
            sock_info["last_target"] = (host, port)
            _set_socket_info(socket_id, sock_info)
            
            return f"UDP数据发送成功！\n目标: {host}:{port}\n发送字节数: {bytes_sent}\n数据长度: {len(data_bytes)}字节"
        
        else:
            return f"错误：不支持的套接字类型 '{sock_type}'"
    
    except socket.timeout:
        return f"发送超时（{timeout}秒）"
    except Exception as e:
        return f"发送数据时出错：{str(e)}"

def _handle_receive(socket_id: Optional[str], timeout: float, buffer_size: int, encoding: str) -> str:
    """处理接收数据"""
    if not socket_id:
        return "错误：接收数据需要指定socket_id参数"
    
    sock_info = _get_socket_info(socket_id)
    if not sock_info:
        return f"错误：找不到套接字 '{socket_id}'"
    
    sock = sock_info["socket"]
    sock_type = sock_info["type"]
    
    try:
        # 设置超时
        sock.settimeout(timeout)
        
        if sock_type == "tcp":
            # TCP接收
            data_bytes = sock.recv(buffer_size)
            if not data_bytes:
                return "TCP连接已关闭（收到空数据）"
            
            # 处理接收到的数据
            if encoding == "binary":
                # 二进制模式，返回十六进制表示
                data_hex = data_bytes.hex()
                data_str = f"[二进制数据，{len(data_bytes)}字节]\n十六进制: {data_hex}"
            else:
                # 文本模式
                try:
                    data_str = data_bytes.decode(encoding)
                except UnicodeDecodeError:
                    data_str = f"[无法用{encoding}解码的数据，{len(data_bytes)}字节]\n十六进制: {data_bytes.hex()}"
            
            return f"TCP数据接收成功！\n接收字节数: {len(data_bytes)}\n数据内容:\n{data_str}"
        
        elif sock_type == "udp":
            # UDP接收
            data_bytes, addr = sock.recvfrom(buffer_size)
            
            # 处理接收到的数据
            if encoding == "binary":
                data_hex = data_bytes.hex()
                data_str = f"[二进制数据，{len(data_bytes)}字节]\n十六进制: {data_hex}"
            else:
                try:
                    data_str = data_bytes.decode(encoding)
                except UnicodeDecodeError:
                    data_str = f"[无法用{encoding}解码的数据，{len(data_bytes)}字节]\n十六进制: {data_bytes.hex()}"
            
            # 保存来源地址供下次发送使用
            sock_info["last_target"] = (addr[0], addr[1])
            _set_socket_info(socket_id, sock_info)
            
            return f"UDP数据接收成功！\n来源: {addr[0]}:{addr[1]}\n接收字节数: {len(data_bytes)}\n数据内容:\n{data_str}"
        
        else:
            return f"错误：不支持的套接字类型 '{sock_type}'"
    
    except socket.timeout:
        return f"接收超时（{timeout}秒）"
    except Exception as e:
        return f"接收数据时出错：{str(e)}"

def _handle_list() -> str:
    """处理列出所有套接字"""
    with _socket_lock:
        if not _sockets:
            return "当前没有活动的套接字"
        
        result = f"活动套接字 ({len(_sockets)}个):\n"
        result += "-" * 50 + "\n"
        
        for sock_id, info in _sockets.items():
            sock_type = info.get("type", "unknown")
            created = info.get("created", 0)
            age = time.time() - created
            
            if sock_type == "tcp":
                local_addr = info.get("local_addr", ("?", 0))
                remote_addr = info.get("remote_addr", ("?", 0))
                result += f"ID: {sock_id} (TCP)\n"
                result += f"  连接: {local_addr[0]}:{local_addr[1]} -> {remote_addr[0]}:{remote_addr[1]}\n"
            elif sock_type == "udp":
                local_addr = info.get("local_addr", ("?", 0))
                result += f"ID: {sock_id} (UDP)\n"
                result += f"  绑定: {local_addr[0]}:{local_addr[1]}\n"
            
            result += f"  创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created))} ({age:.1f}秒前)\n"
            
            if "last_target" in info and info["last_target"]:
                host, port = info["last_target"]
                result += f"  最后目标: {host}:{port}\n"
            
            result += "\n"
        
        return result

def _handle_info(socket_id: Optional[str]) -> str:
    """处理获取套接字详细信息"""
    if not socket_id:
        return "错误：获取信息需要指定socket_id参数"
    
    sock_info = _get_socket_info(socket_id)
    if not sock_info:
        return f"错误：找不到套接字 '{socket_id}'"
    
    result = f"套接字信息: {socket_id}\n"
    result += "-" * 50 + "\n"
    
    sock_type = sock_info.get("type", "unknown")
    result += f"类型: {sock_type}\n"
    
    created = sock_info.get("created", 0)
    result += f"创建时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(created))}\n"
    
    if sock_type == "tcp":
        local_addr = sock_info.get("local_addr", ("?", 0))
        remote_addr = sock_info.get("remote_addr", ("?", 0))
        result += f"本地地址: {local_addr[0]}:{local_addr[1]}\n"
        result += f"远程地址: {remote_addr[0]}:{remote_addr[1]}\n"
        result += f"超时设置: {sock_info.get('timeout', '未设置')}秒\n"
    
    elif sock_type == "udp":
        local_addr = sock_info.get("local_addr", ("?", 0))
        bind_host = sock_info.get("bind_host", "0.0.0.0")
        bind_port = sock_info.get("bind_port", 0)
        result += f"绑定地址: {local_addr[0]}:{local_addr[1]}\n"
        result += f"绑定配置: {bind_host}:{bind_port}\n"
        result += f"超时设置: {sock_info.get('timeout', '未设置')}秒\n"
        
        if "last_target" in sock_info and sock_info["last_target"]:
            host, port = sock_info["last_target"]
            result += f"最后发送目标: {host}:{port}\n"
    
    # 套接字选项信息
    try:
        sock = sock_info["socket"]
        result += f"\n套接字选项:\n"
        result += f"  阻塞模式: {'非阻塞' if sock.getblocking() == 0 else '阻塞'}\n"
        result += f"  超时设置: {sock.gettimeout()}秒\n"
        
        if sock_type == "tcp":
            result += f"  TCP_NODELAY: {sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY)}\n"
    except:
        pass
    
    return result