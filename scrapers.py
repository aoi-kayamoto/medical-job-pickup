"""
スクレイパー群：CrowdWorks / Lancers / Coconala / Indeed 対応
配布用の動作実績あるシンプル版 + 詐欺判定をハイブリッド統合
"""
import re
import time
import random
import sqlite3
import logging
import feedparser

import requests
import cloudscraper
from bs4 import BeautifulSoup

from keywords import classify_job
from database import insert_job, log_fetch, DB_PATH

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# cloudscraper: Cloudflare・Renderサーバーブロック回避用
# ローカルとRenderどちらでも動く共通セッション
def _make_scraper():
    return cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )

# ── 検索ワード（配布用の実績あるリストを使用）──
MEDICAL_TERMS  = ["看護師", "訪問看護", "医療ライター", "記事監修", "美容クリニック", "医療系"]
WRITER_TERMS   = ["Webライター", "コンテンツライター", "ライター 募集"]
SNS_TERMS      = ["SNS運用", "Instagram運用", "インスタ運用"]
ALL_SEARCH_TERMS = MEDICAL_TERMS + WRITER_TERMS[:2] + SNS_TERMS[:2]

# Indeedは専用の検索クエリリストを使用（配布版と同じ）
INDEED_QUERIES = [
    "看護師 業務委託",
    "訪問看護 パート",
    "医療ライター",
    "美容クリニック 看護師",
    "ヘルスケア ライター",
    "Webライター 在宅",
    "SNS運用 業務委託",
    "Instagram運用 フリーランス",
]

# CrowdWorksの案件URLパターン
_CW_JOB_URL_RE = re.compile(r'/public/jobs/\d+')


def _process_item(source, title, description, url, budget, posted_at) -> tuple[bool, bool]:
    """
    分類・保存を行い (was_new: bool, was_scam: bool) を返す。
    """
    if not title or not url:
        return False, False

    result = classify_job(title, description, source=source)

    if result["is_scam"]:
        logger.debug(f"[SCAM] {title[:40]} | score={result['scam_score']}")
        insert_job(
            source, title, description, url, budget, posted_at,
            matched_keywords=[], job_tier=0, is_scam=1,
            scam_score=result["scam_score"],
            scam_reasons=result["scam_reasons"],
            categories=[],
        )
        return False, True

    if result["tier"] is None:
        return False, False

    was_new = insert_job(
        source, title, description, url, budget, posted_at,
        matched_keywords=result["matched_keywords"],
        job_tier=result["tier"], is_scam=0,
        scam_score=result["scam_score"],
        scam_reasons=result["scam_reasons"],
        categories=result["categories"],
    )
    if was_new:
        tier_label = "🏥医療" if result["tier"] == 1 else "📂一般"
        logger.info(f"[NEW {tier_label}] {title[:50]} ({source})")
    return was_new, False


# ─────────────────────────────────────
# CrowdWorks（requests版 ＋ Playwright フォールバック）
# ─────────────────────────────────────
def scrape_crowdworks() -> tuple[int, int]:
    source = "CrowdWorks"
    total_new, total_scam = 0, 0
    seen_urls: set[str] = set()

    for term in ALL_SEARCH_TERMS:
        try:
            url = f"https://crowdworks.jp/public/jobs/search?keyword={requests.utils.quote(term)}&order=new"
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            links = soup.select("a[href*='/public/jobs/']")
            job_links = [l for l in links if _CW_JOB_URL_RE.search(l.get("href", ""))]
            logger.info(f"CrowdWorks '{term}': {len(job_links)} jobs found")

            for link in job_links:
                try:
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)
                    job_url = "https://crowdworks.jp" + href if href.startswith("/") else href
                    title = link.get_text(strip=True)
                    if not title:
                        continue

                    # 詳細ページを取得して本文をスキャン
                    description = ""
                    try:
                        dr = requests.get(job_url, headers=HEADERS, timeout=10)
                        if dr.status_code == 200:
                            ds = BeautifulSoup(dr.text, "lxml")
                            el = ds.find(class_=re.compile(r"job_detail|detail"))
                            if not el:
                                el = ds.find("body")
                            if el:
                                description = el.get_text(" ", strip=True)
                    except Exception:
                        pass

                    is_new, is_scam = _process_item(source, title, description, job_url, None, None)
                    if is_new: total_new += 1
                    if is_scam: total_scam += 1
                except Exception as e:
                    logger.debug(f"CrowdWorks item error: {e}")
            time.sleep(1)
        except Exception as e:
            logger.warning(f"CrowdWorks fetch error ({term}): {e}")

    log_fetch(source, total_new, scam_blocked=total_scam)
    return total_new, total_scam


