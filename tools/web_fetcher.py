#!/usr/bin/env python3
"""
tools/web_fetcher.py
网页抓取工具：支持使用urllib保存网页HTML，使用requests发送HTTP/HTTPS请求。
"""

import os
import sys
import json
import time
from typing import Optional, Dict, Any, Union
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import ssl

# 检查requests是否可用
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

# 工具定义（OpenAI格式）
tool_def = {
    "type": "function",
    "function": {
        "name": "web_fetcher",
        "description": "网页抓取工具：支持使用urllib保存网页HTML到本地文件，使用requests库发送HTTP/HTTPS请求，支持GET/POST等方法和自定义请求头。",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["save", "request", "get", "post", "info"],
                    "description": "操作类型：save-保存网页HTML到文件；request-发送HTTP/HTTPS请求；get-发送GET请求；post-发送POST请求；info-获取工具信息。",
                    "default": "request"
                },
                "url": {
                    "type": "string",
                    "description": "目标URL地址（必需）"
                },
                "method": {
                    "type": "string",
                    "description": "HTTP方法（用于request操作），如GET、POST、PUT、DELETE",
                    "default": "GET"
                },
                "headers": {
                    "type": "string",
                    "description": "HTTP请求头，JSON格式字符串，如 '{\"User-Agent\": \"Mozilla/5.0\", \"Accept\": \"application/json\"}'"
                },
                "data": {
                    "type": "string",
                    "description": "请求数据，对于POST/PUT等方法（表单数据或JSON字符串）"
                },
                "output": {
                    "type": "string",
                    "description": "输出文件路径（用于save操作），保存网页HTML内容"
                },
                "timeout": {
                    "type": "number",
                    "description": "请求超时时间（秒），默认30秒",
                    "default": 30.0,
                    "minimum": 1.0
                },
                "verify_ssl": {
                    "type": "boolean",
                    "description": "是否验证SSL证书（仅requests），默认True",
                    "default": True
                },
                "encoding": {
                    "type": "string",
                    "description": "响应编码（用于save操作），默认自动检测",
                    "default": "auto"
                },
                "json_data": {
                    "type": "boolean",
                    "description": "是否将data参数作为JSON发送（仅requests），默认False",
                    "default": False
                },
                "follow_redirects": {
                    "type": "boolean",
                    "description": "是否跟随重定向（仅requests），默认True",
                    "default": True
                }
            },
            "required": ["url"]
        }
    }
}

def execute(
    url: str,
    action: str = "request",
    method: str = "GET",
    headers: Optional[str] = None,
    data: Optional[str] = None,
    output: Optional[str] = None,
    timeout: float = 30.0,
    verify_ssl: bool = True,
    encoding: str = "auto",
    json_data: bool = False,
    follow_redirects: bool = True
) -> str:
    """
    执行网页抓取操作
    """
    try:
        if action == "save":
            return _save_with_urllib(url, output, timeout, encoding, headers)
        elif action == "request":
            return _request_with_requests(url, method, headers, data, timeout, verify_ssl, json_data, follow_redirects)
        elif action == "get":
            return _request_with_requests(url, "GET", headers, data, timeout, verify_ssl, json_data, follow_redirects)
        elif action == "post":
            return _request_with_requests(url, "POST", headers, data, timeout, verify_ssl, json_data, follow_redirects)
        elif action == "info":
            return _get_tool_info()
        else:
            return f"错误：未知操作 '{action}'"
    except Exception as e:
        return f"操作失败：{str(e)}"

def _save_with_urllib(url: str, output_path: Optional[str], timeout: float, encoding: str, headers_str: Optional[str]) -> str:
    """
    使用urllib保存网页HTML到文件
    """
    # 解析请求头
    req_headers = {}
    if headers_str:
        try:
            req_headers = json.loads(headers_str)
        except json.JSONDecodeError as e:
            return f"错误：请求头格式无效（必须是JSON）：{e}"
    
    # 创建请求对象
    req = Request(url, headers=req_headers)
    
    # 创建SSL上下文（用于HTTPS）
    ssl_context = ssl.create_default_context()
    
    try:
        # 打开URL
        response = urlopen(req, timeout=timeout, context=ssl_context)
        
        # 读取内容
        content = response.read()
        
        # 检测编码
        if encoding == "auto":
            # 尝试从Content-Type头获取编码
            content_type = response.headers.get('Content-Type', '')
            if 'charset=' in content_type:
                charset = content_type.split('charset=')[-1].split(';')[0].strip()
                try:
                    html_content = content.decode(charset)
                except (UnicodeDecodeError, LookupError):
                    # 如果指定的编码失败，尝试常见编码
                    html_content = _decode_with_fallback(content)
            else:
                # 没有指定编码，尝试检测
                html_content = _decode_with_fallback(content)
        else:
            # 使用指定编码
            try:
                html_content = content.decode(encoding)
            except (UnicodeDecodeError, LookupError) as e:
                return f"错误：无法使用编码 '{encoding}' 解码内容：{e}"
        
        # 如果没有指定输出路径，生成默认文件名
        if not output_path:
            # 从URL生成文件名
            import re
            filename = re.sub(r'[^\w\-_.]', '_', url)
            if len(filename) > 100:
                filename = filename[:100]
            filename += ".html"
            output_path = filename
        
        # 确保目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        # 保存到文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # 获取响应信息
        info = response.info()
        content_length = len(content)
        
        result = f"网页保存成功！\n"
        result += f"URL: {url}\n"
        result += f"保存到: {os.path.abspath(output_path)}\n"
        result += f"文件大小: {content_length} 字节\n"
        result += f"HTTP状态码: {response.status}\n"
        result += f"Content-Type: {info.get('Content-Type', '未知')}\n"
        
        return result
        
    except HTTPError as e:
        return f"HTTP错误 {e.code}: {e.reason}\nURL: {url}"
    except URLError as e:
        return f"URL错误: {e.reason}\nURL: {url}"
    except TimeoutError:
        return f"请求超时（{timeout}秒）\nURL: {url}"
    except Exception as e:
        return f"保存网页时出错：{str(e)}\nURL: {url}"

