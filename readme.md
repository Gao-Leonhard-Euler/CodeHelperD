# CodeHelperD - 智能代码助手

CodeHelperD 是一个基于 API 的智能代码助手 Agent，它能够理解自然语言指令，并通过调用一系列内置工具来完成文件操作、代码编译、程序执行、调试、Python 环境管理、历史记录管理等任务。它支持多轮对话、工具调用和交互式程序交互，并能通过文件存储实现长期记忆。

## 功能特点

- **智能对话**：使用 LLM 大语言模型（支持 reasoning 模式）理解用户需求。
- **丰富的工具集**：
  - 文件读写（文本/二进制）
  - 文件系统操作（ls, mkdir, rm, cp, mv, 压缩解压等）
  - C/C++ 编译（gcc/g++、make、CMake）
  - 程序执行与交互（支持超时和会话管理）
  - GDB 调试
  - Python 代码执行（一次性运行或交互式解释器）
  - 长期关键信息管理
  - 历史记录搜索、统计、摘要
- **多行输入支持**：使用 `:send` 发送多行消息。
- **自动历史记录**：每次对话保存在 `memory/` 目录下，支持存档和清理。
- **Token 预警**：自动估算对话长度，超过阈值时提醒模型及时保存至本地，当对话长度超过限制时触发强制保存。
- **绝对路径**：基于项目根目录操作，不受工作目录改变影响。
- **交互式程序支持**：可启动 gdb、Python 解释器等交互式会话，并通过 Agent 转发用户输入。

## 安装与依赖

### 环境要求

- Python 3.8 或更高版本
- 操作系统：Windows / Linux（部分工具可能需要系统支持，如 gcc、gdb 等）

### 安装步骤

1. 克隆或下载本项目到本地。
2. 进入项目目录：

   ```bash
      cd CodeHelperD
   ```

3. 安装 Python 依赖：

   ```bash
      pip install -r requirements.txt
   ```

4. （可选）如果需要编译和调试 C++，请确保系统已安装 `gdb`, `gcc` 和 `g++`。

### 依赖列表

- `openai>=1.0.0`：调用 DeepSeek（或其它LLM模型） API
- `tiktoken>=0.5.0`：用于估算 token 数量
- `virtualenv>=20.0.0`: 用于创建和管理 python 虚拟环境
- `PyMuPDF>=1.23.0`: 用于读取 PDF 文件
- `openpyxl>=3.0.0`: 用于读取和编辑 xlsx 表格

## 配置说明

首次运行时会交互式引导输入以下配置，并自动保存到 `config.json` 和 `history_config.json`：

- **主配置** (`config.json`)：用于对话的 API Key、Base URL、模型（默认 `deepseek-reasoner`）。
- **历史摘要配置** (`history_config.json`)：用于生成摘要的 API 配置（可单独指定模型，建议使用普通模型以节省成本）。

你也可以手动创建或修改这些 JSON 文件。

## 使用方法

### 启动

```bash
python agent.py
```

### 交互命令

- 普通消息：直接输入内容，按回车发送单行；如需多行，输入第一行后按回车，后续行使用 `...` 提示符，最后单独一行输入 `:send` 发送。
- `:exit` 或 `:quit`：退出程序。
- `:clean`：删除所有会话历史文件并退出。

## 工具列表

所有工具均通过 Agent 自动调用，以下为当前已实现的部分工具及功能概览：

