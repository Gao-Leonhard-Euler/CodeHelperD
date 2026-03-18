import os
import json
import sys
import time
import datetime
import traceback
import math
from pathlib import Path
from openai import OpenAI
from typing import List, Dict, Any, Optional
import tiktoken,transformers
history: List[Dict[str, Any]] = []

# ==================== 路径管理 ====================

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
MEMORY_DIR = os.path.join(BASE_DIR, "memory")
KEY_INFO_FILE = os.path.join(MEMORY_DIR, "key_info.txt")
HISTORY_CONFIG_FILE = os.path.join(BASE_DIR, "history_config.json")
PROMPT_FILE = os.path.join(BASE_DIR, "prompt.txt")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ==================== 配置管理 ====================

def load_config() -> Dict[str, Any]:
    """加载配置文件，若不存在或格式错误则交互式输入"""
    default_config = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-reasoner",
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            # 只检查必要字段
            required = ["api_key", "base_url", "model"]
            if all(k in config for k in required):
                return config
            else:
                print("配置文件缺少必要字段，将重新输入。")
        except Exception as e:
            print(f"配置文件读取失败: {e}，将重新输入。")
    # 交互式输入
    print("请输入 api 配置信息（直接回车使用默认值）：")
    api_key = input("API Key: ").strip()
    base_url = input("Base URL (默认: https://api.deepseek.com): ").strip() or default_config["base_url"]
    model = input("Model (默认: deepseek-reasoner): ").strip() or default_config["model"]
    config = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"配置已保存到 config.json")
    return config

# ==================== 历史摘要API配置管理 ====================

def load_history_config() -> Dict[str, Any]:
    """加载历史摘要专用的API配置文件，若不存在或格式错误则交互式输入"""
    default_config = {
        "api_key": "",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",  # 摘要可用普通模型，节省成本
    }
    if os.path.exists(HISTORY_CONFIG_FILE):
        try:
            with open(HISTORY_CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
            required = ["api_key", "base_url", "model"]
            if all(k in config for k in required):
                return config
            else:
                print("历史摘要配置文件缺少必要字段，将重新输入。")
        except Exception as e:
            print(f"历史摘要配置文件读取失败: {e}，将重新输入。")
    # 交互式输入
    print("请输入历史摘要专用的 api 配置信息（直接回车使用默认值）：")
    api_key = input("API Key: ").strip()
    base_url = input("Base URL (默认: https://api.deepseek.com): ").strip() or default_config["base_url"]
    model = input("Model (默认: deepseek-chat): ").strip() or default_config["model"]
    config = {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }
    with open(HISTORY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"历史摘要配置已保存到 {HISTORY_CONFIG_FILE}")
    return config

# ==================== 关键信息管理 ====================

def load_key_info() -> str:
    """加载关键信息文件内容，若不存在则创建空文件"""
    Path(MEMORY_DIR).mkdir(exist_ok=True)
    if not os.path.exists(KEY_INFO_FILE):
        with open(KEY_INFO_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return ""
    with open(KEY_INFO_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def load_prompt() -> str:
    """读取 prompt.txt 中的系统设定，若文件不存在则返回空字符串"""
    prompt_file = PROMPT_FILE
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

# ==================== Token 计数和长度预警 ====================

def read_max_tokens(lenfile: str = 'MAX_TOKENS.txt') -> int:
    """读取模型上下文最大 token 数"""
    try:
        with open(os.path.join(BASE_DIR, lenfile), 'r', encoding='utf-8') as f:
            return int(f.readline().strip())
    except FileNotFoundError:
        print(f"文件未找到: {lenfile}")
    except ValueError:
        print("无法将内容转换为数字")
    except Exception as e:
        print(f"发生错误: {e}")
    return 131072

# 全局 tokenizer 缓存
_ds_tokenizer = None
def ds_get_tokenizer():
    global _ds_tokenizer
    if _ds_tokenizer is None:
        ds_tokenizer_dir = os.path.join(BASE_DIR, "ds_token_calucation")
        if not os.path.exists(ds_tokenizer_dir):
            raise FileNotFoundError(f"Tokenizer directory not found: {ds_tokenizer_dir}")
        _ds_tokenizer = transformers.AutoTokenizer.from_pretrained(
            ds_tokenizer_dir,
            trust_remote_code=True
        )
    return _ds_tokenizer

def count_tokens_DS(messages: List[Dict[str, Any]]) -> int:
    """估算消息列表的 token 数"""
    tokenizer = ds_get_tokenizer()
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if content:
            total += len(tokenizer.encode(content, add_special_tokens=False))
        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            total += len(tokenizer.encode(reasoning, add_special_tokens=False))
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "")
                total += len(tokenizer.encode(name, add_special_tokens=False))
                total += len(tokenizer.encode(args, add_special_tokens=False))
    return total

def count_tokens_tik(messages: List[Dict[str, Any]], encode: str = "cl100k_base") -> int:
    """估算消息列表的 token 数"""
    encoding = tiktoken.get_encoding(encode)
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if content:
            total += len(encoding.encode(content))
        reasoning = msg.get("reasoning_content", "")
        if reasoning:
            total += len(encoding.encode(reasoning))
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "")
                total += len(encoding.encode(name))
                total += len(encoding.encode(args))
    return total

def count_tokens(messages: List[Dict[str, Any]]) -> int:
    return count_tokens_DS(messages)

# ==================== 历史记录保存工具 ====================
def save_history_tool(keep_last: int = 0) -> str:
    """
    将历史记录中除最近 keep_last 条之外的消息保存到文件，并从内存中移除。
    返回保存的文件名。
    """
    global history
    if keep_last < 0:
        keep_last = 0
    total = len(history)
    keep_last=keep_last+1
    if total <= keep_last:
        return "没有需要保存的消息"
    # 要保存的消息索引范围 [0, total-keep_last-1]
    save_count = total - keep_last
    if save_count<total and history[save_count]['role']=='tool':
        save_count=save_count-1
    to_save = history[:save_count]
    # 确保 memory 目录存在
    Path(MEMORY_DIR).mkdir(exist_ok=True)
    # 生成文件名
    filenowtime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"session_{filenowtime}.json"
    while os.path.exists(os.path.join(MEMORY_DIR, filename)):
        filenowtime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"session_{filenowtime}.json"
    with open(os.path.join(MEMORY_DIR, filename), "w", encoding="utf-8") as f:
        json.dump(to_save, f, indent=2, ensure_ascii=False)
    
    # 从 history 中移除已保存的消息
    history = history[save_count:]
    return f"已保存 {save_count} 条消息，时间戳 {filenowtime}"

def force_save(keep_last: int = 12) -> str:
    global history
    from tools import history_summarizer
    filenowtime=save_history_tool(keep_last=keep_last)
    text=history_summarizer.execute(filenowtime)
    return f'你之前的工作（已保存 {filenowtime}）摘要:\n\n{text}'

# ==================== 历史记录管理 ====================

def load_history(session_file: str) -> List[Dict[str, Any]]:
    """加载指定会话文件的历史消息（若存在且有效）"""
    if os.path.exists(session_file):
        try:
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"历史记录加载失败: {e}，将新建会话。")
    print(f"历史记录不存在，将新建会话。")
    return []

