# Swimlane Chart Pipeline for Miro

お客様ヒアリング情報（議事録・メモ・業務シナリオ）から、Miro 上のスイムレーンチャートを自動生成するパイプライン。Claude Code の Skill / Agent として実装し、`/swimlane-pipeline` コマンド一つで全工程を実行可能にする。

## パイプライン全体像

```
[Input: 議事録/メモ/箇条書き]
        │
   Step 1: process-analyzer        業務プロセス分析 → 要件定義書
        │
   Step 2: requirements-reviewer   抜け漏れ・矛盾レビュー（最大3回ループ）
        │
   Step 3: chart-planner           要件定義書 → チャート計画 JSON
        │
   Step 4: chart-generator         JSON → Miro API でチャート生成
        │
   Step 5: chart-reviewer          Miro 読戻しレビュー（最大3回ループ）
        │
[Output: Miro Board URL]
```

## 現在のステータス

**Phase 1〜4 実装済み / Phase 5 統合テスト段階**

- [x] Miro API 経由のスイムレーンチャート生成スクリプト (`scripts/swimlane_chart_demo.py`)
- [x] コアライブラリ抽出 (`src/swimlane_lib.py`)
- [x] JSON ローダー (`src/chart_plan_loader.py`)
- [x] CLI ラッパー (`scripts/generate_chart.py`)
- [x] サンプル JSON 化 (`examples/monthly_report_flow.json`)

## セットアップ

### 前提条件

- Python 3.12+
- Miro アカウント（Free プラン以上）

### インストール

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Miro API トークンの取得

1. [Miro Developer Platform](https://miro.com/app/settings/user-profile/apps) でアプリを作成
2. スコープに `boards:read` と `boards:write` を設定
3. アプリをインストールしてアクセストークンを取得

詳細は [docs/setup-guide.md](docs/setup-guide.md) を参照。

### 環境変数の設定

プロジェクトルートに `.env` ファイルを作成:

```
MIRO_TOKEN=your_access_token_here
MIRO_BOARD_ID=your_board_id_here
```

ボード ID はボード URL の `https://miro.com/app/board/<BOARD_ID>/` から取得する。

## 使い方

### デモスクリプト（ハードコードされた月次売上報告フロー）

```bash
python scripts/swimlane_chart_demo.py
```

### JSON からチャート生成

```bash
python scripts/generate_chart.py <chart_plan.json> [--run-id <uuid>]
```

### パイプラインコマンド（Claude Code 上で実行）

```bash
/swimlane-pipeline
```

議事録テキストを入力すると、要件分析 → レビュー → JSON 生成 → Miro チャート生成 → 視覚レビューまで自動実行される。

## プロジェクト構造

```
swimlane-chart/
├── .claude/
│   ├── skills/                    ← Skill 定義
│   │   ├── process-analyzer/      業務プロセス分析
│   │   ├── requirements-reviewer/ 要件レビューループ
│   │   ├── chart-planner/         要件 → JSON 構造化
│   │   ├── chart-generator/       JSON → Miro API
│   │   └── swimlane-pipeline/     全ステップ統合実行
│   └── agents/                    ← Agent 定義
│       ├── process-consultant.md
│       ├── chart-layout-reviewer.md
│       └── process-analyst.md
├── src/                           ← コアライブラリ
│   ├── swimlane_lib.py            座標計算・API クライアント
│   └── chart_plan_loader.py       JSON → dataclass 変換
├── scripts/                       ← CLI ツール
│   ├── generate_chart.py          JSON → Miro チャート生成
│   ├── cleanup_chart.py           生成済みアイテム一括削除
│   ├── validate_chart.py          Miro API 読戻し＋検証
│   └── swimlane_chart_demo.py     ハードコードされたデモスクリプト
├── tests/                         ← テストスイート
│   ├── conftest.py                共通フィクスチャ
│   ├── test_generate_chart.py
│   ├── test_validate_chart.py
│   └── test_chart_plan_loader.py
├── examples/                      ← サンプルデータ
│   └── monthly_report_flow.json
├── output/                        ← 実行時生成物（.gitignore 対象）
├── docs/
│   ├── design.md                  スクリプト設計書
│   ├── setup-guide.md             セットアップ手順書
│   └── swimlane-pipeline-design.md パイプライン設計書
├── requirements.txt               依存パッケージ
├── .env                           環境変数（.gitignore 対象）
└── .gitignore
```

## カスタマイズ

### フローの変更（デモスクリプト）

`scripts/swimlane_chart_demo.py` 内の以下の定数を編集する:

| 定数 | 説明 |
|---|---|
| `LANES` | レーン名（部署名）のリスト。上から下の順序 |
| `COLUMNS` | 時系列カラムのヘッダーラベル。左から右の順序 |
| `NODES` | ノード定義。`key`, `label`, `lane`, `col`, `kind` 等を指定 |
| `EDGES` | コネクタ定義。`src` と `dst` にノードの `key` を指定 |

### フローの変更（JSON 入力）

`chart_plan.json` を作成して `scripts/generate_chart.py` に渡す:

```json
{
  "title": "月次売上報告フロー",
  "subtitle": "月次（毎月末締め、翌月5営業日目報告）",
  "lanes": ["各営業拠点", "営業企画部", "経理部"],
  "columns": ["毎月末日", "翌月1日", "翌月2日"],
  "layout": { "lane_height": 220, "col_width": 360 },
  "nodes": [
    { "key": "START", "label": "開始", "lane": "各営業拠点", "col": 0, "kind": "start" }
  ],
  "edges": [
    { "src": "START", "dst": "SF_INPUT" }
  ]
}
```

### ノード種別

| kind | Miro Shape | 用途 |
|---|---|---|
| `start` | circle | フロー開始点 |
| `end` | circle | フロー終了点 |
| `task` | rectangle | タスク / 処理 |
| `decision` | rhombus | 判断 / 分岐 |
| `chip` | round_rectangle | 使用システム名タグ |

### レイアウト調整

`Layout` dataclass のパラメータで調整:

```python
Layout(
    lane_height=220,      # 各レーンの高さ
    col_width=360,        # 各カラムの幅
    left_label_width=240, # 左端のレーンラベル領域幅
    task_w=170,           # タスクノードの幅
    task_h=80,            # タスクノードの高さ
    frame_padding=200,    # フレーム右側の余白
)
```

各ノードの `dx`, `dy` で同一カラム・レーン内の微調整が可能。

## 実装ロードマップ

| Phase | 内容 | ステータス |
|---|---|---|
| 1 | 基盤整備: コアライブラリ抽出、JSON ローダー、CLI ラッパー | 実装済み |
| 2 | ユーティリティ: cleanup / validate スクリプト | 実装済み |
| 3 | Agent 定義: process-consultant / chart-layout-reviewer / process-analyst | 実装済み |
| 4 | Skill 作成: chart-generator → chart-planner → requirements-reviewer → process-analyzer | 実装済み |
| 5 | 統合: swimlane-pipeline マスターオーケストレーター + E2E テスト | 進行中 |

## ドキュメント

- [スクリプト設計書](docs/design.md) - データモデル、座標計算、API 仕様の詳細
- [セットアップ手順書](docs/setup-guide.md) - Miro API の環境構築ガイド
- [パイプライン設計書](docs/swimlane-pipeline-design.md) - Skill/Agent 全体設計

## 制約 / 注意事項

- Bulk API は 1 回あたり最大 20 アイテム（トランザクション）
- コネクタの経路（折れ曲がり位置）は Miro が自動決定する
- レート制限: 100,000 クレジット/分（通常の利用では問題なし）
