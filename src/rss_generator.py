# ========================================
# rss_generator.py - RSS フィード生成
# ========================================
#
# このファイルでは、検出した新着・更新情報を
# RSS 2.0 形式のフィードとして出力します。
#
# タイトル形式:
#   【生涯2単位】研修会名 - 2026/2/15 13:00〜 @岩手県医師会館
#
# 出力先: docs/feed.xml（GitHub Pages用）
# ========================================

import os
from datetime import datetime, timezone
from typing import List

from feedgen.feed import FeedGenerator

from .config import RSS_CONFIG, RSS_OUTPUT_PATH
from .database import PageRecord


class RSSGenerator:
    """
    RSSフィードを生成するクラス

    使い方:
        generator = RSSGenerator()
        generator.generate(page_records)
    """

    def __init__(self, output_path: str = RSS_OUTPUT_PATH):
        """
        RSSジェネレーターを初期化

        Args:
            output_path: RSS出力ファイルのパス
        """
        self.output_path = output_path

        # 出力ディレクトリが存在しない場合は作成
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def generate(self, records: List[PageRecord]) -> str:
        """
        RSSフィードを生成してファイルに保存

        Args:
            records: PageRecordのリスト（RSSに含めるページ情報）

        Returns:
            生成したRSSのXML文字列
        """
        # FeedGeneratorを初期化
        fg = FeedGenerator()

        # フィードの基本情報を設定
        fg.title(RSS_CONFIG["title"])
        fg.description(RSS_CONFIG["description"])
        fg.link(href=RSS_CONFIG["link"], rel="self")
        fg.language(RSS_CONFIG["language"])

        # 最終更新日時を設定（現在時刻）
        fg.lastBuildDate(datetime.now(timezone.utc))

        # 各ページをフィードエントリーとして追加
        for record in records:
            entry = fg.add_entry()

            # タイトルを生成（単位・日時・場所を含む）
            title = self._generate_title(record)
            entry.title(title)
            entry.link(href=record.url)

            # GUID（一意識別子）- URLを使用
            entry.guid(record.url, permalink=True)

            # 公開日時・更新日時
            # SQLiteのdatetimeはタイムゾーン情報がないので、JSTとして扱う
            pub_date = record.first_seen.replace(tzinfo=timezone.utc)
            update_date = record.last_updated.replace(tzinfo=timezone.utc)

            entry.published(pub_date)
            entry.updated(update_date)

            # 説明文（サイト名を含める）
            description = self._generate_description(record)
            entry.description(description)

        # RSSフィードを生成
        rss_xml = fg.rss_str(pretty=True).decode("utf-8")

        # ファイルに保存
        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(rss_xml)

        print(f"[RSS] フィードを生成しました: {self.output_path}")
        print(f"[RSS] エントリー数: {len(records)}件")

        return rss_xml

    def _generate_title(self, record: PageRecord) -> str:
        """
        RSSエントリーのタイトルを生成

        形式: 【生涯2単位】研修会名 - 2026/2/15 13:00〜 @岩手県医師会館

        Args:
            record: ページ情報

        Returns:
            生成したタイトル
        """
        parts = []

        # 単位情報を先頭に追加（目立つように）
        if record.units:
            parts.append(f"【{record.units}】")

        # 元のタイトル（長すぎる場合は切り詰め）
        original_title = record.title
        # タイトルから不要な接頭辞を除去
        prefixes_to_remove = [
            "研修会医師向け",
            "医師向け",
        ]
        for prefix in prefixes_to_remove:
            if original_title.startswith(prefix):
                original_title = original_title[len(prefix):]

        # タイトルを適度な長さに
        max_title_len = 50
        if len(original_title) > max_title_len:
            original_title = original_title[:max_title_len] + "..."

        parts.append(original_title)

        # 日時情報を追加
        if record.event_date or record.event_time:
            date_time_parts = []
            if record.event_date:
                # 日付を短縮形式に変換（2026年2月15日 → 2/15）
                short_date = self._shorten_date(record.event_date)
                date_time_parts.append(short_date)
            if record.event_time:
                date_time_parts.append(record.event_time)

            if date_time_parts:
                parts.append(f" - {' '.join(date_time_parts)}")

        # 場所情報を追加
        if record.location:
            # 場所を短縮
            short_location = record.location
            if len(short_location) > 15:
                short_location = short_location[:15] + "..."
            parts.append(f" @{short_location}")

        return "".join(parts)

    def _shorten_date(self, date_str: str) -> str:
        """
        日付を短縮形式に変換

        Args:
            date_str: 元の日付文字列（例: "2026年2月15日（土）"）

        Returns:
            短縮形式（例: "2/15(土)"）
        """
        import re

        # 年月日（曜日）形式をパース
        match = re.match(r'(\d+)年(\d+)月(\d+)日[（\(]?([月火水木金土日])?[）\)]?', date_str)
        if match:
            year, month, day = match.group(1), match.group(2), match.group(3)
            weekday = match.group(4)

            # 今年なら年を省略
            current_year = datetime.now().year
            if int(year) == current_year:
                if weekday:
                    return f"{month}/{day}({weekday})"
                return f"{month}/{day}"
            else:
                if weekday:
                    return f"{year}/{month}/{day}({weekday})"
                return f"{year}/{month}/{day}"

        # 月日（曜日）形式
        match = re.match(r'(\d+)月(\d+)日[（\(]?([月火水木金土日])?[）\)]?', date_str)
        if match:
            month, day = match.group(1), match.group(2)
            weekday = match.group(3)
            if weekday:
                return f"{month}/{day}({weekday})"
            return f"{month}/{day}"

        # パースできない場合はそのまま返す
        return date_str

    def _generate_description(self, record: PageRecord) -> str:
        """
        RSSエントリーの説明文を生成

        Args:
            record: ページ情報

        Returns:
            説明文のHTML
        """
        # サイト名を日本語に変換
        site_names = {
            "iwate_med": "岩手県医師会",
            "iwates_johas_seminar": "岩手産業保健総合支援センター（セミナー）",
            "iwates_johas_training": "岩手産業保健総合支援センター（産業医研修）",
            "sangyo_doctors": "日本産業医協会",
            "med_or_jp": "日本医師会Web研修",
        }

        site_display_name = site_names.get(record.site_name, record.site_name)

        # 新規か更新かを判定
        is_new = record.first_seen == record.last_updated
        status = "【新着】" if is_new else "【更新】"

        # 説明文を組み立て
        lines = [
            f"<p><strong>{status}</strong> {site_display_name}</p>",
        ]

        # 詳細情報を追加
        if record.units:
            lines.append(f"<p>📚 単位: {record.units}</p>")

        if record.event_date:
            date_info = record.event_date
            if record.event_time:
                date_info += f" {record.event_time}"
            lines.append(f"<p>📅 日時: {date_info}</p>")

        if record.location:
            lines.append(f"<p>📍 場所: {record.location}</p>")

        lines.append(f"<p>🔍 検出: {record.first_seen.strftime('%Y/%m/%d %H:%M')}</p>")

        if not is_new:
            lines.append(f"<p>🔄 更新: {record.last_updated.strftime('%Y/%m/%d %H:%M')}</p>")

        lines.append(f'<p><a href="{record.url}">▶ 詳細を見る</a></p>')

        return "\n".join(lines)

    def generate_empty(self) -> str:
        """
        空のRSSフィードを生成（初期化用）

        Returns:
            生成したRSSのXML文字列
        """
        return self.generate([])
