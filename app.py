"""
Reuters News Dashboard
======================
Streamlit-based dashboard for visualizing collected Reuters news articles.
Run with: streamlit run app.py
"""

import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st
from deep_translator import GoogleTranslator

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CSV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reuters_news.csv")

st.set_page_config(
    page_title="Reuters News Dashboard",
    page_icon="📰",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_data() -> pd.DataFrame:
    """Load article data from CSV."""
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=["title", "url", "published_at", "category", "scraped_at"])

    df = pd.read_csv(CSV_FILE, encoding="utf-8-sig")

    # Parse dates
    if "published_at" in df.columns:
        df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    if "scraped_at" in df.columns:
        df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce")

    # Sort by published_at descending (newest first)
    if "published_at" in df.columns:
        df = df.sort_values("published_at", ascending=False, na_position="last")

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Sidebar – Filters
# ---------------------------------------------------------------------------

def render_sidebar(df: pd.DataFrame) -> pd.DataFrame:
    """Render sidebar filters and return filtered DataFrame."""
    st.sidebar.header("Filters")

    # Keyword filter
    keyword = st.sidebar.text_input("Keyword search (title)", "")

    # Category filter
    if "category" in df.columns and not df["category"].dropna().empty:
        categories = ["All"] + sorted(df["category"].dropna().unique().tolist())
        selected_cat = st.sidebar.selectbox("Category", categories)
    else:
        selected_cat = "All"

    # Date range filter
    if "published_at" in df.columns and df["published_at"].notna().any():
        min_date = df["published_at"].min().date()
        max_date = df["published_at"].max().date()
        date_range = st.sidebar.date_input(
            "Date range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
    else:
        date_range = None

    # Time granularity for chart
    granularity = st.sidebar.radio(
        "Chart granularity",
        ["Daily", "Hourly"],
        index=0,
    )

    # Number of articles to display
    n_display = st.sidebar.slider("Articles to display", 10, 50, 20)

    # Apply filters
    filtered = df.copy()

    if keyword:
        mask = filtered["title"].str.contains(keyword, case=False, na=False)
        filtered = filtered[mask]

    if selected_cat != "All":
        filtered = filtered[filtered["category"] == selected_cat]

    if date_range and len(date_range) == 2 and "published_at" in filtered.columns:
        start, end = date_range
        start_dt = pd.Timestamp(start)
        end_dt = pd.Timestamp(end) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        mask = filtered["published_at"].between(start_dt, end_dt)
        filtered = filtered[mask | filtered["published_at"].isna()]

    return filtered, granularity, n_display


# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------

def _translate_titles(titles: list[str]) -> list[str]:
    """Translate a list of English titles to Japanese using Google Translate."""
    translator = GoogleTranslator(source="en", target="ja")
    translated: list[str] = []
    for title in titles:
        if not title or not title.strip():
            translated.append(title)
            continue
        try:
            result = translator.translate(title)
            translated.append(result if result else title)
        except Exception:
            translated.append(title)
    return translated


def make_clickable(row) -> str:
    """Create an HTML hyperlink for the article title with Japanese translation."""
    title = row["title"] if pd.notna(row["title"]) else "No title"
    title_ja = row.get("title_ja", "") if pd.notna(row.get("title_ja", "")) else ""
    url = row["url"] if pd.notna(row["url"]) else "#"
    if title_ja and title_ja != title:
        return (
            f'<a href="{url}" target="_blank">{title_ja}</a>'
            f'<br><span style="color: #888; font-size: 0.85em;">{title}</span>'
        )
    return f'<a href="{url}" target="_blank">{title}</a>'


def render_article_table(df: pd.DataFrame, n_display: int):
    """Display the latest articles as a table with clickable links."""
    st.subheader(f"Latest Articles (top {n_display})")

    if df.empty:
        st.info("No articles found matching the current filters.")
        return

    display_df = df.head(n_display).copy()

    # Translate titles to Japanese
    titles_to_translate = display_df["title"].fillna("").tolist()
    with st.spinner("タイトルを翻訳中..."):
        display_df["title_ja"] = _translate_titles(titles_to_translate)

    # Create clickable title column
    display_df["Article"] = display_df.apply(make_clickable, axis=1)

    # Format dates for display
    if "published_at" in display_df.columns:
        display_df["Published"] = display_df["published_at"].dt.strftime("%Y-%m-%d %H:%M")
    else:
        display_df["Published"] = ""

    if "category" in display_df.columns:
        display_df["Category"] = display_df["category"]
    else:
        display_df["Category"] = ""

    # Select and rename columns for display
    show_cols = ["Article", "Published", "Category"]
    show_df = display_df[show_cols].reset_index(drop=True)
    show_df.index = show_df.index + 1  # 1-based index

    st.write(
        show_df.to_html(escape=False, index=True),
        unsafe_allow_html=True,
    )


def render_frequency_chart(df: pd.DataFrame, granularity: str):
    """Display article posting frequency over time."""
    st.subheader("Article Posting Frequency")

    if df.empty or "published_at" not in df.columns or df["published_at"].isna().all():
        st.info("No date information available for charting.")
        return

    chart_df = df.dropna(subset=["published_at"]).copy()

    if granularity == "Daily":
        chart_df["period"] = chart_df["published_at"].dt.date
        xlabel = "Date"
    else:
        chart_df["period"] = chart_df["published_at"].dt.floor("h")
        xlabel = "Hour"

    freq = chart_df.groupby("period").size().reset_index(name="Article Count")
    freq = freq.rename(columns={"period": xlabel})
    freq = freq.sort_values(xlabel)

    # Use Streamlit's built-in bar chart
    st.bar_chart(
        freq.set_index(xlabel)["Article Count"],
        use_container_width=True,
    )

    # Also show category breakdown if multiple categories exist
    if "category" in chart_df.columns and chart_df["category"].nunique() > 1:
        st.subheader("Articles by Category")
        cat_counts = chart_df["category"].value_counts().reset_index()
        cat_counts.columns = ["Category", "Count"]
        st.bar_chart(cat_counts.set_index("Category")["Count"], use_container_width=True)


def render_stats(df: pd.DataFrame):
    """Display summary statistics."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Articles", len(df))
    with col2:
        n_categories = df["category"].nunique() if "category" in df.columns else 0
        st.metric("Categories", n_categories)
    with col3:
        if "published_at" in df.columns and df["published_at"].notna().any():
            latest = df["published_at"].max()
            st.metric("Latest Article", latest.strftime("%Y-%m-%d %H:%M"))
        else:
            st.metric("Latest Article", "N/A")
    with col4:
        if "published_at" in df.columns and df["published_at"].notna().any():
            oldest = df["published_at"].min()
            st.metric("Oldest Article", oldest.strftime("%Y-%m-%d %H:%M"))
        else:
            st.metric("Oldest Article", "N/A")


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

def main():
    st.title("Reuters News Dashboard")
    st.markdown("Real-time monitoring of Reuters news article trends.")

    # Scraper button
    col_refresh, col_info = st.columns([1, 3])
    with col_refresh:
        if st.button("Scrape Latest Articles", type="primary"):
            with st.spinner("Scraping Reuters... (this may take a minute)"):
                try:
                    from scraper import scrape_reuters
                    results = scrape_reuters()
                    st.success(f"Scraped {len(results)} articles!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Scraping failed: {e}")

    with col_info:
        st.caption(
            "Click the button to fetch the latest articles from Reuters. "
            "Data is saved to reuters_news.csv and deduplicated automatically."
        )

    st.divider()

    # Load data
    df = load_data()

    if df.empty:
        st.warning(
            "No data found. Click **Scrape Latest Articles** above to collect data, "
            "or run `python scraper.py` from the terminal."
        )
        return

    # Sidebar filters
    filtered_df, granularity, n_display = render_sidebar(df)

    # Summary stats
    render_stats(filtered_df)

    st.divider()

    # Article table
    render_article_table(filtered_df, n_display)

    st.divider()

    # Frequency chart
    render_frequency_chart(filtered_df, granularity)

    # Footer
    st.divider()
    st.caption(
        "Data source: Reuters (reuters.com). "
        "This tool is for personal/research use only. "
        "Please respect Reuters' terms of service."
    )


if __name__ == "__main__":
    main()
