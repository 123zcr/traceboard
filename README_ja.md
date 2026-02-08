[English](README.md) | [中文](README_zh.md) | **日本語**

# TraceBoard

**ローカルファーストの AI Agent オブザーバビリティ＆デバッグツールキット。**

TraceBoard は Agent トレーシングにおける *SQLite* です —— 設定不要、完全ローカル、即座にセットアップ。クラウドアカウント、Docker、外部データベースは一切不要。`pip install` するだけで始められます。

---

## 特徴

- **マルチ SDK** —— OpenAI Agents SDK、Anthropic、LangChain、LiteLLM をサポート
- **設定不要** —— `pip install traceboard[all]` + コード 2 行
- **ローカルファースト** —— 全データをローカルの SQLite ファイルに保存、プライバシーリスクゼロ
- **内蔵 Web ダッシュボード** —— `traceboard ui` でインタラクティブなトレースビューアを起動
- **コスト追跡** —— 6 プロバイダー、100 以上のモデルの自動コスト計算
- **リアルタイム更新** —— WebSocket によるライブビュー（HTTP ポーリングフォールバック付き）
- **データエクスポート** —— JSON または CSV 形式でオフライン分析用にエクスポート
- **オフライン動作** —— インターネット接続不要

## クイックスタート

### インストール

```bash
pip install traceboard[all]       # 全 SDK アダプター
pip install traceboard[openai]    # OpenAI Agents SDK のみ
pip install traceboard[anthropic] # Anthropic のみ
pip install traceboard[langchain] # LangChain のみ
pip install traceboard[litellm]   # LiteLLM のみ（100+ プロバイダー対応）
```

### OpenAI Agents SDK

```python
import traceboard
traceboard.init()

from agents import Agent, Runner
agent = Agent(name="Assistant", instructions="あなたは親切なアシスタントです。")
result = Runner.run_sync(agent, "こんにちは！")
```

### Anthropic Claude

```python
import traceboard
tracer = traceboard.init_anthropic()
client = tracer.instrument()

response = client.messages.create(
    model="claude-opus-4.6",
    max_tokens=1024,
    messages=[{"role": "user", "content": "こんにちは！"}]
)
```

### LangChain

```python
import traceboard
handler = traceboard.init_langchain()

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-5", callbacks=[handler])
response = llm.invoke("こんにちは！")
```

### LiteLLM（100+ プロバイダーを一括対応）

```python
import traceboard
traceboard.init()  # LiteLLM を自動検出

from litellm import completion
response = completion(model="gpt-5", messages=[{"role": "user", "content": "こんにちは！"}])
```

### 全インストール済み SDK の自動検出

```python
import traceboard
traceboard.init()  # インストール済みの全 SDK を自動検出・登録
```

### トレースを表示

```bash
traceboard ui
```

`http://localhost:8745` でローカル Web ダッシュボードが開き、以下が可能です：

- すべてのトレース済み Agent 実行を閲覧
- 実行タイムラインを可視化（ガントチャート形式）
- LLM プロンプト/レスポンス、ツール呼び出し、ハンドオフを検査
- モデルごとのトークン使用量とコストを追跡
- 集約メトリクスをリアルタイムで表示

## 仕組み

```
┌────────────────────┐       ┌───────────────┐       ┌──────────────────┐
│  Agent コード       │       │   SQLite DB   │       │  Web ダッシュボード │
│                    │       │               │       │                  │
│  traceboard.init() │──────>│ traceboard.db │<──────│  traceboard ui   │
│  Agent.run(...)    │ 書込   │               │  読取  │  localhost:8745  │
└────────────────────┘       └───────────────┘       └──────────────────┘
```

TraceBoard は OpenAI Agents SDK の `TracingProcessor` インターフェースを実装しています。`traceboard.init()` を呼び出すと、すべてのトレースとスパン（LLM 呼び出し、ツール呼び出し、ハンドオフ、ガードレール）をキャプチャするカスタムプロセッサが登録され、ローカルの SQLite データベースに書き込まれます。

