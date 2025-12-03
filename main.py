#!/usr/bin/env python3
"""
TopstepX → Notion 同期 GUI アプリケーション（モダンUI版）
CustomTkinterを使用したダークモードのスタイリッシュなデザイン

インストール:
  pip install customtkinter

機能:
- 手動同期（単一/全アカウント）
- 自動同期モード（定期実行）
- リアルタイムログ表示
- 認証情報の設定・保存
- 自動同期設定の保存・復元
"""

import json
import sys
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

# CustomTkinterのインストールチェック
try:
    import customtkinter as ctk
except ImportError:
    print("=" * 60)
    print("CustomTkinter が必要です。以下のコマンドでインストールしてください:")
    print()
    print("  pip install customtkinter")
    print()
    print("=" * 60)
    sys.exit(1)

import tkinter as tk
from tkinter import messagebox

# 現在のスクリプトのディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from topstepx_client import TopstepXClient
from notion_client import NotionRoundtripClient, load_credentials
from roundtrip_transformer import RoundtripTransformer


# カラーテーマ
class Theme:
    # 背景色
    BG_DARK = "#0d1117"
    BG_SECONDARY = "#161b22"
    BG_CARD = "#21262d"
    BG_INPUT = "#0d1117"
    
    # アクセントカラー
    PRIMARY = "#238636"
    PRIMARY_HOVER = "#2ea043"
    SECONDARY = "#1f6feb"
    SECONDARY_HOVER = "#388bfd"
    DANGER = "#da3633"
    WARNING = "#d29922"
    
    # テキスト
    TEXT_PRIMARY = "#f0f6fc"
    TEXT_SECONDARY = "#8b949e"
    TEXT_MUTED = "#6e7681"
    
    # ボーダー
    BORDER = "#30363d"
    BORDER_ACTIVE = "#58a6ff"
    
    # ステータス
    SUCCESS = "#3fb950"
    ERROR = "#f85149"
    INFO = "#58a6ff"


class ModernButton(ctk.CTkButton):
    """モダンなボタンコンポーネント"""
    
    def __init__(self, master, variant="primary", **kwargs):
        colors = {
            "primary": (Theme.PRIMARY, Theme.PRIMARY_HOVER),
            "secondary": (Theme.SECONDARY, Theme.SECONDARY_HOVER),
            "danger": (Theme.DANGER, "#b62324"),
            "ghost": (Theme.BG_CARD, Theme.BORDER),
        }
        
        fg_color, hover_color = colors.get(variant, colors["primary"])
        
        # heightが指定されていなければデフォルト値を使用
        if "height" not in kwargs:
            kwargs["height"] = 36
        
        super().__init__(
            master,
            fg_color=fg_color,
            hover_color=hover_color,
            corner_radius=8,
            border_width=0,
            font=ctk.CTkFont(size=13, weight="bold"),
            **kwargs
        )


class ModernCard(ctk.CTkFrame):
    """カード風のコンテナ"""
    
    def __init__(self, master, title=None, **kwargs):
        super().__init__(
            master,
            fg_color=Theme.BG_CARD,
            corner_radius=12,
            border_width=1,
            border_color=Theme.BORDER,
            **kwargs
        )
        
        if title:
            self.title_label = ctk.CTkLabel(
                self,
                text=title,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color=Theme.TEXT_PRIMARY,
                anchor="w"
            )
            self.title_label.pack(fill="x", padx=16, pady=(16, 12))
            
            # セパレータ
            separator = ctk.CTkFrame(self, height=1, fg_color=Theme.BORDER)
            separator.pack(fill="x", padx=16)
        
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.pack(fill="both", expand=True, padx=16, pady=16)


class StatusBadge(ctk.CTkFrame):
    """ステータスバッジ"""
    
    def __init__(self, master, text="", status="info", **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            **kwargs
        )
        
        self.indicator = ctk.CTkFrame(
            self,
            width=8,
            height=8,
            corner_radius=4,
            fg_color=Theme.TEXT_MUTED
        )
        self.indicator.pack(side="left", padx=(0, 8))
        
        self.label = ctk.CTkLabel(
            self,
            text=text,
            font=ctk.CTkFont(size=13),
            text_color=Theme.TEXT_SECONDARY
        )
        self.label.pack(side="left")
    
    def set_status(self, text, status="info"):
        colors = {
            "success": Theme.SUCCESS,
            "error": Theme.ERROR,
            "warning": Theme.WARNING,
            "info": Theme.INFO,
            "muted": Theme.TEXT_MUTED
        }
        self.label.configure(text=text)
        self.indicator.configure(fg_color=colors.get(status, Theme.TEXT_MUTED))


class LogDisplay(ctk.CTkTextbox):
    """モダンなログ表示"""
    
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=Theme.BG_DARK,
            text_color=Theme.TEXT_SECONDARY,
            font=ctk.CTkFont(family="Consolas", size=12),
            corner_radius=8,
            border_width=1,
            border_color=Theme.BORDER,
            **kwargs
        )
        self.configure(state="disabled")
        
        # タグ設定
        self._textbox.tag_configure("success", foreground=Theme.SUCCESS)
        self._textbox.tag_configure("error", foreground=Theme.ERROR)
        self._textbox.tag_configure("warning", foreground=Theme.WARNING)
        self._textbox.tag_configure("info", foreground=Theme.TEXT_SECONDARY)
        self._textbox.tag_configure("auto", foreground=Theme.INFO)
        self._textbox.tag_configure("timestamp", foreground=Theme.TEXT_MUTED)
    
    def log(self, message: str, level: str = "info"):
        self.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self._textbox.insert("end", f"[{timestamp}] ", "timestamp")
        self._textbox.insert("end", f"{message}\n", level)
        self._textbox.see("end")
        self.configure(state="disabled")
    
    def clear(self):
        self.configure(state="normal")
        self._textbox.delete("1.0", "end")
        self.configure(state="disabled")


