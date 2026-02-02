# Node Kind Guide

## ノード種別一覧

| kind | 形状 | Miro shape | 用途 | デフォルトサイズ |
|---|---|---|---|---|
| `start` | 円 | circle | プロセス開始 | 50×50 |
| `end` | 円 | circle | プロセス終了 | 50×50 |
| `task` | 矩形 | rectangle | 通常業務タスク | 170×80 |
| `decision` | ひし形 | rhombus | 判断ポイント | 90×90 |
| `chip` | 角丸矩形 | round_rectangle | システム/ツールラベル | 90×26 |

## kind 判定ルール

### start
- 要件定義書の最初のステップ
- トリガーイベント（「開始」「受付」等）
- プロセスに1つだけ

### end
- 要件定義書の最後のステップ
- プロセスの完了を示す
- 複数の end ノードがある場合もある（例: 正常終了 + 例外終了）

### task
- 通常の業務アクション
- 「〇〇する」「〇〇を作成」「〇〇を確認」等の動詞を含む
- 1つの部門が1つの作業を行う

### decision
- Yes/No または条件分岐がある判断ポイント
- 要件定義書の「判断ポイント」セクションに記載された項目
- ラベルは短く（「差異\nある？」のように改行で2行以内）
- `\n` を使って改行

### chip
- 業務で使用するシステム・ツール名
- task ノードの補足情報
- 親の task ノードの直下に配置（dy=+70）
- key は `CHIP_` + システム略称

## key の命名規則

- **大文字スネークケース**: `SF_INPUT`, `DEC_DIFF`, `CHIP_EXCEL`
- **start/end**: `START`, `END` (複数ある場合は `START_1`, `END_NORMAL`, `END_ERROR`)
- **task**: 動作を表す短い名称 (`EXCEL_SUM`, `REVIEW`, `UPLOAD`)
- **decision**: `DEC_` + 判断内容 (`DEC_DIFF`, `DEC_APPROVE`)
- **chip**: `CHIP_` + システム名 (`CHIP_SF`, `CHIP_SLACK`)

## label のガイドライン

- 日本語: 1行あたり最大8文字程度（task_w=170px の場合）
- 2行以上の場合は `\n` で改行
- decision は2行以内に収める
- chip は1行（システム名のみ）