Web ダッシュボードは同じ SQLite ファイルからデータを読み取り、インタラクティブな UI で表示します。WebSocket 接続が利用可能な場合、ダッシュボードはほぼリアルタイムの更新（約 1 秒の遅延）を受信します。それ以外の場合は HTTP ポーリングにフォールバックします。

## CLI コマンド

```bash
traceboard ui                        # Web ダッシュボードを起動（デフォルト: http://localhost:8745）
traceboard ui --port 9000            # カスタムポート
traceboard ui --no-open              # ブラウザを自動で開かない

traceboard export                    # 全トレースを JSON でエクスポート（標準出力）
traceboard export -o traces.json     # ファイルにエクスポート
traceboard export -f csv -o data.csv # CSV でエクスポート（トレース + スパンファイル）
traceboard export --pretty           # JSON を整形出力

traceboard clean                     # 全トレースデータを削除
```

## 設定

```python
import traceboard

traceboard.init(
    db_path="./my_traces.db",   # カスタムデータベースパス（デフォルト: ./traceboard.db）
    auto_open=False,             # 初期化時にブラウザを自動で開かない
)
```

## プログラムによるエクスポート

```python
from traceboard import TraceExporter

exporter = TraceExporter("./traceboard.db")

# 全トレースを JSON ファイルにエクスポート
data = exporter.export_json("traces.json")

# 特定のトレースを CSV にエクスポート
exporter.export_csv("output.csv", trace_ids=["trace_abc123"])

# メモリ内でデータを取得（ファイル書き込みなし）
data = exporter.export_json()
print(f"エクスポート済み: {data['trace_count']} トレース")
```

## 対応モデル（コスト追跡）

TraceBoard は **6 プロバイダー、100 以上のモデルバリアント**のコスト追跡に対応しています：

| プロバイダー | モデル |
|---|---|
| **OpenAI** | `gpt-5.2`、`gpt-5.1`、`gpt-5`、`gpt-5-mini`、`gpt-5-nano`、`gpt-4.1`、`gpt-4o`、`o1`、`o3`、`o4-mini` など |
| **Anthropic** | `claude-opus-4.6`、`claude-opus-4.5`、`claude-sonnet-4.5`、`claude-haiku-4.5`、`claude-opus-4`、`claude-sonnet-4`、`claude-3.5-sonnet` |
| **Google** | `gemini-3-pro-preview`、`gemini-3-flash-preview`、`gemini-2.5-pro`、`gemini-2.5-flash`、`gemini-2.0-flash` |
| **DeepSeek** | `deepseek-chat`、`deepseek-reasoner` |
| **Meta** | `llama-4-maverick`、`llama-4-scout`、`llama-3.3-70b`、`llama-3.1-405b` |
| **Mistral** | `mistral-large-latest`、`mistral-medium-latest`、`mistral-small-latest`、`codestral-latest` |

不明なモデルはデフォルト価格（$2.00/$8.00 per 1M トークン）にフォールバックします。価格データは各プロバイダーの公式価格ページに基づき、各リリースで更新されます。

## 開発

```bash
# クローンして開発モードでインストール
git clone https://github.com/123zcr/traceboard.git
cd traceboard
pip install -e ".[dev]"

# テスト実行
pytest

# 開発モードでダッシュボードを起動
traceboard ui --no-open
```

## コントリビュート

コントリビューションを歓迎します！以下の手順でお願いします：

1. リポジトリをフォーク
2. フィーチャーブランチを作成（`git checkout -b feature/my-feature`）
3. 変更を加え、テストを追加
4. `pytest` を実行して全テストが通ることを確認
5. プルリクエストを送信

## 必要環境

- Python >= 3.10
- サポート対象 SDK のいずれか: `openai-agents`、`anthropic`、`langchain-core`、`litellm`

## ライセンス

[MIT](LICENSE)