class SettingsDialog(ctk.CTkToplevel):
    """設定ダイアログ"""
    
    CREDENTIALS_PATH = "credentials.json"
    
    def __init__(self, parent, on_save_callback=None):
        super().__init__(parent)
        
        self.on_save_callback = on_save_callback
        
        self.title("設定")
        self.geometry("520x700")
        self.resizable(True, True)
        self.minsize(400, 500)
        
        # モーダル設定
        self.transient(parent)
        self.grab_set()
        
        # 背景色
        self.configure(fg_color=Theme.BG_DARK)
        
        # 中央に配置
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 520) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 700) // 2
        self.geometry(f"520x700+{x}+{y}")
        
        # 表示/非表示の状態
        self.show_apikey = False
        self.show_notion_apikey = False
        
        self.create_widgets()
        self.load_settings()
    
    def create_widgets(self):
        # ボタン行を先に下部に配置（固定）
        btn_frame = ctk.CTkFrame(self, fg_color=Theme.BG_SECONDARY, height=60)
        btn_frame.pack(side="bottom", fill="x", padx=0, pady=0)
        btn_frame.pack_propagate(False)
        
        btn_inner = ctk.CTkFrame(btn_frame, fg_color="transparent")
        btn_inner.pack(expand=True, pady=10)
        
        ModernButton(btn_inner, text="保存", variant="secondary", width=80, command=self.save_only).pack(side="left", padx=5)
        ModernButton(btn_inner, text="保存して接続", variant="primary", width=130, command=self.save_and_connect).pack(side="left", padx=5)
        ModernButton(btn_inner, text="キャンセル", variant="ghost", width=100, command=self.destroy).pack(side="left", padx=5)
        
        # スクロール可能なメインコンテナ
        self.scrollable_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Theme.BORDER,
            scrollbar_button_hover_color=Theme.TEXT_MUTED
        )
        self.scrollable_frame.pack(fill="both", expand=True, padx=20, pady=(16, 10))
        
        main = self.scrollable_frame
        
        # タイトル
        ctk.CTkLabel(
            main,
            text="⚙️ 設定",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", pady=(0, 16))
        
        # === TopstepX設定 ===
        topstepx_header = ctk.CTkFrame(main, fg_color=Theme.BG_CARD, corner_radius=8)
        topstepx_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            topstepx_header,
            text="  TopstepX API",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", pady=8)
        
        # Username
        ctk.CTkLabel(main, text="Username", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY).pack(anchor="w", pady=(8, 0))
        self.username_entry = ctk.CTkEntry(main, height=38, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER, corner_radius=6, placeholder_text="TopstepXのユーザー名")
        self.username_entry.pack(fill="x", pady=(4, 8))
        
        # API Key行
        apikey_row = ctk.CTkFrame(main, fg_color="transparent")
        apikey_row.pack(fill="x")
        ctk.CTkLabel(apikey_row, text="API Key", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY).pack(side="left")
        self.show_apikey_btn = ctk.CTkButton(apikey_row, text="表示", font=ctk.CTkFont(size=10), width=50, height=22,
            fg_color="transparent", hover_color=Theme.BG_CARD, text_color=Theme.TEXT_MUTED, command=self.toggle_apikey_visibility)
        self.show_apikey_btn.pack(side="right")
        
        self.apikey_entry = ctk.CTkEntry(main, height=38, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER, corner_radius=6, show="•", placeholder_text="APIキー")
        self.apikey_entry.pack(fill="x", pady=(4, 8))
        
        # TopstepX接続テスト
        ModernButton(main, text="🔗 接続テスト", variant="secondary", width=130, height=32, command=self.test_topstepx).pack(anchor="w", pady=(4, 16))
        
        # 区切り線
        ctk.CTkFrame(main, height=1, fg_color=Theme.BORDER).pack(fill="x", pady=(0, 16))
        
        # === Notion設定 ===
        notion_header = ctk.CTkFrame(main, fg_color=Theme.BG_CARD, corner_radius=8)
        notion_header.pack(fill="x", pady=(0, 4))
        ctk.CTkLabel(
            notion_header,
            text="  Notion API",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w", pady=8)
        
        # Integration Token行
        token_row = ctk.CTkFrame(main, fg_color="transparent")
        token_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(token_row, text="Integration Token", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY).pack(side="left")
        self.show_notion_apikey_btn = ctk.CTkButton(token_row, text="表示", font=ctk.CTkFont(size=10), width=50, height=22,
            fg_color="transparent", hover_color=Theme.BG_CARD, text_color=Theme.TEXT_MUTED, command=self.toggle_notion_apikey_visibility)
        self.show_notion_apikey_btn.pack(side="right")
        
        self.notion_apikey_entry = ctk.CTkEntry(main, height=38, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER, corner_radius=6, show="•", placeholder_text="ntn_xxxx...")
        self.notion_apikey_entry.pack(fill="x", pady=(4, 8))
        
        # Database ID
        ctk.CTkLabel(main, text="Database ID", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_SECONDARY).pack(anchor="w")
        self.dbid_entry = ctk.CTkEntry(main, height=38, fg_color=Theme.BG_INPUT, border_color=Theme.BORDER, corner_radius=6, placeholder_text="データベースID")
        self.dbid_entry.pack(fill="x", pady=(4, 2))
        ctk.CTkLabel(main, text="💡 URLの https://notion.so/xxxxx?v=... の xxxxx 部分", font=ctk.CTkFont(size=10), text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0, 8))
        
        # Notion接続テスト
        ModernButton(main, text="🔗 接続テスト", variant="secondary", width=130, height=32, command=self.test_notion).pack(anchor="w", pady=(4, 16))
        
        # ステータス表示エリア
        status_frame = ctk.CTkFrame(main, fg_color=Theme.BG_SECONDARY, corner_radius=8)
        status_frame.pack(fill="x", pady=(8, 0))
        self.status_label = ctk.CTkLabel(status_frame, text="設定を入力してください", font=ctk.CTkFont(size=12), text_color=Theme.TEXT_MUTED)
        self.status_label.pack(pady=12)
    
    def toggle_apikey_visibility(self):
        """TopstepX APIキーの表示/非表示を切り替え"""
        self.show_apikey = not self.show_apikey
        if self.show_apikey:
            self.apikey_entry.configure(show="")
            self.show_apikey_btn.configure(text="隠す")
        else:
            self.apikey_entry.configure(show="•")
            self.show_apikey_btn.configure(text="表示")
    
    def toggle_notion_apikey_visibility(self):
        """Notion APIキーの表示/非表示を切り替え"""
        self.show_notion_apikey = not self.show_notion_apikey
        if self.show_notion_apikey:
            self.notion_apikey_entry.configure(show="")
            self.show_notion_apikey_btn.configure(text="隠す")
        else:
            self.notion_apikey_entry.configure(show="•")
            self.show_notion_apikey_btn.configure(text="表示")
    
    def test_topstepx(self):
        """TopstepX接続テスト"""
        username = self.username_entry.get().strip()
        api_key = self.apikey_entry.get().strip()
        
        if not username or not api_key:
            self.status_label.configure(text="✗ UsernameとAPI Keyを入力してください", text_color=Theme.ERROR)
            return
        
        self.status_label.configure(text="🔄 TopstepX接続テスト中...", text_color=Theme.INFO)
        self.update()
        
        def test():
            try:
                import requests
                topstepx = TopstepXClient.__new__(TopstepXClient)
                topstepx.username = username
                topstepx.api_key = api_key
                topstepx.session_token = None
                topstepx.session = requests.Session()
                topstepx.BASE_URL = "https://api.topstepx.com/api"
                topstepx.authenticate()
                
                self.after(0, lambda: self.status_label.configure(
                    text="✓ TopstepX接続成功!", text_color=Theme.SUCCESS
                ))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"✗ TopstepX接続失敗: {str(e)[:40]}", text_color=Theme.ERROR
                ))
        
        threading.Thread(target=test, daemon=True).start()
    
    def test_notion(self):
        """Notion接続テスト"""
        api_key = self.notion_apikey_entry.get().strip()
        database_id = self.dbid_entry.get().strip()
        
        if not api_key or not database_id:
            self.status_label.configure(text="✗ API KeyとDatabase IDを入力してください", text_color=Theme.ERROR)
            return
        
        self.status_label.configure(text="🔄 Notion接続テスト中...", text_color=Theme.INFO)
        self.update()
        
        def test():
            try:
                notion = NotionRoundtripClient(api_key=api_key, database_id=database_id)
                db_info = notion.get_database()
                db_title = db_info.get('title', [{}])[0].get('plain_text', 'Database')
                
                self.after(0, lambda: self.status_label.configure(
                    text=f"✓ Notion接続成功: {db_title}", text_color=Theme.SUCCESS
                ))
            except Exception as e:
                self.after(0, lambda: self.status_label.configure(
                    text=f"✗ Notion接続失敗: {str(e)[:40]}", text_color=Theme.ERROR
                ))
        
        threading.Thread(target=test, daemon=True).start()
    
    def save_only(self):
        """保存のみ（接続はしない）"""
        if self.save_settings():
            self.status_label.configure(text="✓ 設定を保存しました", text_color=Theme.SUCCESS)
    
    def load_settings(self):
        try:
            if Path(self.CREDENTIALS_PATH).exists():
                with open(self.CREDENTIALS_PATH, 'r', encoding='utf-8') as f:
                    creds = json.load(f)
                
                # 入力欄をクリア
                self.username_entry.delete(0, "end")
                self.apikey_entry.delete(0, "end")
                self.notion_apikey_entry.delete(0, "end")
                self.dbid_entry.delete(0, "end")
                
                # 新フォーマット（topstepx/notion構造）
                if "topstepx" in creds:
                    self.username_entry.insert(0, creds.get("topstepx", {}).get("username", ""))
                    self.apikey_entry.insert(0, creds.get("topstepx", {}).get("api_key", ""))
                    self.notion_apikey_entry.insert(0, creds.get("notion", {}).get("api_key", ""))
                    self.dbid_entry.insert(0, creds.get("notion", {}).get("database_id", ""))
                else:
                    # 旧フォーマット（フラットな構造）
                    self.username_entry.insert(0, creds.get("username", ""))
                    self.apikey_entry.insert(0, creds.get("api_key", ""))
                    self.notion_apikey_entry.insert(0, creds.get("notion_api_key", ""))
                    self.dbid_entry.insert(0, creds.get("notion_database_id", ""))
                
                self.status_label.configure(text="✓ 設定を読み込みました", text_color=Theme.SUCCESS)
            else:
                self.status_label.configure(text="⚠ credentials.json が見つかりません（新規作成）", text_color=Theme.WARNING)
        except Exception as e:
            self.status_label.configure(text=f"✗ 読み込みエラー: {e}", text_color=Theme.ERROR)
    
    def save_settings(self) -> bool:
        if not all([
            self.username_entry.get().strip(),
            self.apikey_entry.get().strip(),
            self.notion_apikey_entry.get().strip(),
            self.dbid_entry.get().strip()
        ]):
            self.status_label.configure(text="✗ すべてのフィールドを入力してください", text_color=Theme.ERROR)
            return False
        
        creds = {
            "topstepx": {
                "username": self.username_entry.get().strip(),
                "api_key": self.apikey_entry.get().strip()
            },
            "notion": {
                "api_key": self.notion_apikey_entry.get().strip(),
                "database_id": self.dbid_entry.get().strip()
            }
        }
        
        try:
            with open(self.CREDENTIALS_PATH, 'w', encoding='utf-8') as f:
                json.dump(creds, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            self.status_label.configure(text=f"✗ 保存エラー: {e}", text_color=Theme.ERROR)
            return False
    
    def save_and_connect(self):
        if self.save_settings():
            self.destroy()
            if self.on_save_callback:
                self.on_save_callback()


class AutoSyncManager:
    """自動同期マネージャー"""
    
    def __init__(self, callback):
        self.callback = callback
        self.is_running = False
        self.interval_minutes = 30
        self.next_sync_time: Optional[datetime] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
    
    def start(self, interval_minutes: int):
        if self.is_running:
            return
        
        self.interval_minutes = interval_minutes
        self.is_running = True
        self.stop_event.clear()
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
    
    def stop(self):
        self.is_running = False
        self.stop_event.set()
        self.next_sync_time = None
    
    def _run_loop(self):
        while self.is_running and not self.stop_event.is_set():
            self.next_sync_time = datetime.now() + timedelta(minutes=self.interval_minutes)
            
            wait_seconds = self.interval_minutes * 60
            for _ in range(wait_seconds):
                if self.stop_event.is_set():
                    return
                time.sleep(1)
            
            if self.is_running and not self.stop_event.is_set():
                self.callback()
    
    def get_remaining_time(self) -> str:
        if not self.next_sync_time:
            return "--:--"
        
        remaining = self.next_sync_time - datetime.now()
        if remaining.total_seconds() <= 0:
            return "同期中..."
        
        minutes = int(remaining.total_seconds() // 60)
        seconds = int(remaining.total_seconds() % 60)
        return f"{minutes:02d}:{seconds:02d}"


class SyncApp(ctk.CTk):
    """TopstepX → Notion 同期 GUIアプリ"""
    
    SYNC_SETTINGS_PATH = "sync_settings.json"
    
    def __init__(self):
        super().__init__()
        
        # ウィンドウ設定
        self.title("TopstepX → Notion Sync")
        self.geometry("900x750")
        self.minsize(800, 650)
        
        # テーマ設定
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=Theme.BG_DARK)

        # アイコン設定
        icon_path = os.path.join(os.path.dirname(__file__), "app_icon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)
        
        # 状態
        self.topstepx: Optional[TopstepXClient] = None
        self.notion: Optional[NotionRoundtripClient] = None
        self.accounts: List[Dict] = []
        self.is_syncing = False
        
        # 自動同期マネージャー
        self.auto_sync = AutoSyncManager(callback=self._auto_sync_callback)
        
        # UI構築
        self.create_widgets()
        
        # タイマー更新
        self.update_timer()
        
        # 認証情報の自動読み込み
        self.after(100, self.auto_load_credentials)
        
        # 終了時の処理
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def create_widgets(self):
        # スクロール可能なメインコンテナ
        main_scroll = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Theme.BORDER,
            scrollbar_button_hover_color=Theme.TEXT_MUTED
        )
        main_scroll.pack(fill="both", expand=True, padx=24, pady=24)
        
        # ヘッダー
        header = ctk.CTkFrame(main_scroll, fg_color="transparent")
        header.pack(fill="x", pady=(0, 24))
        
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left")
        
        ctk.CTkLabel(
            title_frame,
            text="🔄 TopstepX → Notion",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=Theme.TEXT_PRIMARY
        ).pack(anchor="w")
        
        ctk.CTkLabel(
            title_frame,
            text="トレードデータ同期ツール",
            font=ctk.CTkFont(size=14),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", pady=(4, 0))
        
        ModernButton(
            header,
            text="⚙️ 設定",
            variant="ghost",
            width=90,
            command=self.open_settings
        ).pack(side="right")
        
        # 接続状態カード
        status_card = ModernCard(main_scroll, title="📡 接続状態")
        status_card.pack(fill="x", pady=(0, 16))
        
        status_grid = ctk.CTkFrame(status_card.content, fg_color="transparent")
        status_grid.pack(fill="x")
        
        # TopstepX
        ts_frame = ctk.CTkFrame(status_grid, fg_color="transparent")
        ts_frame.pack(side="left", expand=True, fill="x")
        
        ctk.CTkLabel(
            ts_frame,
            text="TopstepX",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        self.topstepx_status = StatusBadge(ts_frame, text="未接続", status="muted")
        self.topstepx_status.pack(anchor="w", pady=(4, 0))
        
        # Notion
        notion_frame = ctk.CTkFrame(status_grid, fg_color="transparent")
        notion_frame.pack(side="left", expand=True, fill="x")
        
        ctk.CTkLabel(
            notion_frame,
            text="Notion",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        self.notion_status = StatusBadge(notion_frame, text="未接続", status="muted")
        self.notion_status.pack(anchor="w", pady=(4, 0))
        
        # 接続ボタン
        btn_frame = ctk.CTkFrame(status_card.content, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(16, 0))
        
        self.connect_btn = ModernButton(
            btn_frame,
            text="🔐 接続",
            variant="secondary",
            width=100,
            command=self.connect
        )
        self.connect_btn.pack(side="left")
        
        ModernButton(
            btn_frame,
            text="🔄 再読込",
            variant="ghost",
            width=100,
            command=self.reload_accounts
        ).pack(side="left", padx=(8, 0))
        
        # 同期設定カード
        sync_card = ModernCard(main_scroll, title="⚡ 同期設定")
        sync_card.pack(fill="x", pady=(0, 16))
        
        # アカウント選択
        ctk.CTkLabel(
            sync_card.content,
            text="アカウント",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        self.account_var = ctk.StringVar()
        self.account_combo = ctk.CTkComboBox(
            sync_card.content,
            variable=self.account_var,
            height=40,
            fg_color=Theme.BG_INPUT,
            border_color=Theme.BORDER,
            button_color=Theme.BORDER,
            button_hover_color=Theme.TEXT_MUTED,
            dropdown_fg_color=Theme.BG_CARD,
            dropdown_hover_color=Theme.BORDER,
            corner_radius=8,
            state="readonly"
        )
        self.account_combo.pack(fill="x", pady=(4, 16))
        
        # 期間選択
        ctk.CTkLabel(
            sync_card.content,
            text="期間",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        period_frame = ctk.CTkFrame(sync_card.content, fg_color="transparent")
        period_frame.pack(fill="x", pady=(4, 0))
        
        self.period_var = ctk.StringVar(value="7")
        periods = [("1日", "1"), ("7日間", "7"), ("30日間", "30"), ("90日間", "90")]
        
        for text, value in periods:
            ctk.CTkRadioButton(
                period_frame,
                text=text,
                variable=self.period_var,
                value=value,
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
                border_color=Theme.BORDER,
                text_color=Theme.TEXT_SECONDARY
            ).pack(side="left", padx=(0, 16))
        
        # 手動同期ボタン
        manual_frame = ctk.CTkFrame(sync_card.content, fg_color="transparent")
        manual_frame.pack(fill="x", pady=(20, 0))
        
        self.sync_btn = ModernButton(
            manual_frame,
            text="📤 同期開始",
            variant="primary",
            width=140,
            command=self.start_sync
        )
        self.sync_btn.pack(side="left")
        
        self.sync_all_btn = ModernButton(
            manual_frame,
            text="📤 全アカウント",
            variant="ghost",
            width=140,
            command=self.start_sync_all
        )
        self.sync_all_btn.pack(side="left", padx=(8, 0))
        
        # プログレスバー
        self.progress = ctk.CTkProgressBar(
            manual_frame,
            mode="indeterminate",
            progress_color=Theme.PRIMARY,
            fg_color=Theme.BORDER,
            height=6,
            corner_radius=3
        )
        self.progress.pack(side="right", fill="x", expand=True, padx=(16, 0))
        self.progress.set(0)
        
        # 自動同期カード
        auto_card = ModernCard(main_scroll, title="⏰ 自動同期")
        auto_card.pack(fill="x", pady=(0, 16))
        
        # 間隔選択
        ctk.CTkLabel(
            auto_card.content,
            text="同期間隔",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        interval_frame = ctk.CTkFrame(auto_card.content, fg_color="transparent")
        interval_frame.pack(fill="x", pady=(4, 16))
        
        self.interval_var = ctk.StringVar(value="30")
        intervals = [("5分", "5"), ("15分", "15"), ("30分", "30"), ("1時間", "60")]
        
        for text, value in intervals:
            ctk.CTkRadioButton(
                interval_frame,
                text=text,
                variable=self.interval_var,
                value=value,
                fg_color=Theme.SECONDARY,
                hover_color=Theme.SECONDARY_HOVER,
                border_color=Theme.BORDER,
                text_color=Theme.TEXT_SECONDARY
            ).pack(side="left", padx=(0, 16))
        
        # 自動同期対象
        ctk.CTkLabel(
            auto_card.content,
            text="同期対象",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")
        
        target_frame = ctk.CTkFrame(auto_card.content, fg_color="transparent")
        target_frame.pack(fill="x", pady=(4, 16))
        
        self.auto_target_var = ctk.StringVar(value="selected")
        
        ctk.CTkRadioButton(
            target_frame,
            text="選択中のアカウント",
            variable=self.auto_target_var,
            value="selected",
            fg_color=Theme.SECONDARY,
            hover_color=Theme.SECONDARY_HOVER,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left", padx=(0, 16))
        
        ctk.CTkRadioButton(
            target_frame,
            text="全アカウント",
            variable=self.auto_target_var,
            value="all",
            fg_color=Theme.SECONDARY,
            hover_color=Theme.SECONDARY_HOVER,
            border_color=Theme.BORDER,
            text_color=Theme.TEXT_SECONDARY
        ).pack(side="left")
        
        # 自動同期コントロール
        auto_control = ctk.CTkFrame(auto_card.content, fg_color="transparent")
        auto_control.pack(fill="x")
        
        self.auto_start_btn = ModernButton(
            auto_control,
            text="▶️ 開始",
            variant="secondary",
            width=100,
            command=self.start_auto_sync
        )
        self.auto_start_btn.pack(side="left")
        
        self.auto_stop_btn = ModernButton(
            auto_control,
            text="⏹️ 停止",
            variant="danger",
            width=100,
            command=self.stop_auto_sync
        )
        self.auto_stop_btn.pack(side="left", padx=(8, 0))
        self.auto_stop_btn.configure(state="disabled")
        
        # タイマー表示
        timer_frame = ctk.CTkFrame(auto_control, fg_color="transparent")
        timer_frame.pack(side="right")
        
        self.auto_status = ctk.CTkLabel(
            timer_frame,
            text="停止中",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        )
        self.auto_status.pack(side="left", padx=(0, 12))
        
        ctk.CTkLabel(
            timer_frame,
            text="次回:",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")
        
        self.timer_label = ctk.CTkLabel(
            timer_frame,
            text="--:--",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=Theme.TEXT_MUTED
        )
        self.timer_label.pack(side="left", padx=(8, 0))
        
        # 結果サマリーカード
        summary_card = ModernCard(main_scroll, title="📊 同期結果")
        summary_card.pack(fill="x", pady=(0, 16))
        
        stats_grid = ctk.CTkFrame(summary_card.content, fg_color="transparent")
        stats_grid.pack(fill="x")
        
        self.stats_labels = {}
        stats = [
            ("roundtrips", "往復トレード", Theme.INFO),
            ("created", "新規作成", Theme.SUCCESS),
            ("skipped", "スキップ", Theme.WARNING),
            ("errors", "エラー", Theme.ERROR),
        ]
        
        for key, label, color in stats:
            frame = ctk.CTkFrame(stats_grid, fg_color="transparent")
            frame.pack(side="left", expand=True)
            
            self.stats_labels[key] = ctk.CTkLabel(
                frame,
                text="-",
                font=ctk.CTkFont(size=28, weight="bold"),
                text_color=color
            )
            self.stats_labels[key].pack()
            
            ctk.CTkLabel(
                frame,
                text=label,
                font=ctk.CTkFont(size=11),
                text_color=Theme.TEXT_MUTED
            ).pack()
        
        # 最終同期
        last_sync_frame = ctk.CTkFrame(summary_card.content, fg_color="transparent")
        last_sync_frame.pack(fill="x", pady=(16, 0))
        
        ctk.CTkLabel(
            last_sync_frame,
            text="最終同期:",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_MUTED
        ).pack(side="left")
        
        self.last_sync_label = ctk.CTkLabel(
            last_sync_frame,
            text="-",
            font=ctk.CTkFont(size=12),
            text_color=Theme.TEXT_SECONDARY
        )
        self.last_sync_label.pack(side="left", padx=(8, 0))
        
        # ログカード
        log_card = ModernCard(main_scroll, title="📝 ログ")
        log_card.pack(fill="both", expand=True)
        
        self.log_display = LogDisplay(log_card.content, height=200)
        self.log_display.pack(fill="both", expand=True)
    
    def log(self, message: str, level: str = "info"):
        self.log_display.log(message, level)
        self.update_idletasks()
    
    def update_stats(self, stats: Dict[str, int]):
        for key, label in self.stats_labels.items():
            value = stats.get(key, 0)
            label.configure(text=str(value))
    
    def reset_stats(self):
        for label in self.stats_labels.values():
            label.configure(text="-")
    
    def update_timer(self):
        if self.auto_sync.is_running:
            remaining = self.auto_sync.get_remaining_time()
            self.timer_label.configure(text=remaining, text_color=Theme.SUCCESS)
        else:
            self.timer_label.configure(text="--:--", text_color=Theme.TEXT_MUTED)
        
        self.after(1000, self.update_timer)
    
    def auto_load_credentials(self):
        if Path("credentials.json").exists():
            self.log("credentials.json を検出しました")
            self.connect()
        else:
            self.log("credentials.json が見つかりません", "warning")
            self.after(500, self.open_settings)
    
    def open_settings(self):
        SettingsDialog(self, on_save_callback=self.connect)
    
    def connect(self):
        self.connect_btn.configure(state="disabled")
        self.log("接続中...")
        
        thread = threading.Thread(target=self._connect_async)
        thread.daemon = True
        thread.start()
    
    def _connect_async(self):
        try:
            creds = load_credentials("credentials.json")
            topstepx_creds = creds.get("topstepx", {})
            notion_creds = creds.get("notion", {})
            
            self.after(0, lambda: self.log("TopstepX認証中..."))
            
            topstepx = TopstepXClient.__new__(TopstepXClient)
            topstepx.username = topstepx_creds["username"]
            topstepx.api_key = topstepx_creds["api_key"]
            topstepx.session_token = None
            topstepx.session = __import__('requests').Session()
            topstepx.BASE_URL = "https://api.topstepx.com/api"
            topstepx.authenticate()
            
            self.topstepx = topstepx
            self.after(0, lambda: self.topstepx_status.set_status(
                f"接続済み ({topstepx_creds['username']})", "success"
            ))
            self.after(0, lambda: self.log("TopstepX接続成功", "success"))
            
            self.after(0, lambda: self.log("Notion接続中..."))
            
            notion = NotionRoundtripClient(
                api_key=notion_creds["api_key"],
                database_id=notion_creds["database_id"]
            )
            db_info = notion.get_database()
            db_title = db_info.get('title', [{}])[0].get('plain_text', 'Database')
            
            self.notion = notion
            self.after(0, lambda: self.notion_status.set_status(
                f"接続済み ({db_title})", "success"
            ))
            self.after(0, lambda: self.log(f"Notion接続成功: {db_title}", "success"))
            
            self.after(0, lambda: self.log("アカウント一覧を取得中..."))
            self.accounts = topstepx.get_accounts()
            self.after(0, self._update_account_list)
            
            self.after(500, self.restore_auto_sync_settings)
            
        except FileNotFoundError:
            self.after(0, lambda: self.log("credentials.json が見つかりません", "error"))
        except Exception as e:
            self.after(0, lambda: self.log(f"接続エラー: {e}", "error"))
        finally:
            self.after(0, lambda: self.connect_btn.configure(state="normal"))
    
    def _update_account_list(self):
        if not self.accounts:
            self.log("アカウントが見つかりません", "warning")
            return
        
        express = []
        combine = []
        practice = []
        
        for acc in self.accounts:
            name = acc.get('name', '').upper()
            display = f"{acc.get('name')} - ${acc.get('balance', 0):,.2f}"
            item = (acc.get('id'), display)
            
            if 'EXPRESS' in name:
                express.append(item)
            elif 'KTC' in name:
                combine.append(item)
            elif 'PRACTICE' in name or 'PRAC-' in name:
                practice.append(item)
            else:
                combine.append(item)
        
        express.sort(key=lambda x: x[0], reverse=True)
        combine.sort(key=lambda x: x[0], reverse=True)
        practice.sort(key=lambda x: x[0], reverse=True)
        
        all_items = []
        first_account = None
        
        if express:
            all_items.append("━━ エクスプレス ━━")
            for item in express[:10]:
                all_items.append(item[1])
                if first_account is None:
                    first_account = item[1]
        
        if combine:
            all_items.append("━━ コンバイン ━━")
            for item in combine[:5]:
                all_items.append(item[1])
                if first_account is None:
                    first_account = item[1]
        
        if practice:
            all_items.append("━━ プラクティス ━━")
            for item in practice[:5]:
                all_items.append(item[1])
                if first_account is None:
                    first_account = item[1]
        
        self.account_combo.configure(values=all_items)
        
        if first_account:
            self.account_combo.set(first_account)
        
        self.log(f"{len(self.accounts)} 個のアカウントを取得", "success")
    
    def reload_accounts(self):
        if not self.topstepx:
            messagebox.showwarning("警告", "先に接続してください")
            return
        
        self.log("アカウント再読み込み中...")
        
        def reload():
            try:
                self.accounts = self.topstepx.get_accounts()
                self.after(0, self._update_account_list)
            except Exception as e:
                self.after(0, lambda: self.log(f"エラー: {e}", "error"))
        
        thread = threading.Thread(target=reload, daemon=True)
        thread.start()
    
    def get_selected_account(self) -> Optional[Dict]:
        selected = self.account_var.get()
        if not selected or selected.startswith("━━"):
            return None
        
        for acc in self.accounts:
            display = f"{acc.get('name')} - ${acc.get('balance', 0):,.2f}"
            if display == selected:
                return acc
        return None
    
    def get_days(self) -> int:
        return int(self.period_var.get())
    
    def get_interval_minutes(self) -> int:
        return int(self.interval_var.get())
    
    def start_sync(self):
        if self.is_syncing:
            return
        
        if not self.topstepx or not self.notion:
            messagebox.showwarning("警告", "先に接続してください")
            return
        
        account = self.get_selected_account()
        if not account:
            messagebox.showwarning("警告", "アカウントを選択してください")
            return
        
        days = self.get_days()
        
        self._start_sync_ui()
        self.log_display.clear()
        self.log(f"同期開始: {account.get('name')} (過去{days}日間)")
        
        thread = threading.Thread(
            target=self._sync_async,
            args=([account], days, False),
            daemon=True
        )
        thread.start()
    
    def start_sync_all(self):
        if self.is_syncing:
            return
        
        if not self.topstepx or not self.notion:
            messagebox.showwarning("警告", "先に接続してください")
            return
        
        if not self.accounts:
            return
        
        result = messagebox.askyesno("確認", f"全 {len(self.accounts)} アカウントを同期しますか？")
        if not result:
            return
        
        days = self.get_days()
        
        self._start_sync_ui()
        self.log_display.clear()
        self.log(f"全アカウント同期開始 ({len(self.accounts)} アカウント)")
        
        thread = threading.Thread(
            target=self._sync_async,
            args=(self.accounts, days, False),
            daemon=True
        )
        thread.start()
    
    def start_auto_sync(self):
        if not self.topstepx or not self.notion:
            messagebox.showwarning("警告", "先に接続してください")
            return
        
        # 選択中アカウントモードの場合のみアカウント選択を確認
        if self.auto_target_var.get() == "selected":
            account = self.get_selected_account()
            if not account:
                messagebox.showwarning("警告", "アカウントを選択してください")
                return
        
        interval = self.get_interval_minutes()
        target_text = "全アカウント" if self.auto_target_var.get() == "all" else "選択中アカウント"
        
        self.log(f"⏰ 自動同期モード開始 (間隔: {interval}分, 対象: {target_text})", "auto")
        
        self.auto_start_btn.configure(state="disabled")
        self.auto_stop_btn.configure(state="normal")
        self.auto_status.configure(text="🟢 実行中", text_color=Theme.SUCCESS)
        
        self._auto_sync_callback()
        self.auto_sync.start(interval)
    
    def stop_auto_sync(self):
        self.auto_sync.stop()
        
        self.log("⏰ 自動同期モード停止", "auto")
        
        self.auto_start_btn.configure(state="normal")
        self.auto_stop_btn.configure(state="disabled")
        self.auto_status.configure(text="停止中", text_color=Theme.TEXT_MUTED)
    
    def _auto_sync_callback(self):
        if self.is_syncing:
            self.after(0, lambda: self.log("⏰ 前回の同期中のためスキップ", "warning"))
            return
        
        days = self.get_days()
        
        # 対象アカウントを決定
        if self.auto_target_var.get() == "all":
            accounts = self.accounts
        else:
            account = self.get_selected_account()
            accounts = [account] if account else []
        
        if not accounts:
            self.after(0, lambda: self.log("⏰ 同期対象なし", "warning"))
            return
        
        self.after(0, lambda n=len(accounts): self.log(f"⏰ 自動同期実行 ({n} アカウント)", "auto"))
        self.after(0, self._start_sync_ui)
        
        thread = threading.Thread(
            target=self._sync_async,
            args=(accounts, days, True),
            daemon=True
        )
        thread.start()
    
    def _start_sync_ui(self):
        self.is_syncing = True
        self.sync_btn.configure(state="disabled")
        self.sync_all_btn.configure(state="disabled")
        self.progress.start()
        self.reset_stats()
    
    def _sync_async(self, accounts: List[Dict], days: int, is_auto: bool = False):
        total_stats = {"roundtrips": 0, "created": 0, "skipped": 0, "errors": 0}
        
        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days)
            
            for i, account in enumerate(accounts):
                account_id = account.get('id')
                account_name = account.get('name')
                
                self.after(0, lambda n=account_name, idx=i: 
                    self.log(f"[{idx+1}/{len(accounts)}] {n}")
                )
                
                try:
                    trades = self.topstepx.get_trades(
                        account_id=account_id,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    self.after(0, lambda t=len(trades): 
                        self.log(f"  {t} 件の片道トレード")
                    )
                    
                    if not trades:
                        continue
                    
                    transformer = RoundtripTransformer()
                    roundtrips = transformer.transform(trades)
                    
                    self.after(0, lambda r=len(roundtrips): 
                        self.log(f"  {r} 件の往復トレード")
                    )
                    
                    if not roundtrips:
                        continue
                    
                    total_stats["roundtrips"] += len(roundtrips)
                    
                    sync_result = self.notion.sync_roundtrips(
                        roundtrips=roundtrips,
                        account_name=account_name,
                        skip_existing=True
                    )
                    
                    total_stats["created"] += sync_result["created"]
                    total_stats["skipped"] += sync_result["skipped"]
                    total_stats["errors"] += sync_result["errors"]
                    
                    self.after(0, lambda c=sync_result["created"], s=sync_result["skipped"]: 
                        self.log(f"  ✅ 作成: {c} / スキップ: {s}", "success")
                    )
                    
                    self.after(0, lambda s=total_stats.copy(): self.update_stats(s))
                    
                except Exception as e:
                    total_stats["errors"] += 1
                    self.after(0, lambda err=str(e): 
                        self.log(f"  ❌ エラー: {err}", "error")
                    )
            
            prefix = "⏰ " if is_auto else ""
            self.after(0, lambda s=total_stats, p=prefix: 
                self.log(f"{p}同期完了! 作成: {s['created']} / スキップ: {s['skipped']}", "success")
            )
            
            now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.after(0, lambda t=now_str: self.last_sync_label.configure(text=t))
            
        except Exception as e:
            self.after(0, lambda err=str(e): self.log(f"エラー: {err}", "error"))
        finally:
            self.after(0, self._sync_complete)
    
    def _sync_complete(self):
        self.is_syncing = False
        self.sync_btn.configure(state="normal")
        self.sync_all_btn.configure(state="normal")
        self.progress.stop()
        self.progress.set(0)
    
    def save_sync_settings(self):
        settings = {
            "auto_sync_enabled": self.auto_sync.is_running,
            "interval_minutes": self.get_interval_minutes(),
            "period_days": self.get_days(),
            "selected_account": self.account_var.get(),
            "auto_target": self.auto_target_var.get()
        }
        
        try:
            with open(self.SYNC_SETTINGS_PATH, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
    
    def load_sync_settings(self) -> Optional[Dict]:
        try:
            if Path(self.SYNC_SETTINGS_PATH).exists():
                with open(self.SYNC_SETTINGS_PATH, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None
    
    def restore_auto_sync_settings(self):
        settings = self.load_sync_settings()
        if not settings:
            return
        
        try:
            period_days = settings.get("period_days", 7)
            self.period_var.set(str(period_days))
            
            interval = settings.get("interval_minutes", 30)
            self.interval_var.set(str(interval))
            
            saved_account = settings.get("selected_account", "")
            values = self.account_combo.cget("values")
            if saved_account and saved_account in values:
                self.account_combo.set(saved_account)
            
            # 自動同期対象を復元
            auto_target = settings.get("auto_target", "selected")
            self.auto_target_var.set(auto_target)
            
            if settings.get("auto_sync_enabled", False):
                self.log("⏰ 前回の自動同期設定を復元中...", "auto")
                self.after(1000, self._start_auto_sync_restored)
                
        except Exception as e:
            self.log(f"設定復元エラー: {e}", "error")
    
    def _start_auto_sync_restored(self):
        if not self.topstepx or not self.notion:
            self.log("⚠️ 接続未完了のため自動同期をスキップ", "warning")
            return
        
        # 選択中アカウントモードの場合のみアカウント選択を確認
        if self.auto_target_var.get() == "selected":
            account = self.get_selected_account()
            if not account:
                self.log("⚠️ アカウント未選択のため自動同期をスキップ", "warning")
                return
        
        interval = self.get_interval_minutes()
        target_text = "全アカウント" if self.auto_target_var.get() == "all" else "選択中アカウント"
        self.log(f"⏰ 自動同期モード復元 (間隔: {interval}分, 対象: {target_text})", "auto")
        
        self.auto_start_btn.configure(state="disabled")
        self.auto_stop_btn.configure(state="normal")
        self.auto_status.configure(text="🟢 実行中", text_color=Theme.SUCCESS)
        
        self._auto_sync_callback()
        self.auto_sync.start(interval)
    
    def on_closing(self):
        self.save_sync_settings()
        
        if self.auto_sync.is_running:
            result = messagebox.askyesno(
                "確認",
                "自動同期が実行中です。終了しますか？\n（次回起動時に自動同期を再開します）"
            )
            if not result:
                return
            self.auto_sync.stop()
        
        self.destroy()


def main():
    app = SyncApp()
    app.mainloop()


if __name__ == "__main__":
    main()