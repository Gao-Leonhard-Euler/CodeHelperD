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
        "description": "保存当前会话的历史记录到文件，并从当前消息历史中移除已保存的部分。可以指定保留的消息条数。",
        "parameters": {
            "type": "object",
            "properties": {
                "keep_last": {
                    "type": "integer",
                    "description": "保留最近的消息条数，默认为0（删除当前工具调用前的消息）",
                    "default": 0
                }
            },
            "required": []
        }
    }
}

def execute(keep_last: int = 0) -> str:
    """调用 agent 的保存函数（延迟导入）"""
    import importlib,sys
    main_module = sys.modules.get('__main__')
    if main_module is None:
        return "错误：无法获取主模块"
    if not hasattr(main_module, 'save_history_tool'):
        return "错误：主模块中没有 save_history_tool 函数"
    return main_module.save_history_tool(keep_last)