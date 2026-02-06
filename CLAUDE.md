# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## プロジェクト概要

日本医師会認定産業医の単位講習情報を自動巡回し、新着・更新をRSSフィードで配信するシステム。
GitHub Actions で毎日06:00 JST に実行される。

RSSタイトル形式: `【単位】タイトル - 日時 @場所`

## コマンド

```bash
# 仮想環境のセットアップ
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 通常実行（巡回してRSS更新）
python watcher.py

# 初期化（DB・RSS作成）
python watcher.py --init

# テスト実行（DB・RSSは更新しない）
python watcher.py --dry-run
```

## アーキテクチャ

```
watcher.py              # エントリポイント
src/
├── config.py           # 監視対象URL・キーワード設定
├── scraper.py          # スクレイピング（単位・日時・場所抽出含む）
├── database.py         # SQLite状態管理
├── rss_generator.py    # RSS生成（タイトルに詳細情報埋め込み）
└── notifier.py         # メール通知（未実装スタブ）
```

## 処理フロー

1. 各監視対象サイトの一覧ページを取得
2. キーワードにマッチするリンクを抽出
3. 詳細ページから単位・日時・場所を抽出し、ハッシュ化
4. DBと比較して新規/更新を判定
5. 変更があればRSSを再生成

## 監視対象の追加

`src/config.py` の `WATCH_TARGETS` に追加:

```python
WatchTarget(
    name="site_id",
    url="https://...",
    keywords=["キーワード"],
    link_selector="a"
)
```

## 抽出ロジック

- **単位**: 「生涯2単位」「基礎1単位」等のパターンを正規表現で抽出
- **日時**: 「令和N年M月D日」「20XX年M月D日」等を西暦に正規化
- **場所**: 「会場：」ラベル優先、施設名パターン（○○会館、○○医師会）で抽出

## GitHub連携

1. リポジトリ作成 → push
2. Settings → Pages → Source: `main` / `/docs`
3. `src/config.py` の `RSS_CONFIG["link"]` を実際のURLに変更
