# swimlane_chart.py 設計書

## 1. 概要

Miro REST API v2 を使用して、スイムレーンチャート（業務フロー図）をプログラムで生成する Python スクリプト。
「縦方向にレーン（部署）、横方向に時系列」のレイアウトで、ノード（タスク・判断等）とコネクタ（矢印）を自動配置する。

### 1.1 背景

note.com の記事「AIで業務フローをつくる to Miro」の手法に基づき、座標計算とコネクタ接続ルールを事前に厳密に定義することで、品質の安定した業務フロー図を API 経由で生成する。

### 1.2 サンプルフロー

初期実装では「月次売上報告フロー」を再現する。5部署 x 7時系列カラムのスイムレーン上に、開始・タスク・判断・終了ノードとコネクタを配置する。

---

## 2. アーキテクチャ

```
swimlane_chart.py
├── [1] データ定義層   ─ LANES, COLUMNS, NODES, EDGES (定数)
├── [2] レイアウト設定層 ─ Layout dataclass (調整パラメータ)
├── [3] 座標計算層     ─ lane_center_y(), col_center_x(), node_xy()
├── [4] Payload 生成層 ─ shape_payload(), text_payload(), connector_payload()
├── [5] API クライアント層 ─ MiroClient (HTTP 通信)
└── [6] オーケストレーション層 ─ main() (全体制御)
```

### 2.1 処理フロー

```
1. 背景レイヤー生成  build_background_items()
   ├── 外枠フレーム (rectangle)
   ├── レーン区切り線 (horizontal lines)
   ├── カラム区切り線 (vertical lines)
   └── ヘッダー区切り線
        │
2. テキストレイヤー生成  build_text_items()
   ├── タイトル / サブタイトル
   ├── カラムヘッダーラベル
   └── レーンラベル
        │
3. ノードレイヤー生成  build_node_items()
   ├── start / end (circle)
   ├── task (rectangle)
   ├── decision (rhombus)
   └── chip (round_rectangle)
        │
4. Bulk 作成  MiroClient.bulk_create()
   └── 20件ずつバッチ送信 → レスポンスから item ID 回収
        │
5. ID マッピング  extract_key_from_item()
   └── content 内の [KEY] パターンから node_key → miro_item_id を構築
        │
6. コネクタ作成  MiroClient.create_connector()
   └── EDGES を走査し、src/dst の item_id を使って矢印を接続
```

---

## 3. データモデル

### 3.1 Node

| フィールド | 型 | 説明 |
|---|---|---|
| `key` | str | 一意識別子。コネクタ接続やID逆引きに使用 |
| `label` | str | Miro 上に表示されるテキスト |
| `lane` | str | 配置先レーン名（LANES の要素と一致） |
| `col` | int | 配置先カラムインデックス（0始まり） |
| `kind` | str | ノード種別: `task`, `decision`, `start`, `end`, `chip`, `text`, `lane_label`, `col_label` |
| `dx` | int | カラム中心からの X 方向オフセット（微調整用） |
| `dy` | int | レーン中心からの Y 方向オフセット（微調整用） |
| `w` | int? | 幅の上書き（None で Layout のデフォルト値を使用） |
| `h` | int? | 高さの上書き |
| `fill` | str? | 背景色（16進カラーコード） |
| `stroke` | str? | 枠線色 |
| `stroke_width` | float? | 枠線の太さ |

### 3.2 Edge

| フィールド | 型 | 説明 |
|---|---|---|
| `src` | str | 始点ノードの key |
| `dst` | str | 終点ノードの key |
| `label` | str | コネクタ上に表示するテキスト |
| `color` | str? | 線の色（16進カラーコード） |
| `dashed` | bool | 破線表示（差戻し等に使用） |
| `shape` | str | コネクタ形状: `elbowed`, `straight`, `curved` |
| `end_cap` | str | 矢印先端形状: `stealth`, `none` |

### 3.3 Layout

レイアウト全体の調整パラメータを集約した frozen dataclass。

| カテゴリ | フィールド | デフォルト値 | 説明 |
|---|---|---|---|
| 原点 | `origin_x`, `origin_y` | 0, 0 | ダイアグラム中心座標（Frame内ではFrame中心に設定） |
| レーン | `left_label_width` | 260 | 左端のレーンラベル領域幅 |
| | `header_height` | 80 | 時系列ヘッダー行の高さ |
| | `lane_height` | 200 | 各レーンの高さ（6-10レーン時） |
| | `lane_gap` | 0 | レーン間の間隔 |
| カラム | `col_width` | 420 | 各時系列カラムの幅 |
| | `col_gap` | 0 | カラム間の間隔 |
| 罫線 | `divider_thickness` | 8 | レーン/カラム区切り線の太さ |
| | `gridline_thickness` | 8 | グリッド線の太さ |
| ノード | `task_w` x `task_h` | 160 x 80 | タスクノードのデフォルトサイズ |
| | `decision_w` x `decision_h` | 110 x 110 | 判断ノードのデフォルトサイズ |
| | `chip_w` x `chip_h` | 130 x 28 | チップ（システム名タグ）のデフォルトサイズ |
| タイトル | `title_y_offset` | 260 | スイムレーン上端からのタイトル表示距離 |
| | `frame_padding` | 200 | フレーム外側の余白 |

