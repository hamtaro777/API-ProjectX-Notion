"""
TopstepX API Client
ProjectX Gateway APIを使用してTopstepXに接続するクライアント
"""

import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List, Any
from pathlib import Path


def is_live_account(account_name: str) -> bool:
    """
    LIVE口座かどうかを判定

    LIVE口座はアカウント名に"TOPX"が含まれる

    Args:
        account_name: アカウント名

    Returns:
        LIVE口座の場合True
    """
    if not account_name:
        return False
    return 'TOPX' in account_name.upper()


def convert_orders_to_trades(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Order/searchのレスポンスをTrade形式に変換

    Order/searchにはprofitAndLoss情報がないため、
    ポジション追跡ロジックでエントリー/エグジットを判定

    Args:
        orders: Order/searchから取得したオーダーリスト

    Returns:
        Trade形式に変換されたリスト
    """
    trades = []
    # ポジション追跡用: contract_id -> list of (side, size, timestamp)
    position_tracker: Dict[str, List[Dict[str, Any]]] = {}

    # 時系列でソート
    sorted_orders = sorted(orders, key=lambda x: x.get('updateTimestamp', x.get('creationTimestamp', '')))

    for order in sorted_orders:
        contract_id = order.get('contractId', '')
        side = order.get('side')  # 0=BUY, 1=SELL
        size = order.get('fillVolume') or order.get('size', 0)
        filled_price = order.get('filledPrice') or order.get('avgFilledPrice', 0)

        if contract_id not in position_tracker:
            position_tracker[contract_id] = []

        # 現在のポジションを計算
        current_positions = position_tracker[contract_id]
        is_entry = True
        matched_pnl = None

        # 反対サイドのポジションがあるか確認（エグジット判定）
        for i, pos in enumerate(current_positions):
            if pos['side'] != side and pos['remaining'] > 0:
                # 反対ポジションがある = これはエグジット
                is_entry = False
                match_size = min(pos['remaining'], size)

                # P&L計算
                if side == 0:  # BUY（ショートクローズ）
                    pnl = (pos['price'] - filled_price) * match_size
                else:  # SELL（ロングクローズ）
                    pnl = (filled_price - pos['price']) * match_size

                # ティックサイズに応じたP&L調整（MNQ/MES等は特定の倍率）
                # 注意: これは概算。実際の倍率は契約によって異なる
                if 'MNQ' in contract_id or 'NQ' in contract_id:
                    pnl *= 2  # $2 per point
                elif 'MES' in contract_id or 'ES' in contract_id:
                    pnl *= 5  # $5 per point

                matched_pnl = pnl
                current_positions[i]['remaining'] -= match_size
                size -= match_size

                if size <= 0:
                    break

        # トレードデータを作成
        trade = {
            'id': order.get('id'),
            'orderId': order.get('id'),
            'contractId': contract_id,
            'side': order.get('side'),
            'size': order.get('fillVolume') or order.get('size', 0),
            'price': filled_price,
            'creationTimestamp': order.get('updateTimestamp') or order.get('creationTimestamp'),
            'profitAndLoss': matched_pnl,  # エントリーはNone、エグジットは計算値
            'fees': 0  # Order APIには手数料情報がない
        }
        trades.append(trade)

        # 新規エントリーの場合、ポジションに追加
        original_size = order.get('fillVolume') or order.get('size', 0)
        if is_entry or size > 0:  # 完全に決済されなかった場合も追加
            remaining_size = original_size if is_entry else size
            if remaining_size > 0:
                current_positions.append({
                    'side': order.get('side'),
                    'price': filled_price,
                    'remaining': remaining_size,
                    'timestamp': order.get('updateTimestamp')
                })

    return trades


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

    def get_order_history(
        self,
        account_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        オーダー履歴を取得（LIVE口座用）

        Args:
            account_id: アカウントID
            start_date: 開始日時（デフォルト: 30日前）
            end_date: 終了日時（デフォルト: 現在）

        Returns:
            オーダー情報のリスト（約定済みのみ）
        """
        url = f"{self.BASE_URL}/Order/search"

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

        print(f"   [DEBUG] Order search payload: {payload}")

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
            orders = data.get('orders', [])
            # 約定済み（status=2）のオーダーのみ返す
            filled_orders = [o for o in orders if o.get('status') == 2]
            print(f"   [DEBUG] Total orders: {len(orders)}, Filled: {len(filled_orders)}")
            return filled_orders
        else:
            error_msg = data.get('errorMessage', '不明なエラー')
            error_code = data.get('errorCode', 'unknown')
            raise Exception(f"オーダー履歴取得失敗 (code={error_code}): {error_msg}")

    def get_trade_data(
        self,
        account_id: int,
        account_name: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        口座タイプに応じてトレードデータを取得

        LIVE口座（TOPX）: Order/searchを使用
        その他: Trade/searchを使用

        Args:
            account_id: アカウントID
            account_name: アカウント名（口座タイプ判定に使用）
            start_date: 開始日時
            end_date: 終了日時

        Returns:
            Trade形式に統一されたトレードデータ
        """
        if is_live_account(account_name):
            print(f"   [INFO] LIVE口座検出: Order/search APIを使用")
            orders = self.get_order_history(account_id, start_date, end_date)
            return convert_orders_to_trades(orders)
        else:
            return self.get_trades(account_id, start_date, end_date)


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