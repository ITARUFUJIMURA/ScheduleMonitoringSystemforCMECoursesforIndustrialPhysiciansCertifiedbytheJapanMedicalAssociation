# ========================================
# scraper.py - Webスクレイピング処理
# ========================================
#
# このファイルでは、Webページを取得し、
# キーワードに基づいてリンクを抽出します。
#
# 主な処理フロー:
# 1. 一覧ページを取得
# 2. キーワードにマッチするリンクを抽出
# 3. 詳細ページの内容をハッシュ化（更新検出用）
# 4. 単位・日時・場所の情報を抽出
# ========================================

import hashlib
import re
import time
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup

from .config import WatchTarget


# ========================================
# 設定値
# ========================================

# HTTPリクエストのタイムアウト（秒）
REQUEST_TIMEOUT = 30

# リクエスト間の待機時間（秒）- サーバー負荷軽減
REQUEST_DELAY = 2

# User-Agent（ボットとして丁寧に名乗る）
USER_AGENT = "SangyoiWatcher/1.0 (Industrial Physician Training Monitor; Contact: your-email@example.com)"


@dataclass
class ScrapedLink:
    """
    スクレイピングで抽出したリンク情報

    Attributes:
        url: リンク先のURL
        title: リンクテキスト（タイトル）
        matched_keywords: マッチしたキーワードのリスト
    """
    url: str
    title: str
    matched_keywords: List[str]


@dataclass
class SeminarInfo:
    """
    研修会の詳細情報

    Attributes:
        units: 取得できる単位（例: "生涯2単位", "基礎1単位・実地2単位"）
        date: 開催日（例: "2026年2月15日"）
        time: 開催時間（例: "13:00〜17:00"）
        location: 開催場所（例: "岩手県医師会館", "オンライン"）
    """
    units: str = ""
    date: str = ""
    time: str = ""
    location: str = ""


@dataclass
class PageContent:
    """
    ページの内容情報

    Attributes:
        url: ページのURL
        title: ページのタイトル
        content_hash: 内容のハッシュ値
        description: 簡単な説明（RSS用）
        seminar_info: 研修会の詳細情報
    """
    url: str
    title: str
    content_hash: str
    description: str
    seminar_info: SeminarInfo = field(default_factory=SeminarInfo)


