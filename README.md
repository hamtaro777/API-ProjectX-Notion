# TopstepX → Notion 往復トレード同期ツール

TopstepXの取引データを自動でNotionデータベースに同期するGUIアプリケーション

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Mac%20%7C%20Linux-lightgrey.svg)

## ✨ 機能

- 🔄 TopstepXからトレードデータを自動取得
- 📊 片道トレード → 往復トレードに自動変換（FIFO方式）
- 📝 Notionデータベースへ自動登録
- ⏰ 定期自動同期モード（5分〜2時間間隔）
- 🎨 モダンなダークテーマUI
- 📈 勝率・損益・プロフィットファクター等の統計計算

## 📸 スクリーンショット

（スクリーンショットを追加予定）

## 🚀 セットアップ

### 1. リポジトリをクローン

```bash
git clone https://github.com/YOUR_USERNAME/topstepx-notion-sync.git
cd topstepx-notion-sync
```

### 2. 依存パッケージをインストール

```bash
pip install -r requirements.txt
```

### 3. 認証情報を設定

```bash
# テンプレートをコピー
cp credentials.example.json credentials.json

# credentials.json を編集して認証情報を入力
```

### 4. Notionデータベースを作成

以下のプロパティを持つデータベースを作成してください：

| プロパティ名 | タイプ | 説明 |
|-------------|-------|------|
| Name | Title | 自動生成ID |
| Account | Select | アカウント名 |
| Contract | Select | MNQ, MES, etc. |
| Direction | Select | LONG / SHORT |
| Size | Number | 枚数 |
| Entry Time | Date | エントリー日時 |
| Exit Time | Date | エグジット日時 |
| Entry Price | Number | エントリー価格 |
| Exit Price | Number | エグジット価格 |
| P&L | Number | 損益（税前） |
| Net PnL | Number | 純損益 |
| Total Fees | Number | 手数料 |
| Points | Number | 獲得ポイント |
| Duration | Text | 保持時間 |
| Result | Select | WIN / LOSS / BE |
| Entry Trade ID | Number | エントリーID |
| Exit Trade ID | Number | エグジットID |

### 5. Notion Integrationを接続

1. データベースを開く
2. 右上「...」→「Connections」
3. 作成したIntegrationを追加

## 💻 使い方

### GUIモード（推奨）

```bash
python main.py
```

### CLIモード

```bash
# 対話モード
python sync_to_notion.py

# 自動モード
python sync_to_notion.py --auto --days 7

# 全アカウント同期
python sync_to_notion.py --auto --all-accounts
```

## 🔑 APIキーの取得方法

### TopstepX API

1. [ProjectX Dashboard](https://dashboard.projectx.com) にログイン
2. 「Subscriptions」→「ProjectX API Access」を購読（無料）
3. 「Settings」→「API」でAPIキーを生成

### Notion API

1. [Notion Integrations](https://www.notion.so/my-integrations) にアクセス
2. 「New integration」をクリック
3. 名前を入力し、ワークスペースを選択
4. Internal Integration Token をコピー

## 📁 ファイル構成

```
topstepx-notion-sync/
├── main.py                  # GUIアプリケーション
├── sync_to_notion.py        # CLI版同期スクリプト
├── topstepx_client.py       # TopstepX APIクライアント
├── notion_client.py         # Notion APIクライアント
├── roundtrip_transformer.py # 往復トレード変換
├── fetch_trades.py          # トレード取得スクリプト
├── credentials.json         # 認証情報（要作成）
├── credentials.example.json # 認証情報テンプレート
├── requirements.txt         # 依存パッケージ
└── README.md
```

## 🔧 exeファイルの作成（オプション）

自分でexeを作成したい場合：

```bash
pip install pyinstaller

pyinstaller --onefile --windowed --name "TopstepX-Notion-Sync" \
    --collect-data customtkinter \
    main.py
```

## ⚠️ 免責事項

- **本ソフトウェアは無保証で提供されます**
- 本ソフトウェアの使用により生じたいかなる損害についても、作者は一切の責任を負いません
- APIキー等の認証情報の管理は利用者自身の責任で行ってください
- 本ソフトウェアは非公式ツールであり、TopstepX社およびNotion社とは一切関係ありません
- 取引に関する判断は自己責任で行ってください

## 📜 ライセンス

MIT License - 詳細は [LICENSE](LICENSE) を参照

## 🤝 コントリビューション

Issue、Pull Request歓迎です。

## 📞 サポート

- バグ報告: [GitHub Issues](https://github.com/YOUR_USERNAME/topstepx-notion-sync/issues)
- 質問: [GitHub Discussions](https://github.com/YOUR_USERNAME/topstepx-notion-sync/discussions)

---

**注意**: このツールを使用する前に、TopstepXおよびNotionの利用規約を確認してください。