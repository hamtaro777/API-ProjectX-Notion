"""
Notion API Client for Roundtrip Trades
往復トレードデータをNotionデータベースに登録するクライアント

Notionデータベースの推奨スキーマ:
=========================================
| プロパティ名    | タイプ      | 説明                    |
|----------------|------------|------------------------|
| Name           | Title      | ユニークID (自動生成)    |
| Account        | Select     | アカウント名             |
| Contract       | Select     | 契約シンボル (MNQ等)     |
| Direction      | Select     | LONG / SHORT           |
| Size           | Number     | 枚数                    |
| Entry Time     | Date       | エントリー日時           |
| Exit Time      | Date       | エグジット日時           |
| Entry Price    | Number     | エントリー価格           |
| Exit Price     | Number     | エグジット価格           |
| P&L            | Number     | 損益（手数料前）         |
| Net P&L        | Number     | 純損益（手数料後）       |
| Total Fees     | Number     | 合計手数料              |
| Points         | Number     | 獲得ポイント            |
| Duration       | Rich Text  | 保持時間                |
| Result         | Select     | WIN / LOSS / BE        |
| Entry Trade ID | Number     | エントリーTrade ID      |
| Exit Trade ID  | Number     | エグジットTrade ID      |
=========================================
"""

import json
import requests
from datetime import datetime
from typing import Optional, Dict, List, Any, Set
from pathlib import Path


