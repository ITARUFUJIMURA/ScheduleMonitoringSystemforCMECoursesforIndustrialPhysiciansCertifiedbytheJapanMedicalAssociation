# ========================================
# notifier.py - 通知機能（将来実装用スタブ）
# ========================================
#
# このファイルは将来のメール通知機能のための
# プレースホルダーです。
#
# TODO:
# - SendGrid または SMTP を使ったメール送信
# - Slack Webhook 通知
# - LINE Notify 連携
# ========================================

from typing import List
from .database import PageRecord


class Notifier:
    """
    通知を送信するクラス（将来実装用）

    使い方:
        notifier = Notifier()
        notifier.send_email(new_pages, updated_pages)
    """

    def __init__(self):
        """通知クラスを初期化"""
        pass

    def send_email(
        self,
        new_pages: List[PageRecord],
        updated_pages: List[PageRecord],
    ) -> bool:
        """
        メール通知を送信（未実装）

        Args:
            new_pages: 新規ページのリスト
            updated_pages: 更新されたページのリスト

        Returns:
            送信成功ならTrue
        """
        # TODO: 実装する
        print("[Notifier] メール通知は未実装です")
        return False

    def send_slack(self, message: str) -> bool:
        """
        Slack通知を送信（未実装）

        Args:
            message: 送信するメッセージ

        Returns:
            送信成功ならTrue
        """
        # TODO: 実装する
        print("[Notifier] Slack通知は未実装です")
        return False