| 工具名称 | 功能描述 |
| ---------- | ---------- |
| `file_read` | 读取文件（文本/二进制），支持按字节、字符、行读取，获取文件大小等。 |
| `file_write` | 写入、插入、删除文件内容（文本/二进制）。 |
| `file_operations` | 文件系统操作：列出目录（支持 `-l`、`-r`）、创建目录/文件、删除、复制、移动、重命名、压缩解压、查看详细信息、cd/pwd。 |
| `g_compile` | 使用 gcc/g++ 编译 C/C++ 源文件，支持自定义选项。 |
| `make_build` | 运行 make 构建项目。 |
| `cmake_build` | 运行 CMake 配置并构建项目。 |
| `executor` | 执行可执行文件，支持交互式会话和超时控制。 |
| `python_executor` | 执行 Python 代码。 |
| `debugger` | 启动 gdb 调试会话，支持发送命令、关闭会话。 |
| `get_current_time` | 获取当前日期时间。 |
| `key_info_manage` | 管理长期记忆文件 `memory/key_info.txt`（读取、追加、替换、删除）。 |
| `history_summarize` | 生成或读取指定会话的摘要。 |
| `history_search` | 搜索聊天记录（按关键词、时间范围、角色等），统计消息条数，获取指定消息。 |
| `history_save` | 保存当前会话的历史记录到文件，并从内存中移除已保存的部分（由 Agent 自主决定）。 |
| `venv_manager` | 管理 Python 虚拟环境，支持在虚拟环境中执行代码。 |
| `python_pdb` | 使用 pdb 调试 Python 代码。 |
| `java_debugger` | 编译和调试 Java 代码。 |
| `read_pdf` | 读取 PDF 文件中的文本内容。 |
| `xlsx_edit` | 读取和编辑 xlsx 文件中的文本内容。 |

## 项目文件结构

```plaintext
CodeHelperD/
├── agent.py                       # 主程序入口
├── config.json                    # 主 API 配置
├── history_config.json            # 摘要专用 API 配置
├── prompt.txt                     # 可选的系统设定
├── MAX_TOKENS.txt                 # 模型最大 token 长度
├── memory/                        # 存储目录
│   ├── key_info.txt               # 长期关键信息
│   ├── last.json                  # 上次会话历史（加载）
│   ├── session_*.json             # 会话历史
│   ├── session_*.txt              # 会话摘要
├── ds_token_calucation/           # 由 deepseek 提供的计算分词工具，从 deepseek 官方 api 手册中下载并直接使用
│   ├── tokenizer_config.json
│   ├── tokenizer.json
├── tools/                         # 工具模块
│   ├── __init__.py                # 动态加载所有工具
│   ├── cmake_compiler.py
│   ├── date_time.py
│   ├── debugger.py
│   ├── executor.py
│   ├── file_operations.py
│   ├── file_read.py
│   ├── file_write.py
│   ├── g_compiler.py
│   ├── history_save.py
│   ├── history_searcher.py
│   ├── history_summarizer.py
│   ├── key_info_manager.py
│   ├── make_compiler.py
│   ├── python_executor.py
│   ├── python_pdb.py
│   ├── venv_manager.py
│   ├── java_debugger.py
│   ├── read_pdf.py
│   ├── xlsx_edit.py
│   └── utils/
│       └── cpp_bridge/            # C++ 实现的工具（可扩展）
└── requirements.txt               # Python 依赖
```

## 注意事项

1. **API Key**：请确保 API Key 有效且有足够的额度。
2. **系统工具依赖**：部分工具（如 gcc、gdb、make、cmake、python、java、javac、jdb）需要系统已安装相应程序，并加入 PATH。
3. **路径安全**：Agent 有读、写、执行文件的权限，可以考虑在更安全的环境下运行或监视 Agent 的行为。
4. **Token 计算**：使用 tiktoken 或各个模型官网提供的计算工具进行计算，使用不同模型可能需要修改 agent.py 中 count_tokens 的实现。（参考：[deepseek](https://api-docs.deepseek.com/zh-cn/quick_start/token_usage), [Kimi](https://platform.moonshot.cn/docs/api/estimate#%E8%AF%B7%E6%B1%82%E5%9C%B0%E5%9D%80), [GLM](https://docs.bigmodel.cn/api-reference/%E6%A8%A1%E5%9E%8B-api/%E6%96%87%E6%9C%AC%E5%88%86%E8%AF%8D%E5%99%A8)）
5. **Token 预警**：当对话长度超过 `MAX_TOKENS.txt` 中的 75% 的阈值时，Agent 会收到系统提示，可主动调用 `history_save` 存档旧消息；当对话长度超过 `MAX_TOKENS.txt` 中的阈值时，系统会强制存档旧消息。如果使用非 deepseekV3.2 模型，则可能需要修改此文件。
6. **并发限制**：当前为单线程设计，不支持同时处理多个用户请求。

## License

This project is licensed under the GNU General Public License v3.0. See the LICENSE file for details.