def _request_with_requests(
    url: str, 
    method: str, 
    headers_str: Optional[str], 
    data_str: Optional[str], 
    timeout: float, 
    verify_ssl: bool,
    json_data: bool,
    follow_redirects: bool
) -> str:
    """
    使用requests发送HTTP/HTTPS请求
    """
    if not REQUESTS_AVAILABLE:
        return "错误：requests库不可用。请安装requests库：pip install requests"
    
    # 解析请求头
    headers = {}
    if headers_str:
        try:
            headers = json.loads(headers_str)
        except json.JSONDecodeError as e:
            return f"错误：请求头格式无效（必须是JSON）：{e}"
    
    # 准备请求数据
    request_data = None
    if data_str:
        if json_data:
            try:
                request_data = json.loads(data_str)
                # 如果是JSON数据，设置Content-Type头
                if 'Content-Type' not in headers:
                    headers['Content-Type'] = 'application/json'
            except json.JSONDecodeError as e:
                return f"错误：data参数不是有效的JSON：{e}"
        else:
            request_data = data_str
    
    # 记录开始时间
    start_time = time.time()
    
    try:
        # 发送请求
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers,
            data=None if json_data and isinstance(request_data, dict) else request_data,
            json=request_data if json_data and isinstance(request_data, dict) else None,
            timeout=timeout,
            verify=verify_ssl,
            allow_redirects=follow_redirects
        )
        
        # 计算请求耗时
        elapsed_time = time.time() - start_time
        
        # 构建结果
        result = f"请求成功！\n"
        result += f"URL: {url}\n"
        result += f"方法: {method.upper()}\n"
        result += f"状态码: {response.status_code} {response.reason}\n"
        result += f"耗时: {elapsed_time:.2f}秒\n"
        result += f"响应大小: {len(response.content)} 字节\n\n"
        
        # 响应头
        result += "响应头:\n"
        for key, value in response.headers.items():
            result += f"  {key}: {value}\n"
        
        # 响应内容（预览）
        result += f"\n响应内容（预览前2000字符）:\n"
        content_type = response.headers.get('Content-Type', '').lower()
        
        if 'application/json' in content_type:
            try:
                json_content = response.json()
                result += json.dumps(json_content, ensure_ascii=False, indent=2)
            except:
                result += response.text[:2000]
        elif 'text/' in content_type:
            result += response.text[:2000]
        else:
            result += f"[二进制内容，{len(response.content)}字节]"
            result += f"\n十六进制预览: {response.content[:100].hex()}"
        
        # 如果有重定向历史
        if response.history:
            result += f"\n\n重定向历史（{len(response.history)}次）:\n"
            for i, resp in enumerate(response.history):
                result += f"  {i+1}. {resp.status_code} {resp.reason}: {resp.url}\n"
        
        return result
        
    except requests.exceptions.Timeout:
        return f"请求超时（{timeout}秒）\nURL: {url}"
    except requests.exceptions.SSLError as e:
        return f"SSL错误：{str(e)}\n提示：可以设置 verify_ssl=false 跳过SSL验证"
    except requests.exceptions.ConnectionError as e:
        return f"连接错误：{str(e)}\nURL: {url}"
    except requests.exceptions.RequestException as e:
        return f"请求异常：{str(e)}\nURL: {url}"
    except Exception as e:
        return f"未知错误：{str(e)}\nURL: {url}"

def _decode_with_fallback(content: bytes) -> str:
    """
    尝试使用多种编码解码内容
    """
    encodings = ['utf-8', 'gbk', 'gb2312', 'big5', 'latin-1', 'iso-8859-1']
    
    for encoding in encodings:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    
    # 所有编码都失败，使用utf-8并忽略错误
    return content.decode('utf-8', errors='ignore')

def _get_tool_info() -> str:
    """
    获取工具信息
    """
    info = "网页抓取工具信息：\n"
    info += "=" * 50 + "\n"
    info += f"requests库可用: {REQUESTS_AVAILABLE}\n"
    info += f"urllib可用: True\n"
    info += f"Python版本: {sys.version.split()[0]}\n"
    
    if REQUESTS_AVAILABLE:
        info += f"requests版本: {requests.__version__}\n"
    
    info += "\n支持的操作：\n"
    info += "1. save - 使用urllib保存网页HTML到本地文件\n"
    info += "2. request - 使用requests发送HTTP/HTTPS请求（支持所有方法）\n"
    info += "3. get - 发送GET请求\n"
    info += "4. post - 发送POST请求\n"
    info += "5. info - 获取工具信息\n"
    
    info += "\n示例用法：\n"
    info += "- 保存网页: action='save', url='https://example.com', output='page.html'\n"
    info += "- GET请求: action='get', url='https://api.example.com/data'\n"
    info += "- POST请求: action='post', url='https://api.example.com/submit', data='key=value'\n"
    info += "- 自定义请求: action='request', url='https://api.example.com', method='PUT', headers='{\"Authorization\": \"Bearer token\"}'\n"
    
    return info