class NotionRoundtripClient:
    """往復トレード用 Notion API クライアント"""
    
    BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"
    
    def __init__(self, api_key: str, database_id: str):
        """
        クライアントを初期化
        
        Args:
            api_key: Notion Integration Token
            database_id: NotionデータベースID
        """
        self.api_key = api_key
        self.database_id = database_id
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.NOTION_VERSION
        })
    
    def get_database(self) -> Dict[str, Any]:
        """データベース情報を取得"""
        url = f"{self.BASE_URL}/databases/{self.database_id}"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json()
    
    def query_database(
        self, 
        filter_obj: Optional[Dict] = None,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        データベースをクエリして既存のエントリを取得（ページネーション対応）
        """
        url = f"{self.BASE_URL}/databases/{self.database_id}/query"
        all_results = []
        has_more = True
        start_cursor = None
        
        while has_more:
            payload = {"page_size": page_size}
            if filter_obj:
                payload["filter"] = filter_obj
            if start_cursor:
                payload["start_cursor"] = start_cursor
            
            response = self.session.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            
            all_results.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        
        return all_results
    
    def get_existing_roundtrip_ids(self) -> Set[str]:
        """既存の往復トレードID（Entry Trade ID + Exit Trade ID）を取得"""
        pages = self.query_database()
        existing_ids = set()
        
        for page in pages:
            props = page.get("properties", {})
            
            # Entry Trade ID と Exit Trade ID の組み合わせでユニーク判定
            entry_id = props.get("Entry Trade ID", {}).get("number")
            exit_id = props.get("Exit Trade ID", {}).get("number")
            
            if entry_id and exit_id:
                unique_key = f"{entry_id}-{exit_id}"
                existing_ids.add(unique_key)
        
        return existing_ids
    
    def _truncate_account_name(self, name: str, max_length: int = 50) -> str:
        """アカウント名を短縮（Notionのselectオプション用）"""
        # EXPRESS-V2-140427-27209524 -> EXPRESS-V2-140427
        if len(name) > max_length:
            parts = name.split('-')
            if len(parts) >= 3:
                # 最後の部分（数字）を削除
                return '-'.join(parts[:-1])
        return name
    
    def create_roundtrip_entry(
        self, 
        roundtrip: Dict[str, Any], 
        account_name: str
    ) -> Dict[str, Any]:
        """
        往復トレードエントリを作成
        
        Args:
            roundtrip: 往復トレードデータ（RoundtripTransformerの出力形式）
            account_name: アカウント名
        
        Returns:
            作成されたページ情報
        """
        url = f"{self.BASE_URL}/pages"
        
        # 結果を判定
        pnl = roundtrip.get("pnl", 0)
        if pnl > 0:
            result = "WIN"
        elif pnl < 0:
            result = "LOSS"
        else:
            result = "BE"  # Breakeven
        
        # ユニークなタイトルを生成
        entry_info = roundtrip.get("entry", {})
        exit_info = roundtrip.get("exit", {})
        
        # タイトル: 日付_契約_方向_結果 (例: 1104_MNQ_LONG_WIN)
        exit_ts = exit_info.get("timestamp", "")
        date_part = exit_ts[5:10].replace("-", "") if exit_ts else "0000"  # MM-DD -> MMDD
        title = f"{date_part}_{roundtrip.get('contract')}_{roundtrip.get('direction')}_{result}"
        
        # プロパティを構築
        properties = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Account": {
                "select": {"name": self._truncate_account_name(account_name)}
            },
            "Contract": {
                "select": {"name": roundtrip.get("contract", "Other")}
            },
            "Direction": {
                "select": {"name": roundtrip.get("direction", "LONG")}
            },
            "Size": {
                "number": roundtrip.get("size", 1)
            },
            "Entry Price": {
                "number": entry_info.get("price", 0)
            },
            "Exit Price": {
                "number": exit_info.get("price", 0)
            },
            "P&L": {
                "number": roundtrip.get("pnl", 0)
            },
            "Net PnL": {
                "number": roundtrip.get("net_pnl", 0)
            },
            "Total Fees": {
                "number": roundtrip.get("total_fees", 0)
            },
            "Points": {
                "number": roundtrip.get("points", 0)
            },
            "Duration": {
                "rich_text": [{"text": {"content": roundtrip.get("duration_formatted", "")}}]
            },
            "Result": {
                "select": {"name": result}
            },
            "Entry Trade ID": {
                "number": entry_info.get("trade_id", 0)
            },
            "Exit Trade ID": {
                "number": exit_info.get("trade_id", 0)
            }
        }
        
        # Entry Time（日時）
        entry_ts = entry_info.get("timestamp")
        if entry_ts:
            properties["Entry Time"] = {
                "date": {"start": entry_ts}
            }
        
        # Exit Time（日時）
        exit_ts = exit_info.get("timestamp")
        if exit_ts:
            properties["Exit Time"] = {
                "date": {"start": exit_ts}
            }
        
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": properties
        }
        
        response = self.session.post(url, json=payload)
        
        if not response.ok:
            print(f"   [ERROR] {response.status_code}: {response.text}")
            response.raise_for_status()
        
        return response.json()
    
    def sync_roundtrips(
        self,
        roundtrips: List[Dict[str, Any]],
        account_name: str,
        skip_existing: bool = True
    ) -> Dict[str, int]:
        """
        往復トレードデータをNotionに同期
        
        Args:
            roundtrips: 往復トレードのリスト
            account_name: アカウント名
            skip_existing: 既存のトレードをスキップするか
        
        Returns:
            結果の統計 {"created": n, "skipped": m, "errors": e}
        """
        stats = {"created": 0, "skipped": 0, "errors": 0}
        
        # 既存のIDを取得
        existing_ids = set()
        if skip_existing:
            print("   既存のエントリを確認中...")
            existing_ids = self.get_existing_roundtrip_ids()
            print(f"   {len(existing_ids)} 件の既存エントリを検出")
        
        total = len(roundtrips)
        for i, rt in enumerate(roundtrips):
            # ユニークキーを生成
            entry_id = rt.get("entry", {}).get("trade_id", 0)
            exit_id = rt.get("exit", {}).get("trade_id", 0)
            unique_key = f"{entry_id}-{exit_id}"
            
            # 進捗表示
            if (i + 1) % 10 == 0 or i == 0:
                print(f"   処理中: {i + 1}/{total}")
            
            # 既存チェック
            if unique_key in existing_ids:
                stats["skipped"] += 1
                continue
            
            try:
                self.create_roundtrip_entry(rt, account_name)
                stats["created"] += 1
            except Exception as e:
                print(f"   [ERROR] Roundtrip {unique_key}: {e}")
                stats["errors"] += 1
        
        return stats


# 旧クライアントとの互換性のためエイリアス
NotionClient = NotionRoundtripClient


def load_credentials(path: str = "credentials.json") -> Dict[str, Any]:
    """
    認証情報を読み込む（新旧両フォーマットに対応）
    """
    creds_path = Path(path)
    if not creds_path.exists():
        raise FileNotFoundError(f"認証情報ファイルが見つかりません: {path}")
    
    with open(creds_path, 'r', encoding='utf-8') as f:
        creds = json.load(f)
    
    # 新フォーマット（topstepx/notion構造）
    if "topstepx" in creds and "notion" in creds:
        return creds
    
    # 旧フォーマット（フラットな構造）の場合
    return {
        "topstepx": {
            "username": creds.get("username"),
            "api_key": creds.get("api_key")
        },
        "notion": {
            "api_key": creds.get("notion_api_key"),
            "database_id": creds.get("notion_database_id")
        }
    }


def print_database_schema():
    """Notionデータベースの推奨スキーマを表示"""
    schema = """
╔══════════════════════════════════════════════════════════════╗
║           Notion Database Schema for Roundtrip Trades        ║
╠══════════════════════════════════════════════════════════════╣
║ Property        │ Type       │ Description                   ║
╠══════════════════════════════════════════════════════════════╣
║ Name            │ Title      │ 自動生成ID (MMDD_MNQ_LONG_WIN)║
║ Account         │ Select     │ アカウント名                   ║
║ Contract        │ Select     │ MNQ, MES, MGC, etc.           ║
║ Direction       │ Select     │ LONG / SHORT                  ║
║ Size            │ Number     │ 枚数                          ║
║ Entry Time      │ Date       │ エントリー日時                 ║
║ Exit Time       │ Date       │ エグジット日時                 ║
║ Entry Price     │ Number     │ エントリー価格                 ║
║ Exit Price      │ Number     │ エグジット価格                 ║
║ P&L             │ Number     │ 損益（手数料前）               ║
║ Net P&L         │ Number     │ 純損益（手数料後）             ║
║ Total Fees      │ Number     │ 合計手数料                    ║
║ Points          │ Number     │ 獲得ポイント                  ║
║ Duration        │ Text       │ 保持時間 (10分24秒)           ║
║ Result          │ Select     │ WIN / LOSS / BE               ║
║ Entry Trade ID  │ Number     │ エントリーのTrade ID          ║
║ Exit Trade ID   │ Number     │ エグジットのTrade ID          ║
╚══════════════════════════════════════════════════════════════╝

Select Options:
  - Account: アカウント名を追加
  - Contract: MNQ, MES, NQ, ES, MGC, MCL, GC, CL, Other
  - Direction: LONG, SHORT
  - Result: WIN, LOSS, BE
"""
    print(schema)


if __name__ == "__main__":
    print_database_schema()