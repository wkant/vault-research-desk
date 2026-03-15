#!/usr/bin/env python3
"""
Vault Research Desk — News Fetcher (Finnhub + Marketaux)

Two sources, one cache:
  - Finnhub:   High volume of headlines, broad coverage
  - Marketaux: Per-entity sentiment scores (-1 to +1)

All articles cached to vault.db news table.

Usage:
    python3 tools/news.py GOOGL              # company news (both APIs)
    python3 tools/news.py GOOGL XLE NVDA     # multiple tickers
    python3 tools/news.py --market           # general market news
    python3 tools/news.py --portfolio        # news for all holdings
    python3 tools/news.py --days 3           # look back 3 days (default 7)
    python3 tools/news.py --no-cache         # force fresh fetch
    python3 tools/news.py --sentiment GOOGL  # show sentiment summary
"""

import json
import os
import sys
import argparse
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import quote

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from db import VaultDB

# ── Config ─────────────────────────────────────────────────────────

def _load_api_keys():
    """Load API keys from api_keys.conf (repo), falling back to env vars."""
    keys = {}
    conf = os.path.join(SCRIPT_DIR, "api_keys.conf")
    if os.path.exists(conf):
        with open(conf) as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    keys[k.strip()] = v.strip()
    return keys

_keys = _load_api_keys()
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY") or _keys.get("FINNHUB_API_KEY", "")
MARKETAUX_API_KEY = os.environ.get("MARKETAUX_API_KEY") or _keys.get("MARKETAUX_API_KEY", "")

FINNHUB_BASE = "https://finnhub.io/api/v1"
MARKETAUX_BASE = "https://api.marketaux.com/v1"


# ── HTTP helper ────────────────────────────────────────────────────

def _fetch_json(url, timeout=15):
    """Fetch JSON from a URL."""
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "VaultResearchDesk/2.0",
    })
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (URLError, HTTPError) as e:
        print(f"  API error: {e}")
        return None
    except json.JSONDecodeError:
        print("  Invalid JSON response")
        return None


# ── Finnhub API ────────────────────────────────────────────────────

def _finnhub_company(ticker, days_back=7):
    """Fetch company news from Finnhub."""
    if not FINNHUB_API_KEY:
        return []

    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = (f"{FINNHUB_BASE}/company-news"
           f"?symbol={ticker}&from={from_date}&to={today}&token={FINNHUB_API_KEY}")

    data = _fetch_json(url)
    if not data or not isinstance(data, list):
        return []

    articles = []
    for item in data:
        published = datetime.fromtimestamp(item.get("datetime", 0)).isoformat()
        articles.append({
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published": published,
            "category": "company",
            "sentiment": None,
        })
    return articles


