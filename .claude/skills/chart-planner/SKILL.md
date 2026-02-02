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

### 3. レーン順序の最適化（★重要）

`references/layout_heuristics.md` の「レーン順序の最適化」セクションに従い、コネクタの交差を最小化するレーン順序を決定する:

1. エッジマトリクスを作成し、レーン間の接続数をカウントする
2. decision ノードの分岐先レーンを確認し、decision レーンに隣接させる
3. フロー後半で使用頻度が低いレーンを端に寄せる
4. 交差数が最小になる順序を選択する

### 4. カラムの統合検討（★重要）

`references/layout_heuristics.md` の「カラムの統合」セクションに従い、不要なカラム分割を統合する:

1. decision ノードと直前の処理が同一レーンにある場合、同一カラムに dx オフセットで配置
2. ノード数が少ないカラムの統合を検討
3. 目標: 7カラム以下

### 5. ノード種別の決定

`references/node_kind_guide.md` に従い各ステップの kind を決定:
- `start` / `end`: 開始・終了ノード
- `task`: 通常の業務タスク
- `decision`: 判断ポイント（Yes/No分岐）
- `chip`: 使用システム・ツールのラベル

### 6. レイアウト計算

`references/layout_heuristics.md` に従い:
- 同一セル（同一lane × 同一col）内の複数ノードの dx/dy オフセットを計算（2ノード: ±100, 3ノード: -160/0/+160）
- レーン数・カラム数に応じた layout パラメータの自動調整
- chip ノードは親ノードの直下（dy=70）に配置
- end ノードはフロー終端の自然なレーンに配置（start レーンと異なってよい）

### 7. 色の適用

`references/color_palette.md` に従い:
- kind に応じたデフォルト fill カラーを設定
- 特別な意味を持つノード（エラーパス等）に強調色を適用

### 8. エッジの設定

- 通常の前進エッジ: shape="elbowed", color=null
- 判断ポイントの Yes 分岐: color="#2E7D32" (green)
- 判断ポイントの No 分岐: color="#C62828" (red)
- 差戻し・ループエッジ: dashed=true, shape="curved"

### 9. バリデーション

生成前に自動検証:
- 全 edges の src/dst が nodes に存在するか
- 全 nodes の lane が lanes に存在するか
- 全 nodes の col が columns の範囲内か
- 重複 key がないか
- decision ノードの分岐先レーンが decision レーンの ±2 レーン以内にあるか（★レーン順序チェック）
- カラム数が 7 以下か（★カラム数チェック）

### 10. JSON 出力

`assets/chart_plan_schema.json` に準拠した chart_plan.json を生成し、
`output/{run_id}/chart_plan.json` に書き込む。

## 出力

- `output/{run_id}/chart_plan.json`

## 参考資料

- `references/layout_heuristics.md` - レイアウト計算ルール
- `references/node_kind_guide.md` - ノード種別ガイド
- `references/color_palette.md` - カラーパレット
- `assets/chart_plan_schema.json` - JSON スキーマ定義
