# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Miro REST API v2 を使って、非構造テキスト（議事録・業務シナリオ等）からスイムレーンチャートを自動生成するパイプライン。Python 3.12+。

## Environment Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install requests python-dotenv
```

`.env` ファイルに `MIRO_TOKEN` と `MIRO_BOARD_ID` を設定する（`.gitignore` 済み）。取得手順は `docs/setup-guide.md` を参照。

## CLI Commands

```bash
# チャート生成（chart_plan.json → Miro）
python scripts/generate_chart.py <chart_plan.json> [--run-id <uuid>]

# 生成済みチャートの削除
python scripts/cleanup_chart.py <output/run_id/miro_items.json> [--force]

# チャートのバリデーション（重複・ラベル切れ・コネクタ欠損チェック）
python scripts/validate_chart.py <output/run_id/miro_items.json> [--chart-plan <json>]

# ハードコードされたデモ（月次売上報告フロー）
python scripts/swimlane_chart_demo.py
```

## Architecture

### Core Library (`src/`)

- **`swimlane_lib.py`** — データモデル（`Layout`, `Node`, `Edge` frozen dataclass）、座標計算、Miro ペイロードビルダー、`MiroClient` クラス。全 API 呼び出しに指数バックオフ付きリトライ。Bulk API は 20 アイテム/トランザクション上限。
- **`chart_plan_loader.py`** — JSON ロード・バリデーション・`ChartPlan` NamedTuple への変換。RFC 6902 JSON Patch の部分サポート（replace/add/remove）。

### Pipeline Flow（Skills / Agents）

非構造テキスト → requirements.md → chart_plan.json → Miro チャートの 3 段階変換。

| Step | Skill | 入力 → 出力 |
|------|-------|-------------|
| 1 | `/process-analyzer` | テキスト → `requirements.md` |
| 2 | `/requirements-reviewer` | `requirements.md` のレビューループ（最大 3 ラウンド） |
| 3 | `/chart-planner` | `requirements.md` → `chart_plan.json` |
| 4 | `/chart-generator` | `chart_plan.json` → Miro（`generate_chart.py` 実行） |
| 5 | `/swimlane-pipeline` | 上記全体をオーケストレーション |

Agents: `process-consultant`（要件レビュー）、`chart-layout-reviewer`（視覚品質レビュー、JSON Patch 出力）、`process-analyst`（テキスト分析）。

### Key Design Decisions

- **Frozen dataclass** による不変データモデル
- **Frame ベース分離**: 各 run ごとに専用 Frame を作成し、`miro_items.json` で追跡
- **出力ディレクトリ**: `output/{run_id}/` に `miro_items.json` と `validation_report.json` を格納
- ノードの `key` は `UPPER_SNAKE_CASE`、`kind` は `task|decision|start|end|chip|text`

## Miro API Constraints

- Bulk API: 1 トランザクションあたり最大 20 アイテム（`chunked()` で分割）
- コネクタはバルク作成不可、1 本ずつ作成
- レート制限: 100,000 credits/分
- コネクタのルーティングは Miro 側が自動決定

## Development Practices

- コードを書く際は **TDD スキル (`/tdd-developer`)** を使用して実施すること。テスト先行で開発し、Red → Green → Refactor のサイクルを守る。
