#!/usr/bin/env python3
# ========================================
# watcher.py - 産業医講習監視システム メインスクリプト
# ========================================
#
# このスクリプトは、産業医の単位講習情報を
# 定期的に巡回し、新着・更新があればRSSを更新します。
#
# 使い方:
#   python watcher.py           # 通常実行
#   python watcher.py --init    # 初期化（空のRSS生成）
#   python watcher.py --dry-run # テスト実行（DB・RSS更新なし）
#
# GitHub Actions から毎日自動実行されます。
# ========================================

import argparse
import sys
from typing import List, Tuple

# 自作モジュールをインポート
from src.config import WATCH_TARGETS, DATABASE_PATH, RSS_OUTPUT_PATH
from src.database import Database, PageRecord
from src.scraper import Scraper, ScrapedLink
from src.rss_generator import RSSGenerator
from src.notifier import Notifier


def parse_args() -> argparse.Namespace:
    """
    コマンドライン引数を解析

    Returns:
        解析した引数
    """
    parser = argparse.ArgumentParser(
        description="産業医講習監視システム - Webサイトを巡回してRSSを生成",
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="初期化モード: データベースと空のRSSを作成",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="テストモード: スクレイピングのみ実行（DB・RSS更新なし）",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="RSSに含める日数（デフォルト: 30日）",
    )

    return parser.parse_args()


def initialize(db: Database, rss: RSSGenerator) -> None:
    """
    システムを初期化

    Args:
        db: データベースオブジェクト
        rss: RSSジェネレーターオブジェクト
    """
    print("=" * 50)
    print("初期化モード")
    print("=" * 50)

    # データベーステーブルを作成
    db.initialize()

    # 空のRSSフィードを生成
    rss.generate_empty()

    print("\n初期化が完了しました。")
    print(f"  データベース: {DATABASE_PATH}")
    print(f"  RSSフィード: {RSS_OUTPUT_PATH}")


def run_watcher(
    db: Database,
    scraper: Scraper,
    rss: RSSGenerator,
    dry_run: bool = False,
    rss_days: int = 30,
) -> Tuple[List[PageRecord], List[PageRecord]]:
    """
    メインの巡回処理を実行

    Args:
        db: データベースオブジェクト
        scraper: スクレイパーオブジェクト
        rss: RSSジェネレーターオブジェクト
        dry_run: テストモードかどうか
        rss_days: RSSに含める日数

    Returns:
        (new_pages, updated_pages) のタプル
    """
    print("=" * 50)
    print("産業医講習監視システム - 巡回開始")
    print("=" * 50)

    if dry_run:
        print("【テストモード】DB・RSSは更新されません\n")

    # データベースを初期化（テーブルがなければ作成）
    if not dry_run:
        db.initialize()

    # 新規・更新ページを記録するリスト
    new_pages: List[PageRecord] = []
    updated_pages: List[PageRecord] = []

    # 各監視対象サイトを巡回
    for target in WATCH_TARGETS:
        print(f"\n--- {target.name} ---")
        print(f"URL: {target.url}")

        # (1) 一覧ページを取得し、キーワードマッチするリンクを抽出
        matching_links = scraper.get_matching_links(target)

        if not matching_links:
            print("  → マッチするリンクなし")
            continue

        # (2) 各詳細ページをチェック
        for link in matching_links:
            # (3) 詳細ページの内容を取得してハッシュ化
            content = scraper.get_page_content(link.url, link.title)

            if content is None:
                print(f"  → 取得失敗: {link.url}")
                continue

            if dry_run:
                # テストモードではDB更新しない
                print(f"  → [DRY-RUN] {content.title[:40]}...")
                continue

            # 既存のページ情報を取得
            existing = db.get_page(link.url)

            # 更新判定: ハッシュ値が変わっていれば更新
            is_updated = False
            if existing and existing.content_hash != content.content_hash:
                is_updated = True

            # データベースに保存（詳細情報も含める）
            is_new, is_content_updated = db.upsert_page(
                url=content.url,
                title=content.title,
                content_hash=content.content_hash,
                site_name=target.name,
                is_updated=is_updated,
                units=content.seminar_info.units,
                event_date=content.seminar_info.date,
                event_time=content.seminar_info.time,
                location=content.seminar_info.location,
            )

            # 新規または更新ページを記録
            if is_new or is_content_updated:
                record = db.get_page(link.url)
                if record:
                    if is_new:
                        new_pages.append(record)
                    else:
                        updated_pages.append(record)

    # 結果サマリー
    print("\n" + "=" * 50)
    print("巡回完了")
    print(f"  新規ページ: {len(new_pages)}件")
    print(f"  更新ページ: {len(updated_pages)}件")
    print("=" * 50)

    # RSSを更新（新規または更新があった場合のみ）
    if not dry_run and (new_pages or updated_pages):
        print("\nRSSフィードを更新中...")

        # 最近のページを取得してRSSに含める
        recent_pages = db.get_recent_updates(days=rss_days)
        rss.generate(recent_pages)
    elif not dry_run:
        print("\n新規・更新なし。RSSは更新しません。")

    return new_pages, updated_pages


def main() -> int:
    """
    メイン関数

    Returns:
        終了コード（0: 成功, 1: エラー）
    """
    args = parse_args()

    # 各コンポーネントを初期化
    db = Database()
    scraper = Scraper()
    rss_generator = RSSGenerator()

    try:
        if args.init:
            # 初期化モード
            initialize(db, rss_generator)
        else:
            # 通常の巡回モード
            new_pages, updated_pages = run_watcher(
                db=db,
                scraper=scraper,
                rss=rss_generator,
                dry_run=args.dry_run,
                rss_days=args.days,
            )

            # 将来のメール通知（現在は未実装）
            # if new_pages or updated_pages:
            #     notifier = Notifier()
            #     notifier.send_email(new_pages, updated_pages)

        return 0

    except Exception as e:
        print(f"\n[エラー] 予期しないエラーが発生しました: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        # リソースを解放
        scraper.close()


if __name__ == "__main__":
    sys.exit(main())
