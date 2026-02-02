---
name: requirements-reviewer
description: 要件定義書(requirements.md)のレビューループを制御し、品質を担保する
user_invocable: true
---

# Requirements Reviewer Skill

requirements.md の品質レビューを行い、必要に応じて修正を適用します。

## 使い方

```
/requirements-reviewer <requirements.md のパス>
```

## 処理手順

### 1. 要件定義書の読み込み

指定パスの requirements.md を Read ツールで読み込む。

### 2. process-consultant Agent によるレビュー

Task ツールで `process-consultant` agent を呼び出し、レビューを依頼する。

agent への入力: requirements.md の全文をプロンプトとして渡す。

### 3. レビュー結果の処理

agent の出力（JSON形式）を解析し、severity に応じて処理を分岐:

#### Critical / Major 指摘がある場合

1. 指摘事項とその修正パッチをユーザーに提示する
2. AskUserQuestion ツールで承認を求める:
   - 「すべて適用」
   - 「個別に選択」
   - 「修正せずに続行」
3. 承認された修正のみを requirements.md に適用する

#### Minor / Info 指摘のみの場合

1. 修正内容をユーザーに表示する（情報として）
2. 自動適用する（事実の書き換えではなく、追記・明確化のみ）

### 4. レビューラウンドの制御

- 修正を適用した場合、再度 process-consultant agent に送付してレビュー
- **最大3ラウンド**まで繰り返す
- 3ラウンド後に Critical が残っている場合:
  - ユーザーにエスカレーション（残存問題を明示し、手動修正を依頼）

### 5. 完了判定

以下のいずれかで完了:
- agent が `"chartability": "ready"` を返した
- 3ラウンド完了
- ユーザーが「修正せずに続行」を選択

## 修正規則

### 許可される修正（自動適用可）

- 欠落セクションの追加（例: 「例外パス」セクションの新規追加）
- 曖昧な記述の明確化（例: 「データを送る」→「メールでExcelファイルを送付」）
- 構造の改善（箇条書きの追加、フォーマット統一）

### 禁止される修正（ユーザー承認必須）

- ユーザーが述べた事実の変更
- ステップの追加・削除
- 部門名の変更
- 判断条件の変更

## 出力

修正後の requirements.md（元ファイルを上書き）

## パッチ形式

修正指示には2つの形式が使用される。混同しないこと:

- **テキストパッチ**: requirements.md (Markdown) に対する修正。Edit ツールで `old_string` / `new_string` を指定して適用する。
- **JSON Patch**: chart_plan.json に対する修正。`apply_patch()` 関数で `{"op": "replace", "path": "/nodes/0/dx", "value": 10}` 形式で適用する。

requirements-reviewer スキルではテキストパッチのみを使用する。

## 参考資料

- `references/review_criteria.md` - レビュー基準の詳細
- `references/common_gaps.md` - よくある漏れパターン
