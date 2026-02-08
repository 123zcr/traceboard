[English](README.md) | **中文** | [日本語](README_ja.md)

# TraceBoard

**本地优先的 AI Agent 可观测性与调试工具包。**

TraceBoard 是 Agent 追踪领域的 *SQLite* —— 零配置、完全本地、即装即用。无需云账号、无需 Docker、无需外部数据库。只需 `pip install` 即可开始。

---

## 特性

- **零配置** —— `pip install traceboard` + 2 行代码
- **本地优先** —— 所有数据存储在本地 SQLite 文件中，零隐私风险
- **内置 Web 仪表盘** —— `traceboard ui` 打开交互式追踪查看器
- **OpenAI Agents SDK** —— 通过 `TracingProcessor` 接口原生集成
- **成本追踪** —— 自动按模型计算费用（GPT-4o、o1、o3、GPT-4.1 等）
- **实时更新** —— WebSocket 驱动的实时视图，支持 HTTP 轮询回退
- **数据导出** —— 支持导出为 JSON 或 CSV 格式进行离线分析
- **离线可用** —— 无需任何网络连接

## 快速开始

### 安装

```bash
pip install traceboard
```

### 集成（仅需 2 行代码）

```python
import traceboard
traceboard.init()

# 你现有的 OpenAI Agents SDK 代码 —— 无需任何修改
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="你是一个有用的助手。")
result = Runner.run_sync(agent, "你好！")
print(result.final_output)
```

### 查看追踪数据

```bash
traceboard ui
```

这将在 `http://localhost:8745` 打开本地 Web 仪表盘，你可以：

- 浏览所有已追踪的 Agent 运行记录
- 可视化执行时间线（甘特图风格）
- 检查 LLM 提示词/响应、工具调用和切换
- 追踪每个模型的 Token 用量和费用
- 实时查看聚合指标

## 工作原理

```
┌────────────────────┐       ┌───────────────┐       ┌──────────────────┐
│   你的 Agent 代码   │       │   SQLite DB   │       │   Web 仪表盘     │
│                    │       │               │       │                  │
│  traceboard.init() │──────>│ traceboard.db │<──────│  traceboard ui   │
│  Agent.run(...)    │  写入  │               │  读取  │  localhost:8745  │
└────────────────────┘       └───────────────┘       └──────────────────┘
```

TraceBoard 实现了 OpenAI Agents SDK 的 `TracingProcessor` 接口。当你调用 `traceboard.init()` 时，它会注册一个自定义处理器，捕获所有的追踪和跨度（LLM 调用、工具调用、切换、护栏），并将它们写入本地 SQLite 数据库。

Web 仪表盘从同一个 SQLite 文件读取数据，并通过交互式 UI 呈现。当 WebSocket 连接可用时，仪表盘会接收近实时更新（约 1 秒延迟）；否则回退到 HTTP 轮询。

## CLI 命令

```bash
traceboard ui                        # 启动 Web 仪表盘（默认: http://localhost:8745）
traceboard ui --port 9000            # 自定义端口
traceboard ui --no-open              # 不自动打开浏览器

traceboard export                    # 导出所有追踪为 JSON（输出到终端）
traceboard export -o traces.json     # 导出到文件
traceboard export -f csv -o data.csv # 导出为 CSV（追踪 + 跨度文件）
traceboard export --pretty           # 格式化 JSON 输出

traceboard clean                     # 删除所有追踪数据
```

## 配置

```python
import traceboard

traceboard.init(
    db_path="./my_traces.db",   # 自定义数据库路径（默认: ./traceboard.db）
    auto_open=False,             # 初始化时不自动打开浏览器
)
```

## 编程式导出

```python
from traceboard import TraceExporter

exporter = TraceExporter("./traceboard.db")

# 导出所有追踪为 JSON 文件
data = exporter.export_json("traces.json")

# 导出特定追踪为 CSV
exporter.export_csv("output.csv", trace_ids=["trace_abc123"])

# 获取内存中的数据（不写入文件）
data = exporter.export_json()
print(f"已导出 {data['trace_count']} 条追踪")
```

## 支持的模型（费用追踪）

TraceBoard 自动计算以下模型的费用：

| 模型系列 | 模型 |
|---|---|
| GPT-4o | `gpt-4o`、`gpt-4o-mini` |
| GPT-4.1 | `gpt-4.1`、`gpt-4.1-mini`、`gpt-4.1-nano` |
| o 系列 | `o1`、`o1-mini`、`o3`、`o3-mini`、`o4-mini` |
| GPT-4 Turbo | `gpt-4-turbo` |
| GPT-4 | `gpt-4` |
| GPT-3.5 | `gpt-3.5-turbo` |

未知模型默认使用 GPT-4o 的定价。定价数据随每个版本发布更新。

## 开发

```bash
# 克隆并以开发模式安装
git clone https://github.com/123zcr/traceboard.git
cd traceboard
pip install -e ".[dev]"

# 运行测试
pytest

# 以开发模式启动仪表盘
traceboard ui --no-open
```

## 贡献

欢迎贡献！请按以下步骤操作：

1. Fork 本仓库
2. 创建功能分支（`git checkout -b feature/my-feature`）
3. 提交你的修改并添加测试
4. 运行 `pytest` 确保所有测试通过
5. 提交 Pull Request

## 环境要求

- Python >= 3.10
- OpenAI Agents SDK（`openai-agents`）

## 许可证

[MIT](LICENSE)
