[English](README.md) | [中文](README_zh.md) | **日本語**

# TraceBoard

**ローカルファーストの AI Agent オブザーバビリティ＆デバッグツールキット。**

TraceBoard は Agent トレーシングにおける *SQLite* です —— 設定不要、完全ローカル、即座にセットアップ。クラウドアカウント、Docker、外部データベースは一切不要。`pip install` するだけで始められます。

---

## 特徴

- **設定不要** —— `pip install traceboard` + コード 2 行
- **ローカルファースト** —— 全データをローカルの SQLite ファイルに保存、プライバシーリスクゼロ
- **内蔵 Web ダッシュボード** —— `traceboard ui` でインタラクティブなトレースビューアを起動
- **OpenAI Agents SDK** —— `TracingProcessor` インターフェースによるネイティブ統合
- **コスト追跡** —— モデル別の自動コスト計算（GPT-4o、o1、o3、GPT-4.1 など）
- **リアルタイム更新** —— WebSocket によるライブビュー（HTTP ポーリングフォールバック付き）
- **データエクスポート** —— JSON または CSV 形式でオフライン分析用にエクスポート
- **オフライン動作** —— インターネット接続不要

## クイックスタート

### インストール

```bash
pip install traceboard
```

### 統合（たった 2 行）

```python
import traceboard
traceboard.init()

# 既存の OpenAI Agents SDK コード —— 変更不要
from agents import Agent, Runner

agent = Agent(name="Assistant", instructions="あなたは親切なアシスタントです。")
result = Runner.run_sync(agent, "こんにちは！")
print(result.final_output)
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

TraceBoard は以下のモデルのコストを自動計算します：

| モデルファミリー | モデル |
|---|---|
| GPT-4o | `gpt-4o`、`gpt-4o-mini` |
| GPT-4.1 | `gpt-4.1`、`gpt-4.1-mini`、`gpt-4.1-nano` |
| o シリーズ | `o1`、`o1-mini`、`o3`、`o3-mini`、`o4-mini` |
| GPT-4 Turbo | `gpt-4-turbo` |
| GPT-4 | `gpt-4` |
| GPT-3.5 | `gpt-3.5-turbo` |

不明なモデルは GPT-4o の価格にフォールバックします。価格データは各リリースにバンドルされ更新されます。

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
- OpenAI Agents SDK（`openai-agents`）

## ライセンス

[MIT](LICENSE)