class Scraper:
    """
    Webスクレイピングを行うクラス

    使い方:
        scraper = Scraper()
        links = scraper.get_matching_links(target)
        for link in links:
            content = scraper.get_page_content(link.url)
    """

    def __init__(self):
        """スクレイパーを初期化"""
        # セッションを使い回すことで効率化
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ja,en;q=0.5",
        })

    def _fetch_page(self, url: str) -> Optional[str]:
        """
        指定URLのHTMLを取得

        Args:
            url: 取得するURL

        Returns:
            HTMLテキスト、または None（エラー時）
        """
        try:
            print(f"[Scraper] ページ取得中: {url}")
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()  # HTTPエラーを例外として発生

            # 文字コードを自動検出（日本語サイト対策）
            response.encoding = response.apparent_encoding

            return response.text

        except requests.RequestException as e:
            print(f"[Scraper] エラー: {url} の取得に失敗 - {e}")
            return None

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """
        BeautifulSoupオブジェクトからテキストを抽出

        Args:
            soup: BeautifulSoupオブジェクト

        Returns:
            抽出したテキスト（正規化済み）
        """
        # script, style タグを除去
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # テキストを取得し、空白を正規化
        text = soup.get_text(separator=" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        return text

    def _compute_hash(self, content: str) -> str:
        """
        コンテンツのハッシュ値を計算

        Args:
            content: ハッシュ化する文字列

        Returns:
            SHA-256ハッシュ値（16進数文字列）
        """
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _is_same_domain(self, url1: str, url2: str) -> bool:
        """
        2つのURLが同じドメインかどうかを判定

        Args:
            url1: URL1
            url2: URL2

        Returns:
            同じドメインならTrue
        """
        domain1 = urlparse(url1).netloc
        domain2 = urlparse(url2).netloc
        return domain1 == domain2

    def _is_valid_link(self, url: str, base_url: str) -> bool:
        """
        有効なリンクかどうかを判定

        Args:
            url: チェックするURL
            base_url: 基準となるURL

        Returns:
            有効なリンクならTrue
        """
        # 空やNoneは除外
        if not url:
            return False

        # アンカーリンク（#で始まる）は除外
        if url.startswith("#"):
            return False

        # javascript: や mailto: は除外
        if url.startswith(("javascript:", "mailto:", "tel:")):
            return False

        # 同一ドメインのみを対象とする
        full_url = urljoin(base_url, url)
        if not self._is_same_domain(full_url, base_url):
            return False

        return True

    def _extract_units(self, text: str) -> str:
        """
        テキストから単位情報を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した単位情報（例: "生涯2単位", "基礎1単位・実地2単位"）
        """
        # 単位のパターン（様々な形式に対応）
        # 例: "生涯2単位", "基礎研修1単位", "実地1単位", "2単位", "２単位"
        patterns = [
            # 「○○研修 N単位」形式
            r'(基礎研修|生涯研修|実地研修|更新研修|専門研修)[^\d]*([0-9０-９]+)\s*単位',
            # 「生涯N単位」「基礎N単位」形式
            r'(生涯|基礎|実地|更新|専門)\s*([0-9０-９]+)\s*単位',
            # 「N単位（○○）」形式
            r'([0-9０-９]+)\s*単位\s*[（\(]?\s*(生涯|基礎|実地|更新|専門)',
            # シンプルな「N単位」形式
            r'([0-9０-９]+)\s*単位',
        ]

        found_units = []

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    # グループがある場合
                    if len(match) == 2:
                        # 全角数字を半角に変換
                        num = self._normalize_number(match[1] if match[0] in ['基礎研修', '生涯研修', '実地研修', '更新研修', '専門研修', '生涯', '基礎', '実地', '更新', '専門'] else match[0])
                        category = match[0] if match[0] in ['基礎研修', '生涯研修', '実地研修', '更新研修', '専門研修', '生涯', '基礎', '実地', '更新', '専門'] else match[1]
                        # 「研修」を除去して簡潔に
                        category = category.replace('研修', '')
                        unit_str = f"{category}{num}単位"
                        if unit_str not in found_units:
                            found_units.append(unit_str)
                else:
                    # 単純なN単位形式
                    num = self._normalize_number(match)
                    unit_str = f"{num}単位"
                    if unit_str not in found_units and not any(unit_str in u for u in found_units):
                        found_units.append(unit_str)

        # 重複を除去して結合
        if found_units:
            return "・".join(found_units[:3])  # 最大3つまで
        return ""

    def _extract_date(self, text: str) -> str:
        """
        テキストから開催日を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した日付（例: "2026年2月15日（土）"）
        """
        # 開催日、日時、日程などのキーワード付近を優先的に探す
        date_context_patterns = [
            r'(?:開催日|日\s*時|日\s*程|期\s*日)[：:\s]*',
        ]

        # まずキーワード付近で日付を探す
        for context_pattern in date_context_patterns:
            context_match = re.search(context_pattern, text)
            if context_match:
                # キーワードの後ろ100文字を対象に
                search_area = text[context_match.end():context_match.end()+100]
                result = self._parse_date_from_text(search_area)
                if result:
                    return result

        # キーワードが見つからない場合は全体から探す
        return self._parse_date_from_text(text)

    def _parse_date_from_text(self, text: str) -> str:
        """
        テキストから日付をパース

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した日付
        """
        # 令和N年M月D日（曜日）形式
        match = re.search(r'令和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日\s*[（\(]\s*([月火水木金土日])\s*[）\)]', text)
        if match:
            reiwa_year = int(self._normalize_number(match.group(1)))
            year = 2018 + reiwa_year
            month = self._normalize_number(match.group(2))
            day = self._normalize_number(match.group(3))
            weekday = match.group(4)
            return f"{year}年{month}月{day}日（{weekday}）"

        # 令和N年M月D日 形式
        match = re.search(r'令和\s*([0-9０-９]+)\s*年\s*([0-9０-９]+)\s*月\s*([0-9０-９]+)\s*日', text)
        if match:
            reiwa_year = int(self._normalize_number(match.group(1)))
            year = 2018 + reiwa_year
            month = self._normalize_number(match.group(2))
            day = self._normalize_number(match.group(3))
            return f"{year}年{month}月{day}日"

        # 20XX年M月D日（曜日）形式
        match = re.search(r'(20[0-9]{2})\s*年\s*([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日\s*[（\(]\s*([月火水木金土日])\s*[）\)]', text)
        if match:
            year = match.group(1)
            month = self._normalize_number(match.group(2))
            day = self._normalize_number(match.group(3))
            weekday = match.group(4)
            return f"{year}年{month}月{day}日（{weekday}）"

        # 20XX年M月D日 形式
        match = re.search(r'(20[0-9]{2})\s*年\s*([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日', text)
        if match:
            year = match.group(1)
            month = self._normalize_number(match.group(2))
            day = self._normalize_number(match.group(3))
            return f"{year}年{month}月{day}日"

        # M月D日（曜日）形式（年なし）
        match = re.search(r'([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日\s*[（\(]\s*([月火水木金土日])\s*[）\)]', text)
        if match:
            month = self._normalize_number(match.group(1))
            day = self._normalize_number(match.group(2))
            weekday = match.group(3)
            # 月が1-12の範囲内かチェック
            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{month}月{day}日（{weekday}）"

        # M月D日 形式（年なし）
        match = re.search(r'([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日(?![（\(])', text)
        if match:
            month = self._normalize_number(match.group(1))
            day = self._normalize_number(match.group(2))
            # 月が1-12の範囲内かチェック
            if 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
                return f"{month}月{day}日"

        return ""

    def _extract_time(self, text: str) -> str:
        """
        テキストから開催時間を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した時間（例: "13:00〜17:00"）
        """
        # 時間のパターン
        patterns = [
            # 13:00〜17:00 形式
            r'([0-9０-９]{1,2})\s*[:：]\s*([0-9０-９]{2})\s*[〜～\-−~]\s*([0-9０-９]{1,2})\s*[:：]\s*([0-9０-９]{2})',
            # 13時00分〜17時00分 形式
            r'([0-9０-９]{1,2})\s*時\s*([0-9０-９]{0,2})\s*分?\s*[〜～\-−~から]\s*([0-9０-９]{1,2})\s*時\s*([0-9０-９]{0,2})\s*分?',
            # 13:00から 形式（終了時間なし）
            r'([0-9０-９]{1,2})\s*[:：]\s*([0-9０-９]{2})\s*[〜～\-−~から開始]',
            # 13時から 形式
            r'([0-9０-９]{1,2})\s*時\s*([0-9０-９]{0,2})\s*分?\s*[〜～\-−~から開始]',
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    start_h = self._normalize_number(groups[0])
                    start_m = self._normalize_number(groups[1]) if groups[1] else "00"
                    end_h = self._normalize_number(groups[2])
                    end_m = self._normalize_number(groups[3]) if groups[3] else "00"
                    return f"{start_h}:{start_m.zfill(2)}〜{end_h}:{end_m.zfill(2)}"
                elif len(groups) == 2:
                    start_h = self._normalize_number(groups[0])
                    start_m = self._normalize_number(groups[1]) if groups[1] else "00"
                    return f"{start_h}:{start_m.zfill(2)}〜"

        return ""

    def _extract_location(self, text: str) -> str:
        """
        テキストから開催場所を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した場所（例: "岩手県医師会館", "オンライン"）
        """
        # オンライン開催のキーワード
        online_keywords = ['オンライン', 'Web開催', 'WEB開催', 'ウェブ開催', 'Zoom', 'ZOOM', 'Teams', 'Webex', 'ライブ配信', 'オンデマンド', 'eラーニング']
        is_online = any(keyword in text for keyword in online_keywords)

        # 物理的な会場を抽出
        physical_location = self._extract_physical_location(text)

        if is_online and physical_location:
            return f"{physical_location}／オンライン"
        elif is_online:
            return "オンライン"
        else:
            return physical_location

    def _extract_physical_location(self, text: str) -> str:
        """
        テキストから物理的な会場を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            抽出した会場名
        """
        # まず「会場：」「場所：」などのラベル付きパターンを優先
        labeled_patterns = [
            # 「会場：○○」形式（施設名まで）
            r'(?:会\s*場|場\s*所|開催場所|ところ)\s*[：:]\s*([^、。\n\r]+?(?:会館|ホール|センター|病院|研修室|会議室|ビル|大学))',
            # 「会場：○○」形式（次の区切りまで）
            r'(?:会\s*場|場\s*所|開催場所)\s*[：:]\s*([^\n\r、。]{3,25})',
        ]

        for pattern in labeled_patterns:
            match = re.search(pattern, text)
            if match:
                location = match.group(1).strip()
                # 不正なパターンを除外
                if self._is_valid_location(location):
                    return self._clean_location(location)

        # ラベルがない場合は施設名パターンで探す
        # ただし、日付や年度を含むものは除外
        facility_patterns = [
            # 「○○医師会館」「○○県医師会」形式
            r'((?:岩手|青森|秋田|宮城|山形|福島|北海道|東京|[^\s\d年月日]{2,6})(?:県|市)?医師会(?:館)?)',
            # 「○○会館」「○○ホール」形式
            r'((?:[^\s\d年月日令和]{2,10})(?:会館|ホール|センター|研修室|会議室))',
            # 「○○大学」形式
            r'((?:[^\s\d年月日]{2,8})(?:大学|大学院))',
            # 「○○病院」形式
            r'((?:[^\s\d年月日]{2,10})病院)',
        ]

        for pattern in facility_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                location = match.strip()
                if self._is_valid_location(location):
                    return self._clean_location(location)

        return ""

    def _is_valid_location(self, location: str) -> bool:
        """
        抽出した場所が有効かどうかをチェック

        Args:
            location: チェックする場所文字列

        Returns:
            有効ならTrue
        """
        if not location or len(location) < 3:
            return False

        # 日付や年度を含む場合は無効
        invalid_patterns = [
            r'令和\d',
            r'20\d{2}年',
            r'\d+月\d+日',
            r'\d+年度',
            r'研修会医師向け',
            r'のお知らせ',
            r'について',
            r'開催',
        ]
        for pattern in invalid_patterns:
            if re.search(pattern, location):
                return False

        return True

    def _clean_location(self, location: str) -> str:
        """
        場所文字列をクリーンアップ

        Args:
            location: クリーンアップする場所文字列

        Returns:
            クリーンアップされた場所文字列
        """
        # 前後の空白を除去
        location = location.strip()

        # 「一般社団法人」などの接頭辞を除去
        prefixes_to_remove = [
            '一般社団法人',
            '公益社団法人',
            '公益財団法人',
            '一般財団法人',
            '社団法人',
            '財団法人',
        ]
        for prefix in prefixes_to_remove:
            if location.startswith(prefix):
                location = location[len(prefix):]

        # 長すぎる場合は切り詰め
        if len(location) > 25:
            location = location[:25] + "..."

        return location.strip()

    def _normalize_number(self, text: str) -> str:
        """
        全角数字を半角に変換

        Args:
            text: 変換対象のテキスト

        Returns:
            半角数字に変換されたテキスト
        """
        if not text:
            return ""
        # 全角数字→半角数字の変換テーブル
        trans_table = str.maketrans('０１２３４５６７８９', '0123456789')
        return text.translate(trans_table)

    def _extract_seminar_info(self, text: str) -> SeminarInfo:
        """
        テキストから研修会の詳細情報を抽出

        Args:
            text: 検索対象のテキスト

        Returns:
            SeminarInfoオブジェクト
        """
        return SeminarInfo(
            units=self._extract_units(text),
            date=self._extract_date(text),
            time=self._extract_time(text),
            location=self._extract_location(text),
        )

    def get_matching_links(self, target: WatchTarget) -> List[ScrapedLink]:
        """
        一覧ページからキーワードにマッチするリンクを抽出

        Args:
            target: 監視対象サイトの設定

        Returns:
            マッチしたリンクのリスト
        """
        # 一覧ページを取得
        html = self._fetch_page(target.url)
        if html is None:
            return []

        soup = BeautifulSoup(html, "lxml")
        results: List[ScrapedLink] = []
        seen_urls: set = set()  # 重複除去用

        # 指定されたセレクタでリンクを抽出
        links = soup.select(target.link_selector)

        for link in links:
            href = link.get("href")

            # 有効なリンクかチェック
            if not self._is_valid_link(href, target.url):
                continue

            # 絶対URLに変換
            full_url = urljoin(target.url, href)

            # 重複チェック
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            # リンクテキストを取得
            link_text = link.get_text(strip=True)
            if not link_text:
                # imgタグのaltなども試す
                img = link.find("img")
                if img and img.get("alt"):
                    link_text = img.get("alt")
                else:
                    link_text = full_url  # URLをタイトルとして使用

            # キーワードマッチング
            # リンクテキストだけでなく、周囲のテキストも確認
            parent_text = ""
            if link.parent:
                parent_text = link.parent.get_text(strip=True)

            search_text = f"{link_text} {parent_text}"
            matched_keywords = [
                kw for kw in target.keywords
                if kw in search_text
            ]

            # キーワードにマッチした場合のみ追加
            if matched_keywords:
                results.append(ScrapedLink(
                    url=full_url,
                    title=link_text,
                    matched_keywords=matched_keywords,
                ))
                print(f"[Scraper] マッチ: {link_text[:40]}... (keywords: {matched_keywords})")

        print(f"[Scraper] {target.name}: {len(results)}件のマッチを検出")
        return results

    def get_page_content(self, url: str, title: str = "") -> Optional[PageContent]:
        """
        詳細ページの内容を取得してハッシュ化

        Args:
            url: ページのURL
            title: ページのタイトル（既知の場合）

        Returns:
            PageContentオブジェクト、またはNone（エラー時）
        """
        # サーバー負荷軽減のため少し待機
        time.sleep(REQUEST_DELAY)

        html = self._fetch_page(url)
        if html is None:
            return None

        soup = BeautifulSoup(html, "lxml")

        # タイトルを取得（引数で指定されていなければ）
        if not title:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else url

        # 本文テキストを抽出
        body_text = self._extract_text(soup)

        # ハッシュ値を計算
        content_hash = self._compute_hash(body_text)

        # 研修会の詳細情報を抽出
        seminar_info = self._extract_seminar_info(body_text)

        # 抽出結果をログ出力
        if seminar_info.units or seminar_info.date:
            print(f"[Scraper] 詳細: 単位={seminar_info.units}, 日時={seminar_info.date} {seminar_info.time}, 場所={seminar_info.location}")

        # 説明文を生成（最初の200文字程度）
        description = body_text[:200] + "..." if len(body_text) > 200 else body_text

        return PageContent(
            url=url,
            title=title,
            content_hash=content_hash,
            description=description,
            seminar_info=seminar_info,
        )

    def close(self):
        """セッションをクローズ"""
        self.session.close()
