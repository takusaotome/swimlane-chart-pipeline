# Miro API セットアップ手順書

## 前提条件

- Miro アカウント（Free プラン以上）
- Python 3.9 以上
- インターネット接続

---

## Step 1: Miro Developer Platform でアプリを作成する

### 1.1 Developer Platform にアクセス

1. ブラウザで [Miro](https://miro.com) にログインする
2. 右上のユーザーアイコンをクリック → **Settings** を選択
3. 左メニューの **Your apps** タブをクリック
4. **+ Create new app** ボタンをクリック

> 直接 URL: https://miro.com/app/settings/user-profile/apps

### 1.2 アプリ名を入力

- **App name**: 任意の名前を入力（例: `swimlane-chart-generator`）

### 1.3 トークンの有効期限を選択

- **Expire user authorization token** チェックボックスが表示される
  - **チェックを外す（推奨: 開発・個人利用時）**: トークンが無期限になる（アプリをアンインストールするまで有効）
  - **チェックを入れる**: アクセストークンは 1 時間で期限切れ、リフレッシュトークンは 60 日で期限切れ

> 個人の開発・テスト用途であれば「チェックを外す（非期限切れ）」が簡単。
> 本番運用やセキュリティ要件がある場合は期限付きトークンを推奨。

### 1.4 アプリを作成

- **Create app** ボタンをクリック

---

## Step 2: スコープ（権限）を設定する

アプリ作成後、アプリの設定画面が表示される。

### 2.1 必要なスコープを有効化

**Permissions** セクションで以下のスコープにチェックを入れる:

| スコープ | 用途 |
|---|---|
| `boards:read` | ボード情報の読み取り（疎通確認に使用） |
| `boards:write` | ボードへのアイテム作成（Shape, Text, Connector） |

### 2.2 保存

設定変更後、ページ下部の **Save** ボタンをクリックして保存する。

---

## Step 3: アクセストークンを取得する

### 3.1 アプリをインストール

1. アプリ設定画面の下部にある **Install app and get OAuth token** をクリック
2. **Select a team** ドロップダウンから対象のチームを選択
3. **Install & authorize** をクリック

### 3.2 トークンを保存

- インストール成功後、**アクセストークン**が表示される
- このトークンを**安全な場所にコピーして保存**する
- 画面を閉じるとトークンは再表示されない（再発行は可能）

> **セキュリティ注意**:
> - トークンを Git リポジトリにコミットしない
> - `.env` ファイルで管理し、`.gitignore` に追加する
> - Slack やメール等で共有しない

---

## Step 4: ボード ID を取得する

### 4.1 対象ボードを開く

1. Miro でスイムレーンチャートを配置したいボードを開く（新規作成でも可）
2. ブラウザのアドレスバーから URL を確認する

### 4.2 URL からボード ID を抽出

URL 形式:
```
https://miro.com/app/board/<BOARD_ID>/
```

例:
```
https://miro.com/app/board/uXjVKxyz1234=/
```
この場合、ボード ID は `uXjVKxyz1234=`（`=` を含む場合はそれも含める）。

---

## Step 5: ローカル環境を構築する

### 5.1 プロジェクトディレクトリに移動

```bash
cd /path/to/swimlane-chart
```

### 5.2 Python 仮想環境を作成

```bash
python3 -m venv .venv
source .venv/bin/activate    # macOS / Linux
# .venv\Scripts\activate     # Windows
```

### 5.3 依存パッケージをインストール

```bash
pip install requests python-dotenv
```

### 5.4 .env ファイルを作成

プロジェクトルートに `.env` ファイルを作成し、トークンとボード ID を記入する:

```bash
MIRO_TOKEN=ここにアクセストークンを貼り付け
MIRO_BOARD_ID=ここにボードIDを貼り付け
```

### 5.5 .gitignore に追加

```bash
echo ".env" >> .gitignore
echo ".venv/" >> .gitignore
```

---

## Step 6: 疎通確認を行う

### 6.1 確認スクリプトを実行

以下のコマンドで Miro API への接続を確認する:

```bash
python3 -c "
import os
from dotenv import load_dotenv
import requests

load_dotenv()
token = os.environ['MIRO_TOKEN']
board_id = os.environ['MIRO_BOARD_ID']

# 1) ボード一覧の取得（認証確認）
r = requests.get(
    'https://api.miro.com/v2/boards',
    headers={'Authorization': f'Bearer {token}'}
)
print(f'GET /v2/boards -> {r.status_code}')
if r.status_code != 200:
    print(f'  Error: {r.text}')
    exit(1)

# 2) 対象ボードの情報取得
r2 = requests.get(
    f'https://api.miro.com/v2/boards/{board_id}',
    headers={'Authorization': f'Bearer {token}'}
)
print(f'GET /v2/boards/{board_id} -> {r2.status_code}')
if r2.status_code == 200:
    data = r2.json()
    print(f'  Board name: {data.get(\"name\", \"(unknown)\")}')
    print('  Connection OK')
else:
    print(f'  Error: {r2.text}')
"
```

### 6.2 期待される出力

```
GET /v2/boards -> 200
GET /v2/boards/uXjVKxyz1234= -> 200
  Board name: My Board
  Connection OK
```

### 6.3 トラブルシューティング

| HTTP ステータス | 原因 | 対処 |
|---|---|---|
| 401 Unauthorized | トークンが無効または期限切れ | Step 3 でトークンを再発行する |
| 403 Forbidden | スコープ不足 | Step 2 で `boards:read`, `boards:write` を確認する |
| 404 Not Found | ボード ID が不正 | Step 4 で URL からボード ID を再確認する |
| 429 Too Many Requests | レート制限超過 | 数秒待って再実行する |

---

## Step 7: Shape 1 個を作成して動作確認する

疎通確認が通ったら、実際にボード上にアイテムを 1 つ作成して確認する。

```bash
python3 -c "
import os
from dotenv import load_dotenv
import requests, json

load_dotenv()
token = os.environ['MIRO_TOKEN']
board_id = os.environ['MIRO_BOARD_ID']

payload = {
    'data': {'shape': 'rectangle', 'content': 'Hello Miro API'},
    'position': {'origin': 'center', 'x': 0, 'y': 0},
    'geometry': {'width': 200, 'height': 80},
    'style': {'fillColor': '#D5F5E3', 'borderColor': '#1a1a1a'}
}

r = requests.post(
    f'https://api.miro.com/v2/boards/{board_id}/shapes',
    headers={
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    },
    data=json.dumps(payload)
)
print(f'POST /v2/boards/{board_id}/shapes -> {r.status_code}')
if r.status_code == 201:
    item = r.json()
    print(f'  Created item ID: {item.get(\"id\")}')
    print('  Check your Miro board - a green rectangle should appear.')
else:
    print(f'  Error: {r.text}')
"
```

Miro ボードを開いて、緑色の矩形「Hello Miro API」が表示されていれば成功。

---

## Step 8: スイムレーンチャート生成スクリプトを実行する

### 8.1 スクリプトに dotenv を組み込む（必要に応じて）

現在の `swimlane_chart.py` は `os.environ` から直接読み取る設計のため、実行前に環境変数をエクスポートするか、スクリプトの冒頭に以下を追加する:

```python
from dotenv import load_dotenv
load_dotenv()
```

### 8.2 実行

```bash
# 方法 A: .env を使う場合（スクリプトに dotenv を組み込み済み）
python3 swimlane_chart.py

# 方法 B: 環境変数を直接指定する場合
MIRO_TOKEN="xxxxx" MIRO_BOARD_ID="yyyyy" python3 swimlane_chart.py
```

### 8.3 期待される出力

```
Done. Swimlane reproduced.
```

エラーが出た場合は Step 6.3 のトラブルシューティングを参照。

---

## 補足: レート制限について

Miro REST API はクレジットベースのレート制限を適用している。

| 項目 | 値 |
|---|---|
| グローバル上限 | 100,000 クレジット/分（ユーザー/アプリ単位） |
| Level 1 エンドポイント | 50 クレジット/回 = 最大 2,000 リクエスト/分 |
| 超過時 | HTTP 429 `tooManyRequests` が返却される |

このスクリプトで生成するアイテム数（約 30〜40 個 + コネクタ数本）であれば、レート制限に抵触する可能性は低い。大量のフロー図を連続生成する場合は、バッチ間に `time.sleep()` を挿入することを推奨する。

---

## 参考リンク

- [Miro Developer Platform](https://developers.miro.com/)
- [REST API Quickstart](https://developers.miro.com/docs/rest-api-build-your-first-hello-world-app)
- [OAuth 2.0 Guide](https://developers.miro.com/docs/getting-started-with-oauth)
- [Create Shape Item](https://developers.miro.com/reference/create-shape-item)
- [Create Connector](https://developers.miro.com/reference/create-connector)
- [Create Items in Bulk](https://developers.miro.com/reference/create-items)
- [Rate Limiting](https://developers.miro.com/reference/rate-limiting)
- [Work with Connectors](https://developers.miro.com/docs/work-with-connectors)
