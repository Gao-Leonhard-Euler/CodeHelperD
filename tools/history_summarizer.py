#!/usr/bin/env python3
"""
tools/history_summarizer.py
生成或读取对话历史摘要。根据传入的会话标识（如时间戳或session_x），
检查对应的摘要文件（session_x.txt）是否存在，存在则直接返回内容；
否则读取聊天记录session_x.json，过滤后调用API生成摘要并保存。
"""

import os
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from openai import OpenAI

# 工具定义
tool_def = {
    "type": "function",
    "function": {
        "name": "history_summarize",
        "description": "获取或生成指定会话的摘要。传入会话标识（时间戳'YYYYMMDD_hhmmss'或文件前缀名'session_YYYYMMDD_hhmmss'）。"
                       "若摘要文件已存在则直接读取，否则从聊天记录生成并保存。",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "会话标识，时间戳'YYYYMMDD_hhmmss'或文件前缀名'session_YYYYMMDD_hhmmss'"
                }
            },
            "required": ["session_id"]
        }
    }
}

# 固定路径
MEMORY_DIR = Path(__file__).parent.parent / "memory"
HISTORY_CONFIG_FILE = Path(__file__).parent.parent / "history_config.json"

def _load_api_config() -> Dict[str, str]:
    """读取 history_config.json 中的API配置"""
    if not os.path.exists(HISTORY_CONFIG_FILE):
        raise RuntimeError(f"配置文件 {HISTORY_CONFIG_FILE} 不存在，请先运行 agent.py 生成。")
    with open(HISTORY_CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)
    required = ["api_key", "base_url", "model"]
    if not all(k in config for k in required):
        raise ValueError(f"配置文件 {HISTORY_CONFIG_FILE} 缺少必要字段 {required}")
    return config

def _normalize_session_id(session_id: str) -> str:
    """将输入标准化为纯时间戳（去掉前缀）"""
    if session_id.startswith("session_"):
        return session_id[8:]
    return session_id

def _format_message_for_summary(msg: Dict[str, Any]) -> Optional[str]:
    """将单条消息格式化为摘要用的文本，过滤掉 reasoning_content，工具消息只保留关键信息"""
    role = msg.get("role")
    if role == "user":
        return f"[用户:\n{msg.get('content', '')}]"
    elif role == "assistant":
        # 助手消息：若有 tool_calls 则视为工具调用，否则为普通回复
        if msg.get("tool_calls"):
            # 多个工具调用，每个单独一行
            lines = []
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "{}")
                lines.append(f"[工具:\n{name}({args})]")
            return "\n".join(lines)
        else:
            # 普通回复，忽略 reasoning_content
            content = msg.get('content', '')
            if content:
                return f"[助手:\n{content}]"
            return None
    elif role == "tool":
        # 工具结果
        content = msg.get('content', '')
        if content:
            return f"[结果:\n{content}]"
        return None
    elif role == "system":
        content = msg.get('content', '')
        if content:
            return f"[系统:\n{content}]"
        return None
    return None

def _build_summary_text(messages: List[Dict[str, Any]]) -> str:
    """将整个消息列表转换为适合摘要的纯文本格式"""
    lines = []
    for msg in messages:
        formatted = _format_message_for_summary(msg)
        if formatted:
            lines.append(formatted)
    return "\n".join(lines)

def _call_llm_to_summarize(text: str, config: Dict[str, str]) -> str:
    """调用API生成摘要"""
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"]
    )
    prompt = f"请对以下对话内容进行简洁的摘要，保留关键信息，如初始目的、重要操作、重要决策，忽略无关细节：\n\n{text}"
    try:
        response = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"生成摘要时API调用失败：{str(e)}"

def execute(session_id: str) -> str:
    """
    工具执行入口
    """
    # 标准化会话ID
    sess = _normalize_session_id(session_id)
    json_file = MEMORY_DIR / f"session_{sess}.json"
    summary_file = MEMORY_DIR / f"session_{sess}.txt"

    # 检查聊天记录是否存在
    if not json_file.exists():
        return f"聊天记录 session_{sess}.json 不存在，无法生成摘要。"

    # 如果摘要已存在，直接读取返回
    if summary_file.exists():
        with open(summary_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return f"摘要：\n{content}"

    # 否则生成新摘要
    # 1. 读取JSON
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception as e:
        return f"读取聊天记录失败：{str(e)}"

    # 2. 构建摘要文本
    summary_text = _build_summary_text(messages)

    # 3. 加载API配置
    try:
        api_config = _load_api_config()
    except Exception as e:
        return f"加载API配置失败：{str(e)}"

    # 4. 调用API生成摘要
    result = _call_llm_to_summarize(summary_text, api_config)

    # 5. 保存到文件
    try:
        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(result)
    except Exception as e:
        return f"摘要已生成但保存失败：{str(e)}\n\n摘要内容：\n{result}"

    return f"摘要：\n{result}"