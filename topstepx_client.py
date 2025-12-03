"""
TopstepX API Client
ProjectX Gateway APIを使用してTopstepXに接続するクライアント
"""

import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path


class TopstepXClient:
    """TopstepX API クライアント"""
    
    # TopstepX用のAPI URL
    BASE_URL = "https://api.topstepx.com/api"
    
    def __init__(self, credentials_path: str = "credentials.json"):
        """
        クライアントを初期化
        
        Args:
            credentials_path: 認証情報JSONファイルのパス
        """
        self.credentials_path = Path(credentials_path)
        self.username: Optional[str] = None
        self.api_key: Optional[str] = None
        self.session_token: Optional[str] = None
        self.session = requests.Session()
        
        # 認証情報を読み込み
        self._load_credentials()
    
    def _load_credentials(self) -> None:
        """認証情報をJSONファイルから読み込む"""
        if not self.credentials_path.exists():
            raise FileNotFoundError(
                f"認証情報ファイルが見つかりません: {self.credentials_path}\n"
                f"credentials.example.json を参考に credentials.json を作成してください。"
            )
        
        with open(self.credentials_path, 'r', encoding='utf-8') as f:
            creds = json.load(f)
        
        self.username = creds.get('username')
        self.api_key = creds.get('api_key')
        
        if not self.username or not self.api_key:
            raise ValueError("認証情報ファイルに username と api_key が必要です")
    
    def authenticate(self) -> Dict[str, Any]:
        """
        APIキーを使用して認証し、セッショントークンを取得
        
        Returns:
            認証レスポンス
        """
        url = f"{self.BASE_URL}/Auth/loginKey"
        payload = {
            "userName": self.username,
            "apiKey": self.api_key
        }
        
        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            self.session_token = data.get('token')
            # 以降のリクエストにトークンを設定
            self.session.headers.update({
                "Authorization": f"Bearer {self.session_token}"
            })
            print("✅ 認証成功")
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            raise Exception(f"認証失敗: {error_msg}")
        
        return data
    
    def get_accounts(self) -> List[Dict[str, Any]]:
        """
        利用可能なアカウント一覧を取得
        
        Returns:
            アカウント情報のリスト
        """
        url = f"{self.BASE_URL}/Account/search"
        
        response = self.session.post(
            url,
            json={},
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            return data.get('accounts', [])
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            raise Exception(f"アカウント取得失敗: {error_msg}")
    
    def get_trades(
        self,
        account_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        トレード履歴を取得
        
        Args:
            account_id: アカウントID
            start_date: 開始日時（デフォルト: 30日前）
            end_date: 終了日時（デフォルト: 現在）
        
        Returns:
            トレード情報のリスト
        """
        url = f"{self.BASE_URL}/Trade/search"
        
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now(timezone.utc)
        
        # ISO 8601形式（Z形式）に変換
        def to_iso_z(dt: datetime) -> str:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        
        payload = {
            "accountId": account_id,
            "startTimestamp": to_iso_z(start_date),
            "endTimestamp": to_iso_z(end_date)
        }
        
        print(f"   [DEBUG] Trade search payload: {payload}")
        
        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        
        # エラーの場合、詳細を表示
        if not response.ok:
            print(f"   [DEBUG] Response status: {response.status_code}")
            print(f"   [DEBUG] Response body: {response.text}")
            response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            return data.get('trades', [])
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            error_code = data.get('errorCode', 'unknown')
            raise Exception(f"トレード取得失敗 (code={error_code}): {error_msg}")
    
    def get_positions(self, account_id: int) -> List[Dict[str, Any]]:
        """
        現在のポジションを取得
        
        Args:
            account_id: アカウントID
        
        Returns:
            ポジション情報のリスト
        """
        url = f"{self.BASE_URL}/Position/search"
        
        payload = {
            "accountId": account_id
        }
        
        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            return data.get('positions', [])
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            raise Exception(f"ポジション取得失敗: {error_msg}")
    
    def get_orders(self, account_id: int) -> List[Dict[str, Any]]:
        """
        オープンオーダーを取得
        
        Args:
            account_id: アカウントID
        
        Returns:
            オーダー情報のリスト
        """
        url = f"{self.BASE_URL}/Order/search"
        
        payload = {
            "accountId": account_id
        }
        
        response = self.session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('success'):
            return data.get('orders', [])
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            raise Exception(f"オーダー取得失敗: {error_msg}")


def format_trade(trade: Dict[str, Any]) -> str:
    """トレード情報を読みやすい形式でフォーマット"""
    side = "BUY" if trade.get('side') == 0 else "SELL"
    pnl = trade.get('profitAndLoss')
    pnl_str = f"${pnl:.2f}" if pnl is not None else "ハーフターン"
    
    return (
        f"  ID: {trade.get('id')}\n"
        f"  Contract: {trade.get('contractId')}\n"
        f"  Side: {side}\n"
        f"  Size: {trade.get('size')}\n"
        f"  Price: {trade.get('price')}\n"
        f"  P&L: {pnl_str}\n"
        f"  Fees: ${trade.get('fees', 0):.2f}\n"
        f"  Time: {trade.get('creationTimestamp')}\n"
    )