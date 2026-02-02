---
name: swimlane-pipeline
description: 議事録・メモからMiroスイムレーンチャートを自動生成するパイプライン全体を実行する
user_invocable: true
---

# Swimlane Pipeline Skill

議事録・メモ・業務シナリオテキストからMiro上のスイムレーンチャートを自動生成する統合パイプラインです。

## 使い方

```
/swimlane-pipeline
```

実行後、業務プロセスに関するテキストの入力を求めます。

## パイプライン全体フロー

```
[Input: テキスト]
    │
    ├── Step 1: process-analyzer     → requirements.md
    │   ★ ユーザー確認
    ├── Step 2: requirements-reviewer → requirements.md (修正済)
    ├── Step 3: chart-planner        → chart_plan.json
    ├── Step 4: chart-generator      → Miro チャート生成
    ├── Step 5: chart-layout-reviewer → レビュー + 修正ループ
    │   ★ 問題検出時はユーザー確認
    └── [Complete: Miro Board URL]
```

## 処理手順

### 0. 初期化

1. run_id (UUID v4) を生成する
2. `output/{run_id}/` ディレクトリを作成する
3. ユーザーに run_id を通知する

```bash
python3 -c "import uuid; print(uuid.uuid4())"
mkdir -p output/{run_id}
```

### Step 1: プロセス分析 (process-analyzer)

1. ユーザーからテキスト入力を受け取る
2. Task ツールで `process-analyst` agent を呼び出し、テキストからプロセス要素を抽出する
3. 不明点を AskUserQuestion で質問する（**最大2ラウンド or 累計15問**）
4. 未確認事項は `(Assumption)` タグ付きで記録
5. `output/{run_id}/requirements.md` を Write ツールで作成する

**★ ユーザー確認ポイント**: requirements.md の内容を表示し、確認を求める。
- AskUserQuestion: 「要件定義書を確認してください。問題がなければ『承認』、修正が必要なら『修正を指示』を選んでください。」

### Step 2: 要件レビュー (requirements-reviewer)

1. Task ツールで `process-consultant` agent を呼び出し、requirements.md をレビューする
2. Critical/Major 指摘がある場合:
   - 差分パッチをユーザーに提示し、AskUserQuestion で承認を求める
   - 承認されたパッチを適用
3. Minor/Info 指摘は自動適用
4. **最大3ラウンド**繰り返す
5. 3ラウンド後にCriticalが残存 → ユーザーにエスカレーション

### Step 3: チャート設計 (chart-planner)

1. `output/{run_id}/requirements.md` を Read ツールで読み込む
2. 以下の参考資料を参照:
   - `.claude/skills/chart-planner/references/layout_heuristics.md`
   - `.claude/skills/chart-planner/references/node_kind_guide.md`
   - `.claude/skills/chart-planner/references/color_palette.md`
3. chart_plan.json を生成する
4. バリデーション（edges の src/dst 存在確認、nodes の lane/col 範囲確認）
5. `output/{run_id}/chart_plan.json` を Write ツールで作成する

**自動進行**（ユーザー確認なし）

### Step 4: チャート生成 (chart-generator)

1. `scripts/generate_chart.py` を実行する:

```bash
python scripts/generate_chart.py output/{run_id}/chart_plan.json --run-id {run_id}
```

2. 実行結果を確認する
3. エラー時は cleanup → chart_plan.json 修正 → リトライ

**自動進行**（ユーザー確認なし）

### Step 5: レイアウトレビュー (chart-layout-reviewer)

**このステップはpipeline内で直接実行する**（専用Skillなし）

1. `scripts/validate_chart.py` を実行する:

```bash
python scripts/validate_chart.py output/{run_id}/miro_items.json --chart-plan output/{run_id}/chart_plan.json
```

2. validation_report.json と chart_plan.json を Task ツールで `chart-layout-reviewer` agent に送付する

3. agent の出力を解析:
   - `"status": "pass"` → Step 5 完了、最終結果へ
   - `"status": "needs_fix"` → 修正フロー実行

4. **修正フロー**（needs_fix の場合）:
   a. 修正パッチをユーザーに提示（★ ユーザー確認ポイント）
   b. 承認後、chart_plan.json にパッチ適用:
      ```python
      from src.chart_plan_loader import apply_patch
      apply_patch("output/{run_id}/chart_plan.json", patches)
      ```
   c. `scripts/cleanup_chart.py output/{run_id}/miro_items.json --force` で旧チャート削除
   d. Step 4 から再実行

5. **最大3ラウンド**。3ラウンド後に問題残存 → 現状のまま結果提示

### 完了

1. ボードURLを提示:
   ```
   https://miro.com/app/board/{MIRO_BOARD_ID}/
   ```

2. 生成物の一覧を表示:
   - `output/{run_id}/requirements.md`
   - `output/{run_id}/chart_plan.json`
   - `output/{run_id}/miro_items.json`
   - `output/{run_id}/validation_report.json`

3. ★ ユーザーに最終確認を求める

## ユーザー確認ポイントまとめ

| タイミング | 条件 | 停止 |
|---|---|---|
| Step 1 完了後 | 常に | ✅ 要件定義書の確認 |
| Step 2 修正時 | Critical/Major指摘時 | ✅ 差分パッチの承認 |
| Step 2 修正時 | Minor/Info指摘時 | ❌ 自動適用 |
| Step 3 完了後 | — | ❌ 自動進行 |
| Step 4 完了後 | — | ❌ 自動進行 |
| Step 5 問題検出時 | レイアウト問題あり | ✅ 修正パッチの承認 |
| 完了時 | 常に | ✅ 最終URL提示 |

## エラーハンドリング

### Step 4 でのMiro API エラー
1. エラーメッセージを確認
2. `scripts/cleanup_chart.py` で部分生成物を削除
3. chart_plan.json を確認・修正
4. 再実行

### Step 5 の3ラウンド超過
1. 残存問題をユーザーに提示
2. 「現状のまま完了」を選択可能
3. 手動でMiro上で微調整を推奨

## 参考資料

- `references/pipeline_workflow.md` - パイプラインの詳細ワークフロー