# ─────────────────────────────────────
# Lancers
# ─────────────────────────────────────
def scrape_lancers() -> tuple[int, int]:
    source = "Lancers"
    total_new, total_scam = 0, 0

    for term in ALL_SEARCH_TERMS:
        try:
            url = f"https://www.lancers.jp/work/search?keyword={requests.utils.quote(term)}&open=1"
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            job_items = soup.select(
                ".work-item, .job-list__item, li[class*='work'], "
                "[class*='WorkItem'], [class*='work-card'], [class*='workCard']"
            )
            if not job_items:
                job_items = soup.select("a[href*='/work/detail/']")
            logger.info(f"Lancers '{term}': {len(job_items)} items found")

            seen_urls: set[str] = set()
            for item in job_items:
                try:
                    if item.name == "a":
                        title = item.get_text(strip=True)
                        job_url = "https://www.lancers.jp" + item["href"] if item["href"].startswith("/") else item["href"]
                    else:
                        link = item.find("a", href=lambda h: h and "/work/detail/" in h)
                        if not link:
                            continue
                        title = link.get_text(strip=True) or item.get_text(strip=True)[:80]
                        job_url = "https://www.lancers.jp" + link["href"] if link["href"].startswith("/") else link["href"]

                    if not title or job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    desc_el = item.find(class_=lambda c: c and ("description" in c or "detail" in c or "body" in c))
                    description = desc_el.get_text(strip=True) if desc_el else ""

                    # 詳細ページ取得
                    try:
                        dr = requests.get(job_url, headers=HEADERS, timeout=10)
                        if dr.status_code == 200:
                            ds = BeautifulSoup(dr.text, "lxml")
                            el = ds.find(class_=re.compile(r'work-detail|work_detail|detail-description'))
                            if not el:
                                el = ds.select_one('.c-entry-detail__text, .p-work-detail__text, main')
                            if el:
                                description = el.get_text(" ", strip=True)
                    except Exception:
                        pass

                    is_new, is_scam = _process_item(source, title, description, job_url, None, None)
                    if is_new: total_new += 1
                    if is_scam: total_scam += 1
                except Exception as e:
                    logger.debug(f"Lancers item error: {e}")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Lancers fetch error ({term}): {e}")

    log_fetch(source, total_new, scam_blocked=total_scam)
    return total_new, total_scam


# ─────────────────────────────────────
# Coconala（サービス募集）
# ─────────────────────────────────────
def scrape_coconala() -> tuple[int, int]:
    source = "Coconala"
    total_new, total_scam = 0, 0

    for term in ALL_SEARCH_TERMS:
        try:
            url = f"https://coconala.com/requests?keyword={requests.utils.quote(term)}"
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            seen_urls: set[str] = set()
            for link in soup.select("a[href*='/requests/']"):
                try:
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)
                    job_url = "https://coconala.com" + href if href.startswith("/") else href
                    title = link.get_text(strip=True)
                    if not title:
                        continue

                    description = ""
                    try:
                        dr = requests.get(job_url, headers=HEADERS, timeout=10)
                        if dr.status_code == 200:
                            ds = BeautifulSoup(dr.text, "lxml")
                            description = ds.body.get_text(" ", strip=True) if ds.body else ""
                    except Exception:
                        pass

                    is_new, is_scam = _process_item(source, title, description, job_url, None, None)
                    if is_new: total_new += 1
                    if is_scam: total_scam += 1
                except Exception as e:
                    logger.debug(f"Coconala item error: {e}")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Coconala fetch error ({term}): {e}")

    log_fetch(source, total_new, scam_blocked=total_scam)
    return total_new, total_scam


