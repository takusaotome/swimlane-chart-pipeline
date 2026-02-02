# Pipeline Workflow Reference

## run_id とスコープ管理

全ての生成物は `run_id`（UUID v4）で追跡される。

```
output/
├── {run_id}/
│   ├── requirements.md        ← Step 1 出力 / Step 2 修正
│   ├── chart_plan.json        ← Step 3 出力 / Step 5 修正
│   ├── miro_items.json        ← Step 4 出力（随時flush）
│   └── validation_report.json ← Step 5 出力
```

## Miro上のスコープ: 専用Frame

- 各 run_id ごとに Miro ボード上に**専用 Frame**を作成
- Frame名: `[swimlane] {title} ({run_id短縮8文字})`
- 全ノード・コネクタはこの Frame 内に配置
- cleanup 時は Frame 内のアイテムのみ削除
- readback/validate 時も Frame 内のアイテムのみ対象

## miro_items.json のフォーマット

```json
{
  "run_id": "a1b2c3d4-...",
  "board_id": "uXjVGHJn7Xs=",
  "frame_id": "miro_item_xxx",
  "created_at": "2026-02-01T22:00:00+09:00",
  "items": [
    {"key": "START", "miro_id": "abc123", "type": "shape", "batch": 1}
  ],
  "connectors": [
    {"src": "START", "dst": "SF_INPUT", "miro_id": "ghi789"}
  ],
  "status": "in_progress|completed"
}
```

## Step 5 レビューループの詳細

```
┌─── Round N (最大3回) ───────────────┐
│                                       │
│  1. validate_chart.py 実行           │
│     └→ validation_report.json         │
│                                       │
│  2. chart-layout-reviewer agent       │
│     入力: chart_plan.json +           │
│           validation_report.json      │
│     出力: findings[] + patches[]      │
│                                       │
│  3. status判定                        │
│     ├─ "pass" → ループ終了           │
│     └─ "needs_fix":                  │
│        ├─ ユーザーにパッチ提示       │
│        ├─ 承認 → パッチ適用          │
│        ├─ cleanup_chart.py 実行      │
│        └─ Step 4 再実行 → Round N+1  │
│                                       │
└───────────────────────────────────────┘
```

## パッチ適用のコマンド例

```python
# Pythonスクリプトとして実行
import sys
sys.path.insert(0, '.')
from src.chart_plan_loader import apply_patch

patches = [
    {"op": "replace", "path": "/nodes/1/dx", "value": 80},
    {"op": "replace", "path": "/layout/col_width", "value": 400}
]
apply_patch("output/{run_id}/chart_plan.json", patches)
```

## 安全設計

### 削除の安全策
1. `miro_items.json` の run_id + frame_id で対象を特定
2. Frame 内のアイテムのみ削除対象
3. 削除前にアイテム数の照合
4. 削除順序: コネクタ → シェイプ → テキスト → Frame

### 部分失敗からの回復
1. `miro_items.json` は各バッチ成功時に即座に flush
2. 中断後も `cleanup_chart.py` で安全に削除可能
3. cleanup 後に Step 4 から再実行

### LLMによる事実書換の防止
- Critical/Major 修正はユーザー承認必須
- 自動適用は Minor/Info の追記・明確化のみ
- 事実の書き換え（ユーザーの述べた内容の変更）は禁止
