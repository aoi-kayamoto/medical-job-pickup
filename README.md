# 🏥 メディフリ案件ピックアップツール

看護師・医療系のクラウドソーシング案件を毎日自動収集するツールです。  
CrowdWorks / Lancers / Coconala / Indeed から案件を取得し、看護師向けキーワードでフィルタリングして一覧表示します。

---

## 📋 必要なもの

- **Docker Desktop**（無料）のみ！Python は不要です。

### Docker Desktop のインストール
- Mac: https://docs.docker.com/desktop/install/mac-install/
- Windows: https://docs.docker.com/desktop/install/windows-install/
- Linux: https://docs.docker.com/desktop/install/linux-install/

---

## 🚀 起動方法

### 1. このフォルダをダウンロードして解凍する

### 2. Docker Desktop を起動する

### 3. 起動ファイルをダブルクリック

- **Mac** →「メディフリ案件ピックアップ.app」をダブルクリック  
- **Windows** →「起動.bat」をダブルクリック

> **⚠️ Mac の方へ（初回のみ）**  
> 「開発元を確認できません」と表示された場合：  
> 　① アプリを**右クリック**  
> 　② 「**開く**」を選択  
> 　③ ダイアログの「**開く**」をクリック  
> 　※ 2回目以降はダブルクリックで開きます

### 4. 初回は5〜10分待つ（自動でブラウザが開きます）

👉 **http://localhost:8765**

---

## 🔄 使い方

| 操作 | 方法 |
|---|---|
| 案件を今すぐ取得 | 画面右上「今すぐ取得」ボタンを押す |
| 自動取得 | 毎朝 **08:00** に自動実行 |
| ソースで絞り込み | 上部タブ（CrowdWorks / Lancers / Coconala / Indeed）|
| キーワード検索 | 検索バーに入力 |
| ブックマーク | カード右下の ☆ ボタン |
| 非表示 | カード右下の ✕ ボタン |

---

## ⏹ 停止方法

ターミナルで `Ctrl + C` を押す。  
次回は再度 `docker-compose up` で再開（データは保持されます）。

### バックグラウンドで動かし続けたい場合

```bash
docker-compose up -d          # バックグラウンド起動
docker-compose down           # 停止
docker-compose logs -f        # ログを見る
```

---

## 🗂 フォルダ構成

```
医療案件/
├── main.py           # サーバー本体
├── scrapers.py       # 各サイトのスクレイパー
├── keywords.py       # 看護師向けキーワード設定
├── database.py       # データ保存管理
├── index.html        # ダッシュボード画面
├── Dockerfile        # Docker ビルド設定
├── docker-compose.yml
└── data/             # DB ファイルが自動生成（削除しないこと）
```

---

## 🔑 キーワードをカスタマイズするには

`keywords.py` の `REQUIRED_KEYWORDS` リストを編集してください。

---

## ❓ よくある質問

**Q: ポート 8765 が使えないと言われる**  
A: `docker-compose.yml` の `"8765:8765"` を `"9000:8765"` などに変更してください。

**Q: どのくらいの頻度でデータが増える？**  
A: 各サイトの更新頻度によりますが、毎朝の自動取得で数件〜数十件程度。

**Q: Docker なしで動かしたい（Python がある場合）**  
```bash
pip install -r requirements.txt
python main.py
```
