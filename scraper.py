"""
Reuters News Scraper
====================
Collects latest articles from Reuters via Google News RSS feeds,
then resolves redirect URLs to actual Reuters article URLs using Selenium (headless).
Saves results to reuters_news.csv with deduplication by URL.

Note: Direct scraping of reuters.com is blocked by DataDome CAPTCHA protection.
This scraper uses Google News RSS feeds filtered for reuters.com as a reliable alternative.
"""

import csv
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reuters_news.csv")
CSV_COLUMNS = ["title", "url", "published_at", "category", "scraped_at"]

CHROME_BINARY = os.environ.get("CHROME_BINARY", "/tmp/chrome-linux64/chrome")
CHROMEDRIVER_BINARY = os.environ.get("CHROMEDRIVER_BINARY", "/usr/local/bin/chromedriver")

# Google News RSS feeds filtered for reuters.com, one per category
CATEGORY_FEEDS = {
    "World": "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
    "Business": "https://news.google.com/rss/search?q=site:reuters.com+business&hl=en-US&gl=US&ceid=US:en",
    "Technology": "https://news.google.com/rss/search?q=site:reuters.com+technology&hl=en-US&gl=US&ceid=US:en",
    "Markets": "https://news.google.com/rss/search?q=site:reuters.com+markets&hl=en-US&gl=US&ceid=US:en",
}

REQUEST_DELAY = 1.5  # seconds between page loads (respect rate limits)
MAX_ARTICLES_PER_CATEGORY = 25  # limit per category to keep scrape fast


# ---------------------------------------------------------------------------
# RSS Fetching
# ---------------------------------------------------------------------------

def _fetch_rss(feed_url: str) -> list[dict]:
    """Fetch and parse a Google News RSS feed, returning raw article dicts."""
    req = Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urlopen(req, timeout=15)
    content = resp.read().decode("utf-8")
    root = ET.fromstring(content)

    articles: list[dict] = []
    for item in root.findall(".//item"):
        title_el = item.find("title")
        link_el = item.find("link")
        pub_el = item.find("pubDate")
        source_el = item.find("source")

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        gnews_link = link_el.text.strip() if link_el is not None and link_el.text else ""
        pub_date_str = pub_el.text.strip() if pub_el is not None and pub_el.text else ""
        source = source_el.text.strip() if source_el is not None and source_el.text else ""

        # Only keep Reuters articles
        if source and "Reuters" not in source:
            continue

        # Clean title (remove " - Reuters" suffix)
        title = re.sub(r"\s*[-\u2013]\s*Reuters\s*$", "", title)

        # Parse published date
        published_at = ""
        if pub_date_str:
            try:
                dt = parsedate_to_datetime(pub_date_str)
                published_at = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                published_at = pub_date_str

        articles.append(
            {
                "title": title,
                "gnews_url": gnews_link,
                "published_at": published_at,
            }
        )

    return articles


# ---------------------------------------------------------------------------
# URL Resolution via Selenium
# ---------------------------------------------------------------------------

def _create_driver() -> webdriver.Chrome:
    """Create a headless Chrome WebDriver instance for URL resolution."""
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
    )
    service = Service(executable_path=CHROMEDRIVER_BINARY)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(20)
    return driver


def _resolve_urls(articles: list[dict], driver: webdriver.Chrome) -> list[dict]:
    """Resolve Google News redirect URLs to actual Reuters URLs using Selenium."""
    resolved: list[dict] = []
    for i, art in enumerate(articles):
        gnews_url = art["gnews_url"]
        try:
            driver.get(gnews_url)
            time.sleep(1)  # allow redirect
            final_url = driver.current_url

            if "reuters.com" in final_url:
                art["url"] = final_url
            else:
                art["url"] = gnews_url
        except Exception:
            art["url"] = gnews_url

        resolved.append(art)

        if (i + 1) % 10 == 0:
            print(f"    Resolved {i + 1}/{len(articles)} URLs...")
            time.sleep(REQUEST_DELAY)

    return resolved


# ---------------------------------------------------------------------------
# CSV I/O
# ---------------------------------------------------------------------------

def _load_existing_urls() -> set[str]:
    """Load already-saved URLs to avoid duplicates."""
    if not os.path.exists(CSV_FILE):
        return set()
    try:
        df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")
        return set(df["url"].dropna().tolist())
    except Exception:
        return set()


def _save_articles(articles: list[dict]) -> int:
    """Append new articles to CSV, skipping duplicates. Returns count of new rows."""
    existing_urls = _load_existing_urls()
    new_articles = [a for a in articles if a.get("url", "") not in existing_urls]

    if not new_articles:
        return 0

    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for art in new_articles:
            writer.writerow(
                {
                    "title": art["title"],
                    "url": art["url"],
                    "published_at": art["published_at"],
                    "category": art.get("category", ""),
                    "scraped_at": art.get("scraped_at", ""),
                }
            )

    return len(new_articles)


# ---------------------------------------------------------------------------
# Main scraper
# ---------------------------------------------------------------------------

def scrape_reuters(
    categories: dict[str, str] | None = None,
    resolve_urls: bool = True,
    max_per_category: int = MAX_ARTICLES_PER_CATEGORY,
) -> list[dict]:
    """
    Scrape Reuters articles via Google News RSS feeds.

    Parameters
    ----------
    categories : dict mapping category name -> RSS feed URL.
    resolve_urls : if True, use Selenium to resolve Google News URLs to Reuters URLs.
    max_per_category : max articles to collect per category.

    Returns
    -------
    List of all collected article dicts.
    """
    if categories is None:
        categories = CATEGORY_FEEDS

    all_articles: list[dict] = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Fetch RSS feeds
    for cat_name, feed_url in categories.items():
        print(f"[scraper] Fetching RSS for {cat_name}...")
        try:
            raw = _fetch_rss(feed_url)
            raw = raw[:max_per_category]
            for art in raw:
                art["category"] = cat_name
                art["scraped_at"] = now_str
            print(f"  -> Got {len(raw)} articles from {cat_name}")
            all_articles.extend(raw)
        except Exception as e:
            print(f"  [error] Failed to fetch {cat_name}: {e}")
        time.sleep(REQUEST_DELAY)

    if not all_articles:
        print("[scraper] No articles found in RSS feeds.")
        return []

    # Step 2: Resolve URLs via Selenium
    if resolve_urls:
        print(f"\n[scraper] Resolving {len(all_articles)} URLs via Selenium...")
        driver = _create_driver()
        try:
            all_articles = _resolve_urls(all_articles, driver)
        finally:
            driver.quit()
    else:
        for art in all_articles:
            art["url"] = art.get("gnews_url", "")

    # Step 3: Save to CSV
    saved_count = _save_articles(all_articles)
    print(f"\n[scraper] Total collected: {len(all_articles)}, Newly saved: {saved_count}")
    return all_articles


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("Reuters News Scraper")
    print("=" * 60)
    results = scrape_reuters()
    if results:
        print(f"\nSample articles:")
        for art in results[:5]:
            print(f"  - {art['title'][:80]}")
            print(f"    URL: {art['url'][:100]}")
            print(f"    Published: {art['published_at']}")
            print()
    else:
        print("No articles collected.")