# ─────────────────────────────────────
# Indeed（RSS優先 → cloudscraper HTML フォールバック）
# ─────────────────────────────────────
def scrape_indeed() -> tuple[int, int]:
    source = "Indeed"
    total_new, total_scam = 0, 0
    seen_urls: set[str] = set()

    for query in INDEED_QUERIES:
        try:
            encoded = requests.utils.quote(query)
            got_results = False

            # ── 方法1: RSSフィード（ブロックされにくい）──
            try:
                rss_url = f"https://jp.indeed.com/rss?q={encoded}&sort=date&fromage=14"
                feed = feedparser.parse(rss_url)
                entries = feed.entries
                logger.info(f"Indeed RSS '{query}': {len(entries)} entries")

                for entry in entries:
                    title = entry.get("title", "").strip()
                    job_url = entry.get("link", "").strip()
                    jk_match = re.search(r"jk=([a-zA-Z0-9]+)", job_url)
                    if jk_match:
                        job_url = f"https://jp.indeed.com/viewjob?jk={jk_match.group(1)}"
                    if not title or not job_url or job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)
                    description = entry.get("summary", "")
                    is_new, is_scam = _process_item(source, title, description, job_url, None, None)
                    if is_new: total_new += 1
                    if is_scam: total_scam += 1
                    got_results = True
            except Exception as e:
                logger.warning(f"Indeed RSS error ({query}): {e}")

            # ── 方法2: cloudscraper HTML（RSSが空のときのみ）──
            if not got_results:
                try:
                    scraper = _make_scraper()
                    html_url = f"https://jp.indeed.com/jobs?q={encoded}&sort=date&fromage=14"
                    res = scraper.get(html_url, timeout=20)
                    logger.info(f"Indeed HTML '{query}': HTTP {res.status_code}, size={len(res.text)}")
                    if res.status_code == 200:
                        soup = BeautifulSoup(res.text, "lxml")
                        for selector in ["a[data-jk]", "[class*='jobTitle'] a", "h2 a"]:
                            cards = soup.select(selector)
                            if cards:
                                logger.info(f"Indeed HTML '{query}': {len(cards)} cards via '{selector}'")
                                for card in cards:
                                    href = card.get("href", "")
                                    if not href or href in seen_urls: continue
                                    seen_urls.add(href)
                                    job_url = "https://jp.indeed.com" + href if href.startswith("/") else href
                                    title = card.get_text(strip=True)
                                    if not title: continue
                                    is_new, is_scam = _process_item(source, title, "", job_url, None, None)
                                    if is_new: total_new += 1
                                    if is_scam: total_scam += 1
                                break
                        else:
                            preview = soup.get_text()[:200].replace("\n", " ")
                            logger.warning(f"Indeed HTML '{query}': 0 cards. Preview: {preview}")
                except Exception as e:
                    logger.warning(f"Indeed cloudscraper error ({query}): {e}")

            time.sleep(2)
        except Exception as e:
            logger.warning(f"Indeed fetch error ({query}): {e}")

    status = "done" if (total_new + total_scam) > 0 else "empty"
    log_fetch(source, total_new, scam_blocked=total_scam, status=status)
    return total_new, total_scam


# ─────────────────────────────────────
# 求人ボックス（RSS優先 → cloudscraper HTML フォールバック）
# ─────────────────────────────────────
def scrape_kyujinbox() -> tuple[int, int]:
    source = "求人ボックス"
    total_new, total_scam = 0, 0
    seen_urls: set[str] = set()
    BASE = "https://xn--pckua2a7gp15o89zb.com"

    for term in MEDICAL_TERMS[:5]:
        for work_type in ["業務委託", "フリーランス"]:
            try:
                query = f"{term} {work_type}"
                encoded = requests.utils.quote(query)
                got_results = False

                # ── 方法1: RSSフィード ──
                try:
                    rss_url = f"{BASE}/rss?q={encoded}"
                    feed = feedparser.parse(rss_url)
                    entries = feed.entries
                    logger.info(f"KyujinBox RSS '{query}': {len(entries)} entries")

                    for entry in entries:
                        title = entry.get("title", "").strip()
                        job_url = entry.get("link", "").strip()
                        description = entry.get("summary", "")
                        if not title or not job_url or job_url in seen_urls: continue
                        seen_urls.add(job_url)
                        is_new, is_scam = _process_item(source, title, description, job_url, None, None)
                        if is_new: total_new += 1
                        if is_scam: total_scam += 1
                        got_results = True
                except Exception as e:
                    logger.warning(f"KyujinBox RSS error ({query}): {e}")

                # ── 方法2: cloudscraper HTML（RSSが空のときのみ）──
                if not got_results:
                    try:
                        scraper = _make_scraper()
                        html_url = f"{BASE}/{encoded}%E3%81%AE%E4%BB%95%E4%BA%8B?ou=1"
                        res = scraper.get(html_url, timeout=20)
                        logger.info(f"KyujinBox HTML '{query}': HTTP {res.status_code}")
                        if res.status_code == 200:
                            soup = BeautifulSoup(res.text, "lxml")
                            found = False
                            for selector in [".p-result_title a", "h2 a", ".p-entry_title a"]:
                                links = soup.select(selector)
                                if links:
                                    logger.info(f"KyujinBox HTML '{query}': {len(links)} via '{selector}'")
                                    for a in links:
                                        title = a.get_text(strip=True)
                                        href = a.get("href", "")
                                        if not title or not href: continue
                                        link = href if href.startswith("http") else BASE + href
                                        if link in seen_urls: continue
                                        seen_urls.add(link)
                                        is_new, is_scam = _process_item(source, title, "", link, None, None)
                                        if is_new: total_new += 1
                                        if is_scam: total_scam += 1
                                    found = True
                                    break
                            if not found:
                                preview = soup.get_text()[:300].replace("\n", " ")
                                logger.warning(f"KyujinBox HTML: no jobs. Preview: {preview}")
                    except Exception as e:
                        logger.warning(f"KyujinBox cloudscraper error ({query}): {e}")

                time.sleep(2)
            except Exception as e:
                logger.warning(f"KyujinBox fetch error ({term} {work_type}): {e}")

    status = "done" if (total_new + total_scam) > 0 else "empty"
    log_fetch(source, total_new, scam_blocked=total_scam, status=status)
    return total_new, total_scam