---

## 4. 座標計算

### 4.1 座標系

- 原点 `(origin_x, origin_y)` をダイアグラムの中心とする
- X 軸: 右方向が正（時系列の進行方向）
- Y 軸: 下方向が正（レーンの積み重ね方向）

### 4.2 レーン中心 Y 座標

```
swimlane_top_left_y = origin_y - total_height / 2
lane_top = swimlane_top_left_y + header_height + lane_index * (lane_height + lane_gap)
lane_center_y = lane_top + lane_height / 2
```

### 4.3 カラム中心 X 座標

```
swimlane_top_left_x = origin_x - total_width / 2
col_left = swimlane_top_left_x + left_label_width + col_index * (col_width + col_gap)
col_center_x = col_left + col_width / 2
```

### 4.4 ノード座標

```
node_x = col_center_x(col) + dx
node_y = lane_center_y(lane) + dy
```

`dx`, `dy` により同一カラム・レーン内に複数ノードを配置可能。

### 4.5 全体サイズ

```
total_width  = left_label_width + len(COLUMNS) * col_width + (len(COLUMNS) - 1) * col_gap
total_height = len(LANES) * lane_height + (len(LANES) - 1) * lane_gap + header_height
```

---

## 5. Miro API 利用仕様

### 5.1 使用エンドポイント

| 操作 | メソッド | エンドポイント | 備考 |
|---|---|---|---|
| Frame 作成 | POST | `/v2/boards/{board_id}/frames` | 各 run ごとに専用 Frame を作成 |
| Bulk 作成 | POST | `/v2/boards/{board_id}/items/bulk` | 最大 20 アイテム/回、トランザクション。`parent` プロパティで Frame 内に配置 |
| コネクタ作成 | POST | `/v2/boards/{board_id}/connectors` | startItem/endItem で既存アイテムを接続 |
| Frame 内アイテム取得 | GET | `/v2/boards/{board_id}/items?parent_item_id={frame_id}` | validate_chart.py で使用 |
| アイテム削除 | DELETE | `/v2/boards/{board_id}/items/{item_id}` | 404 は「削除済み」として正常扱い |
| コネクタ削除 | DELETE | `/v2/boards/{board_id}/connectors/{connector_id}` | 404 は「削除済み」として正常扱い |

### 5.2 認証

- `Authorization: Bearer {MIRO_TOKEN}` ヘッダーで認証
- 必要スコープ: `boards:read`, `boards:write`

### 5.3 Bulk 作成の制約

- **最大 20 アイテム/回**: `chunked()` 関数で 20 件ずつ分割送信
- **トランザクション性**: 1 バッチ内で 1 件でも失敗すると全件ロールバック
- **レスポンス**: 作成されたアイテムの配列（各アイテムに `id` が付与される）

### 5.4 コネクタ作成の制約

- 両端が既存アイテムに接続されている必要がある（片端だけの dangling connector は不可）
- `snapTo` プロパティ: `auto`, `top`, `left`, `bottom`, `right` から選択
- `position` プロパティ（代替）: `x: 0.0-1.0`, `y: 0.0-1.0` で接続点を指定
- `snapTo` と `position` は排他的（同時指定不可）

### 5.5 レート制限

- **クレジットベース**: 100,000 クレジット/分（ユーザー/アプリ単位）
- **Level 1**: 50 クレジット/回 = 最大 2,000 リクエスト/分
- **429 エラー**: レート超過時に返却される

### 5.6 ID マッピング方式

ノードの `content` に `[KEY] ラベル` 形式でキーを埋め込み、Bulk 作成レスポンスから正規表現で抽出して `key -> miro_item_id` の辞書を構築する。

```python
# 埋め込み例
"[SF_INPUT] 売上データ入力"

# 抽出パターン
r"^\[(?P<key>[A-Z0-9_]+)\]\s"
```

---

## 6. ノード種別と Miro Shape の対応

| kind | Miro shape | デフォルトサイズ | 用途 |
|---|---|---|---|
| `start` | `circle` | 50 x 50 | フロー開始点 |
| `end` | `circle` | 50 x 50 | フロー終了点 |
| `task` | `rectangle` | 160 x 80 | 一般的なタスク/処理 |
| `decision` | `rhombus` | 110 x 110 | 判断・分岐（ラベル有効表示幅 ~70px、日本語4文字/行） |
| `chip` | `round_rectangle` | 130 x 28 | 使用システム名タグ（日本語 ~7文字収容） |

