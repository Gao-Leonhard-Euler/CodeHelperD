#!/usr/bin/env python3
"""
tools/date_time.py
提供当前日期时间信息，支持多种格式。
"""

from datetime import datetime

tool_def = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "获取当前日期和时间。",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "enum": ["iso", "date", "time", "timestamp"],
                    "description": "返回格式：iso-完整ISO格式，date-仅日期YYYY-MM-DD，time-仅时间HH:MM:SS，timestamp-Unix时间戳",
                    "default": "iso"
                }
            },
            "required": []
        }
    }
}

def execute(format: str = "iso") -> str:
    """返回当前时间"""
    now = datetime.now()
    if format == "iso":
        return now.isoformat()
    elif format == "date":
        return now.strftime("%Y-%m-%d")
    elif format == "time":
        return now.strftime("%H:%M:%S")
    elif format == "timestamp":
        return str(int(now.timestamp()))
    else:
        return now.isoformat()  # fallback