#!/usr/bin/env python3
"""
tools/history_save.py
提供保存历史记录的工具，实际调用 agent.py 中的函数。
使用延迟导入避免循环依赖。
"""

tool_def = {
    "type": "function",
    "function": {
        "name": "history_save",
        "description": "保存当前会话的历史记录到文件，并从当前消息历史中移除已保存的部分。可以指定保留最近的消息条数。",
        "parameters": {
            "type": "object",
            "properties": {
                "keep_last": {
                    "type": "integer",
                    "description": "保留最近的消息条数，默认为0（只保留当前工具调用后的消息）",
                    "default": 0
                }
            },
            "required": []
        }
    }
}

def execute(keep_last: int = 0) -> str:
    """调用 agent 的保存函数（延迟导入）"""
    import importlib
    agent = importlib.import_module('agent')
    return agent.save_history_tool(keep_last)