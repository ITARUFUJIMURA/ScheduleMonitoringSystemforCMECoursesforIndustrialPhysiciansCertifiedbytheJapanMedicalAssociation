# ========================================
# config.py - 監視対象サイトとキーワードの設定
# ========================================
#
# このファイルでは、巡回するWebサイトのURLと
# 検索に使うキーワードを定義しています。
# 新しいサイトを追加したい場合は、WATCH_TARGETS に追記してください。
# ========================================

from dataclasses import dataclass
from typing import List


@dataclass
class WatchTarget:
    """
    監視対象サイトの設定を保持するクラス

    Attributes:
        name: サイトの識別名（ログやDBで使用）
        url: 一覧ページのURL
        keywords: 検索キーワードのリスト（いずれかにマッチすれば対象）
        link_selector: リンクを抽出するCSSセレクタ（サイトごとに調整）
    """
    name: str
    url: str
    keywords: List[str]
    link_selector: str = "a"  # デフォルトは全てのリンク


# ========================================
# 監視対象サイトの一覧
# ========================================
WATCH_TARGETS = [
    # 1) 岩手県医師会 - 研修会カテゴリ
    WatchTarget(
        name="iwate_med",
        url="https://www.iwate.med.or.jp/category/workshop/",
        keywords=["産業医", "産業医研修会", "実地研修会", "産業医学基本講座"],
        link_selector="article a, .post a, .entry a, a"  # 記事内のリンク
    ),

    # 2) 岩手産業保健総合支援センター - セミナー
    WatchTarget(
        name="iwates_johas_seminar",
        url="https://www.iwates.johas.go.jp/seminar/",
        keywords=["産業医", "日本医師会認定産業医", "生涯研修", "２単位", "2単位"],
        link_selector="a"
    ),

    # 3) 岩手産業保健総合支援センター - 産業医研修
    WatchTarget(
        name="iwates_johas_training",
        url="https://www.iwates.johas.go.jp/industrialphysician-training/",
        keywords=["〖限定〗産業医研修", "日本医師会認定産業医", "生涯研修", "２単位", "2単位"],
        link_selector="a"
    ),

    # 4) 日本産業医協会 - セミナー
    WatchTarget(
        name="sangyo_doctors",
        url="https://www.sangyo-doctors.gr.jp/seminar/",
        keywords=["産業医", "認定産業医", "生涯"],
        link_selector="a"
    ),

    # 5) 日本医師会 - Web研修会
    WatchTarget(
        name="med_or_jp",
        url="https://seminar.med.or.jp/",
        keywords=["産業医Web研修会", "認定産業医", "生涯", "申込み", "申込"],
        link_selector="a"
    ),
]


# ========================================
# RSS設定
# ========================================
RSS_CONFIG = {
    "title": "産業医講習会 新着情報",
    "description": "日本医師会認定産業医の単位講習（岩手県盛岡市中心＋全国）の新着・更新情報",
    "link": "https://itarufujimura.github.io/ScheduleMonitoringSystemforCMECoursesforIndustrialPhysiciansCertifiedbytheJapanMedicalAssociation/feed.xml",
    "language": "ja",
}


# ========================================
# ファイルパス設定
# ========================================
import os

# プロジェクトのルートディレクトリを取得
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 各種ファイルのパス
DATABASE_PATH = os.path.join(PROJECT_ROOT, "data", "state.sqlite3")
RSS_OUTPUT_PATH = os.path.join(PROJECT_ROOT, "docs", "feed.xml")