def save_history(session_file: str, messages: List[Dict[str, Any]]):
    """保存整个消息列表到会话文件（覆盖写入）"""
    Path(MEMORY_DIR).mkdir(exist_ok=True)
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)

# ==================== 工具加载 ====================

# 从 tools 包导入工具列表和调用函数
try:
    from tools import get_tools, call_tool
    tools_list = get_tools()
    print(f"已加载 {len(tools_list)} 个工具")
except ImportError as e:
    print(f"工具加载失败: {e}")
    print("请确保 tools 目录存在且包含 __init__.py")
    sys.exit(1)

# ==================== 消息读取 ====================

def get_multiline_input() -> str:
    """获取多行用户输入，以单独一行的 :send 结束；特殊命令（:exit/:quit/:clean）直接返回命令字符串"""
    lines = []
    while True:
        # 第一行提示符为 >>>，后续行提示符为 ...
        prompt_symbol = ">>> " if not lines else "... "
        line = input(prompt_symbol).rstrip("\n")
        if line.startswith(":"):
            cmd = line.lower()
            if cmd in (":exit", ":quit", ":clean"):
                return cmd          # 返回命令
            elif cmd == ":send":
                # 将累积的行合并为一条消息（用换行符连接）
                return "\n".join(lines)
            else:
                print(f"未知命令: {line}")
                continue
        else:
            lines.append(line)

# ==================== 主对话循环 ====================

