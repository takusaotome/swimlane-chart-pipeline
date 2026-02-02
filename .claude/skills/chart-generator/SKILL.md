---
name: chart-generator
description: chart_plan.json から Miro 上にスイムレーンチャートを生成する
user_invocable: true
---

# Chart Generator Skill

chart_plan.json を入力として、Miro ボード上にスイムレーンチャートを生成します。

## 使い方

```
/chart-generator <chart_plan.json のパス>
```

## 前提条件

- `.env` に `MIRO_TOKEN` と `MIRO_BOARD_ID` が設定されていること
- chart_plan.json が schema_version "1.0" に準拠していること

## 処理手順

1. 引数で指定された chart_plan.json のパスを確認する
2. run_id が指定されていない場合は UUID v4 を生成する
3. `scripts/generate_chart.py` を実行する

```bash
python scripts/generate_chart.py <chart_plan.json> [--run-id <uuid>]
```

4. 実行結果を確認する:
   - 成功時: `output/{run_id}/miro_items.json` が生成される
   - 失敗時: エラーメッセージを表示し、`scripts/cleanup_chart.py` で後片付けを実行する

5. 成功時はボードURLをユーザーに提示する

## エラーハンドリング

生成途中でエラーが発生した場合:

1. `output/{run_id}/miro_items.json` が存在する場合、部分的に作成されたアイテムがある
2. `scripts/cleanup_chart.py output/{run_id}/miro_items.json --force` で削除
3. エラー原因を特定し、chart_plan.json を修正後に再実行

## 出力

- `output/{run_id}/miro_items.json` - 作成されたMiroアイテムのID一覧
- コンソールに作成アイテム数とボードURLを表示

## 参考資料

- `references/miro_api_constraints.md` - Miro API の制約事項
