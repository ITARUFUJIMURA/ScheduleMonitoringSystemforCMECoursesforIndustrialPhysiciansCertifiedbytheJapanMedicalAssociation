# ========================================
# database.py - SQLiteによる状態管理
# ========================================
#
# このファイルでは、巡回済みのページ情報を
# SQLiteデータベースに保存・管理します。
#
# 主な役割：
# - 既知のURLを記録して重複検出を防ぐ
# - ページ内容のハッシュ値を保存して更新検出する
# - 研修会の詳細情報（単位・日時・場所）を保存する
# ========================================

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Tuple
from dataclasses import dataclass

from .config import DATABASE_PATH


@dataclass
class PageRecord:
    """
    ページの記録情報を保持するクラス

    Attributes:
        url: ページのURL
        title: ページのタイトル
        content_hash: ページ内容のハッシュ値（更新検出用）
        first_seen: 初回検出日時
        last_checked: 最終チェック日時
        last_updated: 最終更新検出日時
        site_name: 監視対象サイトの識別名
        units: 取得できる単位（例: "生涯2単位"）
        event_date: 開催日（例: "2026年2月15日"）
        event_time: 開催時間（例: "13:00〜17:00"）
        location: 開催場所（例: "岩手県医師会館"）
    """
    url: str
    title: str
    content_hash: str
    first_seen: datetime
    last_checked: datetime
    last_updated: datetime
    site_name: str
    units: str = ""
    event_date: str = ""
    event_time: str = ""
    location: str = ""