# ─────────────────────────────────────
# ママワークス（Playwright）
# ─────────────────────────────────────
def scrape_mamaworks() -> tuple[int, int]:
    source = "Mamaworks"
    total_new, total_scam = 0, 0
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--single-process"]
            )
            for term in MEDICAL_TERMS[:2]:
                try:
                    page = browser.new_page()
                    page.goto(f"https://mamaworks.jp/list/?keyword={requests.utils.quote(term)}", timeout=20000)
                    page.wait_for_timeout(3000)
                    links = page.eval_on_selector_all('a[href*="/job/"]', "elements => elements.map(el => [el.href, el.innerText])")
                    seen_urls: set[str] = set()
                    for link, text_content in links:
                        if not link.startswith("http"):
                            link = "https://mamaworks.jp" + link
                        if link in seen_urls:
                            continue
                        seen_urls.add(link)
                        title_lines = [l.strip() for l in text_content.split('\n') if l.strip()]
                        if not title_lines:
                            continue
                        title = title_lines[0]
                        if title in ["NEW", "急募", "在宅"]:
                            title = title_lines[1] if len(title_lines) > 1 else title
                        is_new, is_scam = _process_item(source, title, "", link, None, None)
                        if is_new: total_new += 1
                        if is_scam: total_scam += 1
                    page.close()
                except Exception as e:
                    logger.warning(f"Mamaworks term error ({term}): {e}")
            browser.close()
    except Exception as e:
        logger.error(f"Mamaworks fatal error: {e}")
        log_fetch(source, 0, status="error", message=str(e)[:100])
        return 0, 0

    log_fetch(source, total_new, scam_blocked=total_scam)
    return total_new, total_scam


# ─────────────────────────────────────
# メイン実行
# ─────────────────────────────────────
def run_all_scrapers() -> dict:
    results = {}
    logger.info("=== スクレイピング開始 ===")

    for name, func in [
        ("Lancers", scrape_lancers),
        ("Coconala", scrape_coconala),
        ("CrowdWorks", scrape_crowdworks),
        ("Indeed", scrape_indeed),
        ("求人ボックス", scrape_kyujinbox),
        ("Mamaworks", scrape_mamaworks),
    ]:
        try:
            logger.info(f"{name} スクレイピング中...")
            new, scam = func()
            results[name] = {"new": new, "scam_blocked": scam}
            logger.info(f"  → 新規: {new}件  詐欺ブロック: {scam}件")
        except Exception as e:
            logger.error(f"{name} failed: {e}")
            results[name] = {"new": 0, "scam_blocked": 0}
            log_fetch(name, 0, status="error", message=f"致命的エラー: {str(e)[:50]}")

    total_new = sum(v["new"] for v in results.values())
    total_scam = sum(v["scam_blocked"] for v in results.values())
    logger.info(f"=== 完了: 新規 {total_new}件 / 詐欺ブロック {total_scam}件 ===")

    _cleanup_stale_jobs()
    return results


def _cleanup_stale_jobs():
    """DBに保存済みの案件を現在のフィルターで再評価し、対象外になったものを削除する"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, source, title, description FROM jobs WHERE is_scam=0")
    to_delete = []
    for job_id, source, title, desc in c.fetchall():
        r = classify_job(title or "", desc or "", source=source)
        if r["tier"] is None:
            to_delete.append(job_id)
    if to_delete:
        c.executemany("DELETE FROM jobs WHERE id=?", [(i,) for i in to_delete])
        conn.commit()
        logger.info(f"[クリーンアップ] 対象外データ {len(to_delete)}件を削除")
    conn.close()
