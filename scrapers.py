"""
スクレイパー群：CrowdWorks / Lancers / Coconala / Indeed 対応
"""
import re
import feedparser
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time
import logging

from keywords import is_target_job, extract_matched_keywords
from database import insert_job, log_fetch

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

# 医療・看護系（上位4件がCrowdWorks/Lancers検索に使われる）
MEDICAL_TERMS = ["看護師", "訪問看護", "医療ライター", "記事監修", "美容クリニック", "医療系"]
# ライター系
WRITER_TERMS = ["Webライター", "コンテンツライター", "ライター 募集"]
# SNS運用系
SNS_TERMS = ["SNS運用", "Instagram運用", "インスタ運用"]

# 後方互換用（Indeedスクレイパーは独自リストを持つが念のため）
NURSING_SEARCH_TERMS = MEDICAL_TERMS + WRITER_TERMS + SNS_TERMS

# 全スクレイパーが検索する統合リスト（医療4 + ライター2 + SNS2）
ALL_SEARCH_TERMS = MEDICAL_TERMS[:4] + WRITER_TERMS[:2] + SNS_TERMS[:2]


# CrowdWorksの案件URLパターン（/public/jobs/数字 のみ対象）
_CW_JOB_URL_RE = re.compile(r'/public/jobs/\d+')


# ─────────────────────────────────────
# CrowdWorks（requests版）
# ─────────────────────────────────────
def scrape_crowdworks() -> int:
    source = "CrowdWorks"
    total_new = 0
    seen_urls = set()

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
                    if not title or not is_target_job(title, ""):
                        continue
                    matched = extract_matched_keywords(title)
                    if insert_job(source, title, "", job_url, None, None, matched):
                        total_new += 1
                except Exception as e:
                    logger.debug(f"CrowdWorks item parse error: {e}")

            time.sleep(1)
        except Exception as e:
            logger.warning(f"CrowdWorks fetch error ({term}): {e}")

    log_fetch(source, total_new, "success")
    return total_new


# ─────────────────────────────────────
# Lancers
# ─────────────────────────────────────
def scrape_lancers() -> int:
    source = "Lancers"
    total_new = 0
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

            seen_urls = set()
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

                    if not is_target_job(title, description):
                        continue

                    matched = extract_matched_keywords(f"{title} {description}")
                    if insert_job(source, title, description, job_url, None, None, matched):
                        total_new += 1
                except Exception as e:
                    logger.debug(f"Lancers item parse error: {e}")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Lancers fetch error ({term}): {e}")

    log_fetch(source, total_new, "success")
    return total_new


# ─────────────────────────────────────
# Coconala（サービス募集）
# ─────────────────────────────────────
def scrape_coconala() -> int:
    source = "Coconala"
    total_new = 0
    for term in ALL_SEARCH_TERMS:
        try:
            url = f"https://coconala.com/requests?keyword={requests.utils.quote(term)}"
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            job_items = soup.select("a[href*='/requests/']")
            seen_urls = set()
            for link in job_items:
                try:
                    href = link.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)
                    job_url = "https://coconala.com" + href if href.startswith("/") else href
                    title = link.get_text(strip=True)
                    if not title:
                        continue

                    if not is_target_job(title):
                        continue

                    matched = extract_matched_keywords(title)
                    if insert_job(source, title, "", job_url, None, None, matched):
                        total_new += 1
                except Exception as e:
                    logger.debug(f"Coconala item parse error: {e}")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Coconala fetch error ({term}): {e}")

    log_fetch(source, total_new, "success")
    return total_new


# ─────────────────────────────────────
# Indeed（RSS フィード経由）
# ─────────────────────────────────────
def scrape_indeed() -> int:
    source = "Indeed"
    total_new = 0
    search_queries = [
        "看護師 業務委託",
        "訪問看護 パート",
        "医療ライター",
        "美容クリニック 看護師",
        "ヘルスケア ライター",
        "Webライター 在宅",
        "SNS運用 業務委託",
        "Instagram運用 フリーランス",
    ]
    seen_urls = set()
    for query in search_queries:
        try:
            encoded = requests.utils.quote(query)
            url = f"https://jp.indeed.com/jobs?q={encoded}&l=&sort=date&fromage=7"
            res = requests.get(url, headers=HEADERS, timeout=15)
            res.raise_for_status()
            soup = BeautifulSoup(res.text, "lxml")

            job_cards = soup.select("a[data-jk], a[id^='job_'], .job_seen_beacon a, [class*='jobTitle'] a")
            if not job_cards:
                job_cards = soup.select("a[href*='/rc/clk'], a[href*='clk?jk=']")

            logger.info(f"Indeed '{query}': {len(job_cards)} jobs found")

            for card in job_cards:
                try:
                    href = card.get("href", "")
                    if not href or href in seen_urls:
                        continue
                    seen_urls.add(href)
                    job_url = "https://jp.indeed.com" + href if href.startswith("/") else href
                    title = card.get_text(strip=True)
                    if not title:
                        parent = card.find_parent(class_=lambda c: c and "title" in c.lower())
                        title = parent.get_text(strip=True) if parent else ""
                    if not title or not is_target_job(title, ""):
                        continue

                    matched = extract_matched_keywords(title)
                    if insert_job(source, title, "", job_url, None, None, matched):
                        total_new += 1
                except Exception as e:
                    logger.debug(f"Indeed item parse error: {e}")
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Indeed fetch error ({query}): {e}")

    log_fetch(source, total_new, "success")
    return total_new


# ─────────────────────────────────────
# メイン実行
# ─────────────────────────────────────
def run_all_scrapers() -> dict:
    results = {}
    logger.info("=== スクレイピング開始 ===")

    logger.info("CrowdWorks スクレイピング中...")
    results["CrowdWorks"] = scrape_crowdworks()

    logger.info("Lancers スクレイピング中...")
    results["Lancers"] = scrape_lancers()

    logger.info("Coconala スクレイピング中...")
    results["Coconala"] = scrape_coconala()

    logger.info("Indeed スクレイピング中...")
    results["Indeed"] = scrape_indeed()

    total = sum(results.values())
    logger.info(f"=== スクレイピング完了: 新規 {total} 件 ===")
    return results