def main():
    global history
    config = load_config()
    load_history_config()
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"]
    )

    TOKENS = int(read_max_tokens()-64)
    WARNING_TOKENS = int(math.floor(0.75*TOKENS)-64)
    ERROR_TOKENS = int(math.floor(0.875*TOKENS)-64)
    print(f'模型上下文长度：{TOKENS}；对话预警长度：{WARNING_TOKENS}')
    # 创建新会话文件
    history = load_history(os.path.join(MEMORY_DIR, 'last.json'))  # 通常为空，但若文件已存在则加载

    # 加载prompt
    prompt = load_prompt()
    if prompt:
        print("已加载系统设定。")

    print("\n智能代码助手 CodeHelperD 已启动。输入 ':exit' 或 ':quit' 退出，输入':clean'清除所有历史记录并退出，输入':send'发送消息。")

    while True:
        # 获取用户输入
        user_input_or_cmd = get_multiline_input()
        if user_input_or_cmd in (":exit", ":quit"):
            # 退出时保存当前会话所有历史消息到文件
            save_history(os.path.join(MEMORY_DIR, 'last.json'), history)
            print("再见！")
            break
        elif user_input_or_cmd == ":clean":
            # 删除 memory 下所有会话文件
            import glob
            for f in glob.glob(os.path.join(MEMORY_DIR, "session_*.json")):
                os.remove(f)
            for f in glob.glob(os.path.join(MEMORY_DIR, "session_*.txt")):
                os.remove(f)
            print("已清理所有聊天记录。再见！")
            break
        else:
            user_input = user_input_or_cmd   # 正常用户消息
        # 构建消息列表（关键信息 + 历史 + 当前用户输入）
        messages_for_api = []
        if prompt:
            messages_for_api.append({"role": "system", "content": prompt})
        key_info = load_key_info()
        if key_info:
            messages_for_api.append({"role": "system", "content": f"Key information:\n{key_info}"})
        messages_for_api.extend(history)
        messages_for_api.append({"role": "user", "content": user_input})
        history.append({"role": "user", "content": user_input})

        # 构建消息列表后，添加 token 检查
        current_tokens = count_tokens(messages_for_api)
        try_save = 12
        while current_tokens > TOKENS:
            save_result = force_save(try_save)
            try_save = try_save//2
            print(f"\n[触发强制保存]\n")
            # 重新构建 messages_for_api 以反映新的 history
            messages_for_api = []
            if prompt:
                messages_for_api.append({"role": "system", "content": prompt})
            key_info = load_key_info()
            if key_info:
                messages_for_api.append({"role": "system", "content": f"Key information:\n{key_info}"})
            if save_result:
                history.insert(0, {"role": "system", "content": save_result})
            messages_for_api.extend(history)
            current_tokens = count_tokens(messages_for_api)
        if current_tokens > ERROR_TOKENS:
            warning_msg = f"警告：对话长度严重过长({current_tokens}/{TOKENS})，尽快调用工具保存部分聊天记录到文件。"
            messages_for_api.append({"role": "system", "content": warning_msg})
        elif current_tokens > WARNING_TOKENS:
            warning_msg = f"警告：对话长度过长({current_tokens}/{TOKENS})，可调用工具保存部分聊天记录到文件。"
            messages_for_api.append({"role": "system", "content": warning_msg})

        # 工具调用循环
        turn_finished = False
        while not turn_finished:
            try:
                response = client.chat.completions.create(
                    model=config["model"],
                    messages=messages_for_api,
                    tools=tools_list if tools_list else None
                )
            except Exception as e:
                print(f"API 调用失败: {e}")
                traceback.print_exc()
                break

            choice = response.choices[0]
            assistant_message = choice.message

            # 将助手消息添加到内存历史（保留完整内容，包括 reasoning_content）
            msg_dict = {
                "role": "assistant",
                "content": assistant_message.content
            }
            if hasattr(assistant_message, "reasoning_content") and assistant_message.reasoning_content:
                msg_dict["reasoning_content"] = assistant_message.reasoning_content
            else:
                msg_dict["reasoning_content"] = ""
            if assistant_message.tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            history.append(msg_dict)

            # 输出助手回复（显示思考过程和最终内容）
            if msg_dict.get("reasoning_content"):
                print(f"\n[思考] {msg_dict['reasoning_content']}")
            if msg_dict.get("content"):
                print(f"\n[助手] {msg_dict['content']}")

            # 处理工具调用
            if assistant_message.tool_calls:
                for tool_call in assistant_message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        args = {}
                    print(f"\n[工具调用] {tool_name}({args})")

                    # 执行工具
                    try:
                        result = call_tool(tool_name, args)
                    except Exception as e:
                        result = f"工具执行出错: {e}"

                    print(f"[工具结果] {result}")

                    # 将工具结果加入历史
                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(result)
                    }
                    history.append(tool_message)

                # 重新构建 messages_for_api 以保证一致性
                messages_for_api = []
                if prompt:
                    messages_for_api.append({"role": "system", "content": prompt})
                key_info = load_key_info()
                if key_info:
                    messages_for_api.append({"role": "system", "content": f"Key information:\n{key_info}"})
                messages_for_api.extend(history)

                # 构建消息列表后，添加 token 检查
                current_tokens = count_tokens(messages_for_api)
                try_save = 12
                while current_tokens > TOKENS:
                    save_result = force_save(try_save)
                    try_save = try_save//2
                    print(f"\n[触发强制保存]\n")
                    # 重新构建 messages_for_api 以反映新的 history
                    messages_for_api = []
                    if prompt:
                        messages_for_api.append({"role": "system", "content": prompt})
                    key_info = load_key_info()
                    if key_info:
                        messages_for_api.append({"role": "system", "content": f"Key information:\n{key_info}"})
                    if save_result:
                        history.insert(0, {"role": "system", "content": save_result})
                    messages_for_api.extend(history)
                    current_tokens = count_tokens(messages_for_api)
                if current_tokens > ERROR_TOKENS:
                    warning_msg = f"警告：对话长度严重过长({current_tokens}/{TOKENS})，尽快调用工具保存部分聊天记录到文件。"
                    messages_for_api.append({"role": "system", "content": warning_msg})
                elif current_tokens > WARNING_TOKENS:
                    warning_msg = f"警告：对话长度过长({current_tokens}/{TOKENS})，可调用工具保存部分聊天记录到文件。"
                    messages_for_api.append({"role": "system", "content": warning_msg})
            else:
                turn_finished = True

        

if __name__ == "__main__":
    main()