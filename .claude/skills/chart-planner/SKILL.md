---
name: chart-planner
description: 要件定義書(requirements.md)からスイムレーンチャートの設計図(chart_plan.json)を生成する
user_invocable: true
---

# Chart Planner Skill

レビュー済みの requirements.md を読み込み、スイムレーンチャートの設計図（chart_plan.json）を生成します。

## 使い方

```
/chart-planner <requirements.md のパス> [--run-id <uuid>]
```

## 処理手順

### 1. 要件定義書を読み込む

指定されたパスの requirements.md を Read ツールで読み込む。

### 2. データ抽出

要件定義書から以下を抽出:
- **lanes**: 「関連部門・役職」セクションから部門名リストを生成
- **columns**: 「工程フェーズ」または時系列情報からフェーズリストを生成
- **nodes**: 各プロセスステップをノードに変換
- **edges**: ステップ間の接続関係をエッジに変換

### 3. ノード種別の決定

`references/node_kind_guide.md` に従い各ステップの kind を決定:
- `start` / `end`: 開始・終了ノード
- `task`: 通常の業務タスク
- `decision`: 判断ポイント（Yes/No分岐）
- `chip`: 使用システム・ツールのラベル

### 4. レイアウト計算

`references/layout_heuristics.md` に従い:
- 同一セル（同一lane × 同一col）内の複数ノードの dx/dy オフセットを計算
- レーン数・カラム数に応じた layout パラメータの自動調整
- chip ノードは親ノードの直下（dy=70）に配置

### 5. 色の適用

`references/color_palette.md` に従い:
- kind に応じたデフォルト fill カラーを設定
- 特別な意味を持つノード（エラーパス等）に強調色を適用

### 6. エッジの設定

- 通常の前進エッジ: shape="elbowed", color=null
- 判断ポイントの Yes 分岐: color="#2E7D32" (green)
- 判断ポイントの No 分岐: color="#C62828" (red)
- 差戻し・ループエッジ: dashed=true, shape="curved"

### 7. バリデーション

生成前に自動検証:
- 全 edges の src/dst が nodes に存在するか
- 全 nodes の lane が lanes に存在するか
- 全 nodes の col が columns の範囲内か
- 重複 key がないか

### 8. JSON 出力

`assets/chart_plan_schema.json` に準拠した chart_plan.json を生成し、
`output/{run_id}/chart_plan.json` に書き込む。

## 出力

- `output/{run_id}/chart_plan.json`

## 参考資料

- `references/layout_heuristics.md` - レイアウト計算ルール
- `references/node_kind_guide.md` - ノード種別ガイド
- `references/color_palette.md` - カラーパレット
- `assets/chart_plan_schema.json` - JSON スキーマ定義