---

## 7. 背景レイヤーの構成

| 要素 | 実装 | 備考 |
|---|---|---|
| 外枠フレーム | 全体サイズの rectangle | fill: #FFFFFF, stroke: #CFCFCF |
| レーン区切り線 | 水平方向の薄い rectangle | fill: #E5E5E5, thickness: 8px |
| カラム区切り線 | 垂直方向の薄い rectangle | fill: #E5E5E5, thickness: 8px |
| ヘッダー区切り線 | 水平方向の薄い rectangle | ヘッダー行とレーン領域の境界 |

Miro API には「線（line）」の直接作成がないため、細い矩形で代用する。

---

## 8. 依存関係

| パッケージ | バージョン | 用途 |
|---|---|---|
| `requests` | >= 2.28 | Miro REST API HTTP 通信 |
| Python | >= 3.12 | dataclass, typing 等の言語機能 |

### 8.1 環境変数

| 変数名 | 必須 | 説明 |
|---|---|---|
| `MIRO_TOKEN` | Yes | Miro API アクセストークン |
| `MIRO_BOARD_ID` | Yes | 対象ボードの ID |

---

## 9. エラーハンドリング

| 状況 | 挙動 | 備考 |
|---|---|---|
| 環境変数未設定 | `SystemExit` で即終了 | |
| Bulk 作成失敗 (status >= 300) | `@retry` で指数バックオフリトライ（最大3回） | トランザクション全体がロールバック |
| コネクタ作成失敗 (status >= 300) | `@retry` で指数バックオフリトライ（最大3回） | |
| ID マッピング失敗 | WARN 出力し、該当コネクタを SKIP | |
| アイテム削除で 404 | 「削除済み」として正常扱い（即 return） | cleanup 時のハング防止 |
| コネクタ削除で 404 | 「削除済み」として正常扱い（即 return） | cleanup 時のハング防止 |
| Frame 不在時の cleanup | Frame 存在チェック → 不在なら即完了 | 全アイテム削除済みの早期終了 |
| レート制限 (429) | `Retry-After` ヘッダを尊重、なければ指数バックオフ | |

---

## 10. 制約・注意事項

1. **Bulk 作成の上限**: 1 トランザクションあたり最大 20 アイテム。`chunked()` 関数で分割送信する。

2. **content 内のキー埋め込み**: `[KEY] ラベル` の形式でキーを Bulk 作成時に埋め込み、レスポンスから `key → miro_item_id` の辞書を構築する。キーはラベルに紛れないよう `<span style="font-size:1px">[KEY]</span>` で視覚的に隠蔽している。

3. **コネクタの経路制御**: Miro API のコネクタは `elbowed`, `straight`, `curved` の形状を指定できるが、具体的な折れ曲がり位置は制御できない。レーン順序の最適化（隣接性原則）でコネクタ交差を最小化する。

4. **Z-order（重なり順）**: Miro では作成順が重なり順に影響する。背景（フレーム・罫線）→ テキスト → ノードの順で作成すること。

5. **Frame 内座標**: Frame 内のアイテムは、Bulk 作成時に `parent` プロパティに Frame ID を注入することで Frame に所属させる。座標系は Miro API のデフォルト動作（Frame の top-left 基点の相対座標）に依存しており、`relativeTo` を明示設定していない。`generate_chart.py` では `origin_x = chart_w // 2`, `origin_y = chart_h // 2 + ORIGIN_Y_TITLE_OFFSET` でフレーム中心を基準に座標計算している。

6. **削除済みアイテムの扱い**: DELETE エンドポイントで 404 が返った場合は「既に削除済み」として正常扱いし、リトライしない。

---

## 11. 拡張計画

| 項目 | 概要 | ステータス |
|---|---|---|
| リトライ/バックオフ | 429 エラー時の自動リトライ（指数バックオフ） | ✅ 実装済み |
| JSON/YAML 入力対応 | ノード・エッジ定義を外部ファイル（chart_plan.json）から読み込み | ✅ 実装済み |
| Frame ベース分離 | 各 run ごとに専用 Frame を作成し、スコープ管理 | ✅ 実装済み |
| cleanup / validate | run_id スコープでの一括削除と Miro 読戻し検証 | ✅ 実装済み |
| レーン順序最適化 | コネクタ交差を最小化するレーン配置アルゴリズム | ✅ 実装済み（chart-planner） |
| ノードサイズ自動調整 | ラベル文字数に応じた width 自動計算 | 未着手 |
| テンプレートボード複製 | レーン背景をテンプレートから複製し、ノードのみ API で追加する方式 | 未着手 |
| dry-run モード | API を呼ばずに座標計算結果のみ出力 | 未着手 |