def _finnhub_market():
    """Fetch general market news from Finnhub."""
    if not FINNHUB_API_KEY:
        return []

    url = f"{FINNHUB_BASE}/news?category=general&token={FINNHUB_API_KEY}"

    data = _fetch_json(url)
    if not data or not isinstance(data, list):
        return []

    articles = []
    for item in data:
        published = datetime.fromtimestamp(item.get("datetime", 0)).isoformat()
        articles.append({
            "headline": item.get("headline", ""),
            "summary": item.get("summary", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published": published,
            "category": "general",
            "sentiment": None,
        })
    return articles


# ── Marketaux API ──────────────────────────────────────────────────

def _marketaux_company(ticker, days_back=7):
    """Fetch company news with sentiment from Marketaux."""
    if not MARKETAUX_API_KEY:
        return []

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = (f"{MARKETAUX_BASE}/news/all"
           f"?symbols={ticker}"
           f"&filter_entities=true"
           f"&language=en"
           f"&published_after={from_date}"
           f"&limit=50"
           f"&api_token={MARKETAUX_API_KEY}")

    data = _fetch_json(url)
    if not data or "data" not in data:
        return []

    articles = []
    for item in data["data"]:
        # Extract sentiment for this specific ticker
        sentiment = None
        entities = item.get("entities", [])
        for ent in entities:
            if ent.get("symbol", "").upper() == ticker.upper():
                sentiment = ent.get("sentiment_score")
                break
        # Fallback: use first entity sentiment if ticker not matched
        if sentiment is None and entities:
            sentiment = entities[0].get("sentiment_score")

        published = item.get("published_at", "")
        # Normalize to ISO format
        if published and "T" in published:
            published = published.replace(".000000Z", "").replace("Z", "")

        articles.append({
            "headline": item.get("title", ""),
            "summary": item.get("description", "") or item.get("snippet", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published": published,
            "category": "company",
            "sentiment": sentiment,
        })
    return articles


def _marketaux_market(days_back=3):
    """Fetch general market news with sentiment from Marketaux."""
    if not MARKETAUX_API_KEY:
        return []

    from_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = (f"{MARKETAUX_BASE}/news/all"
           f"?language=en"
           f"&published_after={from_date}"
           f"&limit=50"
           f"&api_token={MARKETAUX_API_KEY}")

    data = _fetch_json(url)
    if not data or "data" not in data:
        return []

    articles = []
    for item in data["data"]:
        # Use first entity sentiment if available
        sentiment = None
        entities = item.get("entities", [])
        if entities:
            sentiment = entities[0].get("sentiment_score")

        published = item.get("published_at", "")
        if published and "T" in published:
            published = published.replace(".000000Z", "").replace("Z", "")

        articles.append({
            "headline": item.get("title", ""),
            "summary": item.get("description", "") or item.get("snippet", ""),
            "source": item.get("source", ""),
            "url": item.get("url", ""),
            "published": published,
            "category": "general",
            "sentiment": sentiment,
        })
    return articles


# ── Merged fetchers ────────────────────────────────────────────────

def _merge_articles(finnhub_articles, marketaux_articles):
    """Merge articles from both sources, dedup by headline similarity."""
    seen = set()
    merged = []

    # Marketaux first (has sentiment scores)
    for a in marketaux_articles:
        key = a["headline"][:60].lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(a)

    # Then Finnhub (fills gaps)
    for a in finnhub_articles:
        key = a["headline"][:60].lower().strip()
        if key and key not in seen:
            seen.add(key)
            merged.append(a)

    return merged


def fetch_company_news(ticker, days_back=7):
    """Fetch from both APIs and merge."""
    fh = _finnhub_company(ticker, days_back)
    mx = _marketaux_company(ticker, days_back)
    return _merge_articles(fh, mx)


def fetch_market_news(days_back=3):
    """Fetch market news from both APIs and merge."""
    fh = _finnhub_market()
    mx = _marketaux_market(days_back)
    return _merge_articles(fh, mx)


# ── Cache-aware fetchers ───────────────────────────────────────────

def get_news(ticker, days_back=7, max_age_minutes=60, force=False):
    """Get news for a ticker: cache first, then APIs."""
    with VaultDB() as db:
        if not force:
            cached = db.get_cached_news(ticker, max_age_minutes=max_age_minutes)
            if cached:
                return cached

        # Fetch fresh from both APIs
        if ticker == "MARKET":
            articles = fetch_market_news(days_back=days_back)
        else:
            articles = fetch_company_news(ticker, days_back=days_back)

        if articles:
            db.cache_news(ticker, articles)

        # Return from DB (normalized format)
        return db.get_cached_news(ticker, max_age_minutes=9999, limit=50) or []


def get_portfolio_news(days_back=7, force=False):
    """Fetch news for all portfolio holdings."""
    with VaultDB() as db:
        holdings = db.get_holdings()

    tickers = [h["ticker"] for h in holdings] if holdings else []
    results = {}
    for t in tickers:
        results[t] = get_news(t, days_back=days_back, force=force)
    return results


# ── Sentiment analysis ─────────────────────────────────────────────

def sentiment_summary(ticker, days=7):
    """Compute sentiment summary from cached articles."""
    with VaultDB() as db:
        articles = db.get_recent_news(ticker=ticker, days=days, limit=100)

    if not articles:
        return None

    scores = []
    for a in articles:
        s = a["sentiment"]
        if s is not None:
            scores.append(s)

    if not scores:
        return {"ticker": ticker, "articles": len(articles), "scored": 0,
                "avg": None, "label": "NO DATA"}

    avg = sum(scores) / len(scores)
    if avg >= 0.3:
        label = "BULLISH"
    elif avg >= 0.1:
        label = "SLIGHTLY BULLISH"
    elif avg > -0.1:
        label = "NEUTRAL"
    elif avg > -0.3:
        label = "SLIGHTLY BEARISH"
    else:
        label = "BEARISH"

    return {
        "ticker": ticker,
        "articles": len(articles),
        "scored": len(scores),
        "avg": round(avg, 3),
        "positive": len([s for s in scores if s > 0.1]),
        "negative": len([s for s in scores if s < -0.1]),
        "neutral": len([s for s in scores if -0.1 <= s <= 0.1]),
        "label": label,
    }


# ── Display ────────────────────────────────────────────────────────

def _sentiment_badge(score):
    """Format sentiment score as a compact badge."""
    if score is None:
        return ""
    if score >= 0.3:
        return f" [+{score:.2f}]"
    elif score <= -0.3:
        return f" [{score:.2f}]"
    elif score > 0:
        return f" [+{score:.2f}]"
    elif score < 0:
        return f" [{score:.2f}]"
    return " [0.00]"


def print_news(ticker, articles):
    """Print formatted news output."""
    print(f"\n{'─' * 55}")
    count = len(articles) if articles else 0
    scored = sum(1 for a in (articles or [])
                 if (a["sentiment"] if hasattr(a, 'keys') else a.get("sentiment")) is not None)
    source_tag = f"{count} articles"
    if scored:
        source_tag += f", {scored} with sentiment"
    print(f"  NEWS: {ticker} ({source_tag})")
    print(f"{'─' * 55}")

    if not articles:
        print("  No articles found.")
        return

    for a in articles[:15]:
        # Handle both dict and sqlite3.Row
        if hasattr(a, 'keys'):
            published = a['published']
            source = a['source']
            headline = a['headline']
            summary = a['summary'] or ''
            sentiment = a['sentiment']
        else:
            published = a.get('published', '')
            source = a.get('source', '')
            headline = a.get('headline', '')
            summary = a.get('summary', '')
            sentiment = a.get('sentiment')

        # Format date
        try:
            dt = datetime.fromisoformat(published)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            date_str = str(published)[:16]

        badge = _sentiment_badge(sentiment)
        print(f"\n  {date_str} | {source}{badge}")
        print(f"    {headline[:100]}")
        if summary:
            print(f"    {summary[:120]}")


def print_sentiment_summary(summary):
    """Print sentiment summary for a ticker."""
    if not summary:
        print("  No sentiment data.")
        return
    print(f"\n{'─' * 40}")
    print(f"  SENTIMENT: {summary['ticker']}")
    print(f"{'─' * 40}")
    print(f"  Articles: {summary['articles']} total, {summary['scored']} with scores")
    if summary['avg'] is not None:
        print(f"  Average:  {summary['avg']:+.3f}  →  {summary['label']}")
        print(f"  Positive: {summary.get('positive', 0)} | "
              f"Neutral: {summary.get('neutral', 0)} | "
              f"Negative: {summary.get('negative', 0)}")
    else:
        print(f"  No scored articles available.")


# ── CLI ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fetch news from Finnhub + Marketaux")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--market", action="store_true",
                        help="General market news")
    parser.add_argument("--portfolio", action="store_true",
                        help="News for all holdings")
    parser.add_argument("--days", type=int, default=7,
                        help="Days to look back (default 7)")
    parser.add_argument("--no-cache", action="store_true",
                        help="Force fresh fetch")
    parser.add_argument("--sentiment", nargs="*", metavar="TICKER",
                        help="Show sentiment summary for tickers")
    args = parser.parse_args()

    if not FINNHUB_API_KEY and not MARKETAUX_API_KEY:
        print("ERROR: Set at least one API key:")
        print("  export FINNHUB_API_KEY=your_key")
        print("  export MARKETAUX_API_KEY=your_key")
        sys.exit(1)

    has_action = (args.tickers or args.market or args.portfolio
                  or args.sentiment is not None)
    if not has_action:
        parser.print_help()
        sys.exit(1)

    # Sentiment mode
    if args.sentiment is not None:
        tickers = args.sentiment if args.sentiment else args.tickers
        for t in tickers:
            t = t.upper()
            # Ensure fresh data
            get_news(t, days_back=args.days, force=args.no_cache)
            s = sentiment_summary(t, days=args.days)
            print_sentiment_summary(s)
        print()
        return

    if args.market:
        articles = get_news("MARKET", days_back=args.days, force=args.no_cache)
        print_news("MARKET", articles)

    if args.portfolio:
        results = get_portfolio_news(days_back=args.days, force=args.no_cache)
        for ticker, articles in results.items():
            print_news(ticker, articles)

    for ticker in args.tickers:
        ticker = ticker.upper()
        articles = get_news(ticker, days_back=args.days, force=args.no_cache)
        print_news(ticker, articles)

    print()


if __name__ == "__main__":
    main()
