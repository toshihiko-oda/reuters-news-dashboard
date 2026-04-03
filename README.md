# Reuters News Dashboard

Reuters news articles monitoring dashboard with scraping and visualization.

## Setup

```bash
pip install -r requirements.txt
```

### Chrome for Testing (required for scraper)

The scraper uses Selenium with headless Chrome. You need Chrome for Testing and matching ChromeDriver:

```bash
# Download Chrome for Testing and ChromeDriver (adjust version as needed)
curl -sL "https://storage.googleapis.com/chrome-for-testing-public/147.0.7727.50/linux64/chrome-linux64.zip" -o /tmp/chrome.zip
curl -sL "https://storage.googleapis.com/chrome-for-testing-public/147.0.7727.50/linux64/chromedriver-linux64.zip" -o /tmp/chromedriver.zip
unzip -qo /tmp/chrome.zip -d /tmp/
unzip -qo /tmp/chromedriver.zip -d /tmp/
sudo mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver
sudo chmod +x /usr/local/bin/chromedriver
```

You can customize paths via environment variables:
- `CHROME_BINARY` (default: `/tmp/chrome-linux64/chrome`)
- `CHROMEDRIVER_BINARY` (default: `/usr/local/bin/chromedriver`)

## Usage

### 1. Scrape Articles

```bash
python scraper.py
```

This fetches Reuters articles from Google News RSS feeds (World, Business, Technology, Markets), resolves URLs to actual Reuters article links, and saves them to `reuters_news.csv`.

### 2. Launch Dashboard

```bash
streamlit run app.py
```

Open http://localhost:8501 in your browser.

### Dashboard Features

- **Article Table**: Latest articles with clickable hyperlinks to Reuters
- **Posting Frequency Chart**: Daily or hourly bar chart of article counts
- **Category Breakdown**: Articles per category visualization
- **Filters**: Keyword search, category filter, date range picker
- **In-app Scraping**: Click "Scrape Latest Articles" button to fetch new data

## Architecture

- **scraper.py**: Google News RSS -> Selenium URL resolution -> CSV storage
- **app.py**: Streamlit dashboard reading from CSV
- **reuters_news.csv**: Data storage (UTF-8 BOM, deduplicated by URL)

## Notes

- Reuters blocks direct scraping with DataDome CAPTCHA. This tool uses Google News RSS feeds filtered for `site:reuters.com` as a reliable alternative.
- Access intervals respect rate limits (`time.sleep(1.5)` between requests).
- For personal/research use only. Please respect Reuters' terms of service.