class Database:
    """
    SQLiteデータベースを操作するクラス

    使い方:
        db = Database()
        db.initialize()  # テーブル作成
        db.upsert_page(...)  # ページ情報を保存
        db.get_page(url)  # ページ情報を取得
    """

    def __init__(self, db_path: str = DATABASE_PATH):
        """
        データベースを初期化

        Args:
            db_path: SQLiteファイルのパス
        """
        self.db_path = db_path

        # データベースディレクトリが存在しない場合は作成
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _get_connection(self) -> sqlite3.Connection:
        """
        データベース接続を取得

        Returns:
            SQLite接続オブジェクト
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # カラム名でアクセス可能にする
        return conn

    def initialize(self) -> None:
        """
        データベースのテーブルを作成（存在しない場合のみ）

        pagesテーブル:
            - url: ページのURL（主キー）
            - title: ページタイトル
            - content_hash: 内容のハッシュ値
            - first_seen: 初回検出日時
            - last_checked: 最終チェック日時
            - last_updated: 最終更新検出日時
            - site_name: 監視対象サイト名
            - units: 取得できる単位
            - event_date: 開催日
            - event_time: 開催時間
            - location: 開催場所
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # テーブルが存在するかチェック
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages'")
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            # 新規作成
            cursor.execute("""
                CREATE TABLE pages (
                    url TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_checked TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    site_name TEXT NOT NULL,
                    units TEXT DEFAULT '',
                    event_date TEXT DEFAULT '',
                    event_time TEXT DEFAULT '',
                    location TEXT DEFAULT ''
                )
            """)
        else:
            # 既存テーブルに新しいカラムを追加（存在しない場合のみ）
            cursor.execute("PRAGMA table_info(pages)")
            existing_columns = {row[1] for row in cursor.fetchall()}

            new_columns = [
                ("units", "TEXT DEFAULT ''"),
                ("event_date", "TEXT DEFAULT ''"),
                ("event_time", "TEXT DEFAULT ''"),
                ("location", "TEXT DEFAULT ''"),
            ]

            for col_name, col_def in new_columns:
                if col_name not in existing_columns:
                    cursor.execute(f"ALTER TABLE pages ADD COLUMN {col_name} {col_def}")
                    print(f"[DB] カラム追加: {col_name}")

        # インデックスを作成（検索高速化）
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_site_name ON pages(site_name)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_updated ON pages(last_updated)
        """)

        conn.commit()
        conn.close()

        print(f"[DB] データベースを初期化しました: {self.db_path}")

    def get_page(self, url: str) -> Optional[PageRecord]:
        """
        URLに対応するページ情報を取得

        Args:
            url: 検索するURL

        Returns:
            PageRecord または None（見つからない場合）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM pages WHERE url = ?", (url,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return self._row_to_record(row)

    def _row_to_record(self, row: sqlite3.Row) -> PageRecord:
        """
        データベースの行をPageRecordに変換

        Args:
            row: データベースの行

        Returns:
            PageRecordオブジェクト
        """
        # カラムが存在するかチェックしてデフォルト値を使用
        keys = row.keys()

        return PageRecord(
            url=row["url"],
            title=row["title"],
            content_hash=row["content_hash"],
            first_seen=datetime.fromisoformat(row["first_seen"]),
            last_checked=datetime.fromisoformat(row["last_checked"]),
            last_updated=datetime.fromisoformat(row["last_updated"]),
            site_name=row["site_name"],
            units=row["units"] if "units" in keys else "",
            event_date=row["event_date"] if "event_date" in keys else "",
            event_time=row["event_time"] if "event_time" in keys else "",
            location=row["location"] if "location" in keys else "",
        )

    def upsert_page(
        self,
        url: str,
        title: str,
        content_hash: str,
        site_name: str,
        is_updated: bool = False,
        units: str = "",
        event_date: str = "",
        event_time: str = "",
        location: str = "",
    ) -> Tuple[bool, bool]:
        """
        ページ情報を保存（存在すれば更新、なければ挿入）

        Args:
            url: ページのURL
            title: ページのタイトル
            content_hash: 内容のハッシュ値
            site_name: 監視対象サイト名
            is_updated: 内容が更新されたかどうか
            units: 取得できる単位
            event_date: 開催日
            event_time: 開催時間
            location: 開催場所

        Returns:
            (is_new, is_content_updated) のタプル
            - is_new: 新規ページかどうか
            - is_content_updated: 内容が更新されたかどうか
        """
        now = datetime.now().isoformat()
        existing = self.get_page(url)

        conn = self._get_connection()
        cursor = conn.cursor()

        if existing is None:
            # 新規ページを挿入
            cursor.execute("""
                INSERT INTO pages (url, title, content_hash, first_seen, last_checked, last_updated, site_name, units, event_date, event_time, location)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (url, title, content_hash, now, now, now, site_name, units, event_date, event_time, location))
            conn.commit()
            conn.close()
            print(f"[DB] 新規ページを登録: {title[:30]}...")
            return (True, False)  # 新規, 更新なし

        else:
            # 既存ページを更新
            if is_updated:
                # 内容が変わった場合は last_updated も更新
                cursor.execute("""
                    UPDATE pages
                    SET title = ?, content_hash = ?, last_checked = ?, last_updated = ?,
                        units = ?, event_date = ?, event_time = ?, location = ?
                    WHERE url = ?
                """, (title, content_hash, now, now, units, event_date, event_time, location, url))
                print(f"[DB] ページ更新を検出: {title[:30]}...")
            else:
                # 内容が変わらない場合は last_checked のみ更新（詳細情報は更新）
                cursor.execute("""
                    UPDATE pages
                    SET last_checked = ?, units = ?, event_date = ?, event_time = ?, location = ?
                    WHERE url = ?
                """, (now, units, event_date, event_time, location, url))

            conn.commit()
            conn.close()
            return (False, is_updated)  # 既存, 更新あり/なし

    def get_recent_updates(self, days: int = 30) -> List[PageRecord]:
        """
        最近更新されたページを取得

        Args:
            days: 何日以内の更新を取得するか

        Returns:
            PageRecordのリスト（更新日時の降順）
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM pages
            WHERE last_updated >= datetime('now', ? || ' days')
            ORDER BY last_updated DESC
        """, (f"-{days}",))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_record(row) for row in rows]

    def get_all_pages(self) -> List[PageRecord]:
        """
        全ページを取得

        Returns:
            PageRecordのリスト
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM pages ORDER BY last_updated DESC")
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_record(row) for row in rows]
