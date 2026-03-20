#!/usr/bin/env python3
"""
Vault Research Desk — Stock Screener
Scans S&P 500 tickers for technical signals using yfinance.

Usage:
    python3 screener.py                  # Full scan (all ~500 tickers)
    python3 screener.py --sample 50      # Scan 50 random tickers
    python3 screener.py --top 10         # Show top 10 results
    python3 screener.py --sample 30 --top 5
"""

import sys
import os
import argparse
import random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_fetcher import fetch_technicals, fetch_earnings_date, read_portfolio

from db import VaultDB

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance not installed. Run: pip3 install yfinance")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Sector mapping — ticker to GICS sector
# ---------------------------------------------------------------------------
SECTOR_ETF_MAP = {
    "XLK": "Technology", "XLV": "Healthcare", "XLF": "Financials",
    "XLE": "Energy", "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLI": "Industrials", "XLB": "Materials", "XLRE": "Real Estate",
    "XLU": "Utilities", "XLC": "Communication Services",
    "GLD": "Commodities", "SLV": "Commodities", "USO": "Energy",
}

def _get_ticker_sector(ticker):
    """Get sector for a ticker via yfinance info. Returns sector string or None."""
    if ticker in SECTOR_ETF_MAP:
        return SECTOR_ETF_MAP[ticker]
    try:
        t = yf.Ticker(ticker)
        info = t.info
        return info.get("sector", None)
    except Exception:
        return None

def _detect_portfolio_sectors():
    """Read portfolio and identify which sectors are already owned."""
    port_tickers, _, _ = read_portfolio()
    owned_sectors = set()
    for ticker in port_tickers:
        sector = _get_ticker_sector(ticker)
        if sector:
            owned_sectors.add(sector)
    return owned_sectors, port_tickers

# ---------------------------------------------------------------------------
# S&P 500 tickers (as of early 2026)
# ---------------------------------------------------------------------------
SP500_TICKERS = [
    "A", "AAL", "AAPL", "ABBV", "ABNB", "ABT", "ACGL", "ACN", "ADBE", "ADI",
    "ADM", "ADP", "ADSK", "AEE", "AEP", "AES", "AFL", "AIG", "AIZ", "AJG",
    "AKAM", "ALB", "ALGN", "ALK", "ALL", "ALLE", "AMAT", "AMCR", "AMD", "AME",
    "AMGN", "AMP", "AMT", "AMZN", "ANET", "ANSS", "AON", "AOS", "APA", "APD",
    "APH", "APTV", "ARE", "ATO", "ATVI", "AVB", "AVGO", "AVY", "AWK", "AXP",
    "AZO", "BA", "BAC", "BAX", "BBWI", "BBY", "BDX", "BEN", "BF.B", "BG",
    "BIIB", "BIO", "BK", "BKNG", "BKR", "BLDR", "BLK", "BMY", "BR", "BRK.B",
    "BRO", "BSX", "BWA", "BX", "BXP", "C", "CAG", "CAH", "CARR", "CAT",
    "CB", "CBOE", "CBRE", "CCI", "CCL", "CDNS", "CDW", "CE", "CEG", "CF",
    "CFG", "CHD", "CHRW", "CHTR", "CI", "CINF", "CL", "CLX", "CMCSA", "CME",
    "CMG", "CMI", "CMS", "CNC", "CNP", "COF", "COO", "COP", "COR", "COST",
    "CPAY", "CPB", "CPRT", "CPT", "CRL", "CRM", "CSCO", "CSGP", "CSX", "CTAS",
    "CTLT", "CTRA", "CTSH", "CTVA", "CVS", "CVX", "CZR", "D", "DAL", "DAY",
    "DD", "DE", "DECK", "DFS", "DG", "DGX", "DHI", "DHR", "DIS", "DISH",
    "DLR", "DLTR", "DOV", "DOW", "DPZ", "DRI", "DTE", "DUK", "DVA", "DVN",
    "DXCM", "EA", "EBAY", "ECL", "ED", "EFX", "EIX", "EL", "EMN", "EMR",
    "ENPH", "EOG", "EPAM", "EQIX", "EQR", "EQT", "ES", "ESS", "ETN", "ETR",
    "ETSY", "EVRG", "EW", "EXC", "EXPD", "EXPE", "EXR", "F", "FANG", "FAST",
    "FBHS", "FCX", "FDS", "FDX", "FE", "FFIV", "FI", "FICO", "FIS", "FISV",
    "FITB", "FLT", "FMC", "FOX", "FOXA", "FRC", "FRT", "FSLR", "FTNT", "FTV",
    "GD", "GDDY", "GE", "GEHC", "GEN", "GILD", "GIS", "GL", "GLW", "GM",
    "GNRC", "GOOG", "GOOGL", "GPC", "GPN", "GRMN", "GS", "GWW", "HAL", "HAS",
    "HBAN", "HCA", "HCSG", "HD", "HOLX", "HON", "HPE", "HPQ", "HRL", "HSIC",
    "HST", "HSY", "HUBB", "HUM", "HWM", "IBM", "ICE", "IDXX", "IEX", "IFF",
    "ILMN", "INCY", "INTC", "INTU", "INVH", "IP", "IPG", "IQV", "IR", "IRM",
    "ISRG", "IT", "ITW", "IVZ", "J", "JBHT", "JCI", "JKHY", "JNJ", "JNPR",
    "JPM", "K", "KDP", "KEY", "KEYS", "KHC", "KIM", "KLAC", "KMB", "KMI",
    "KMX", "KO", "KR", "KVUE", "L", "LDOS", "LEN", "LH", "LHX", "LIN",
    "LKQ", "LLY", "LMT", "LNT", "LOW", "LRCX", "LULU", "LUV", "LVS", "LW",
    "LYB", "LYV", "MA", "MAA", "MAR", "MAS", "MCD", "MCHP", "MCK", "MCO",
    "MDLZ", "MDT", "MET", "META", "MGM", "MHK", "MKC", "MKTX", "MLM", "MMC",
    "MMM", "MNST", "MO", "MOH", "MOS", "MPC", "MPWR", "MRK", "MRNA", "MRO",
    "MS", "MSCI", "MSFT", "MSI", "MTB", "MTCH", "MTD", "MU", "NCLH", "NDAQ",
    "NDSN", "NEE", "NEM", "NFLX", "NI", "NKE", "NOC", "NOW", "NRG", "NSC",
    "NTAP", "NTRS", "NUE", "NVDA", "NVR", "NWL", "NWS", "NWSA", "NXPI", "O",
    "ODFL", "OGN", "OKE", "OMC", "ON", "ORCL", "ORLY", "OTIS", "OXY", "PARA",
    "PAYC", "PAYX", "PCAR", "PCG", "PEAK", "PEG", "PEP", "PFE", "PFG", "PG",
    "PGR", "PH", "PHM", "PKG", "PLD", "PM", "PNC", "PNR", "PNW", "PODD",
    "POOL", "PPG", "PPL", "PRU", "PSA", "PSX", "PTC", "PVH", "PWR", "PXD",
    "PYPL", "QCOM", "QRVO", "RCL", "RE", "REG", "REGN", "RF", "RHI", "RJF",
    "RL", "RMD", "ROK", "ROL", "ROP", "ROST", "RSG", "RTX", "RVTY", "SBAC",
    "SBNY", "SBUX", "SCHW", "SEE", "SHW", "SIVB", "SJM", "SLB", "SMCI", "SNA",
    "SNPS", "SO", "SPG", "SPGI", "SRE", "STE", "STLD", "STT", "STX", "STZ",
    "SWK", "SWKS", "SYF", "SYK", "SYY", "T", "TAP", "TDG", "TDY", "TECH",
    "TEL", "TER", "TFC", "TFX", "TGT", "TJX", "TMO", "TMUS", "TPR", "TRGP",
    "TRMB", "TROW", "TRV", "TSCO", "TSLA", "TSN", "TT", "TTWO", "TXN", "TXT",
    "TYL", "UAL", "UBER", "UDR", "UHS", "ULTA", "UNH", "UNP", "UPS", "URI",
    "USB", "V", "VICI", "VLO", "VLTO", "VMC", "VRSK", "VRSN", "VRTX", "VTR",
    "VTRS", "VZ", "WAB", "WAT", "WBA", "WBD", "WDC", "WEC", "WELL", "WFC",
    "WHR", "WM", "WMB", "WMT", "WRB", "WRK", "WST", "WTW", "WY", "WYNN",
    "XEL", "XOM", "XRAY", "XYL", "YUM", "ZBH", "ZBRA", "ZION", "ZTS",
]

# ---------------------------------------------------------------------------
# Core ETFs — always scanned alongside S&P 500 sample
# ---------------------------------------------------------------------------
CORE_ETFS = [
    # Broad market
    'VOO', 'SPY', 'VTI', 'SPLG', 'QQQ', 'RSP',
    # International
    'VEA', 'VWO', 'VXUS', 'EFA',
    # Bonds
    'TLT', 'BND', 'AGG', 'SHY', 'BIL', 'TIP',
    # REITs
    'VNQ',
    # Commodities
    'GLD', 'SLV', 'DBC',
    # Sector ETFs
    'XLK', 'XLV', 'XLF', 'XLE', 'XLY', 'XLP', 'XLI', 'XLB', 'XLRE', 'XLU', 'XLC',
]

CORE_ETFS_SET = set(CORE_ETFS)


def fetch_price_and_volume(ticker):
    """Fetch current price and volume data using yfinance 5-day history.

    Returns dict with price, volume, avg_volume_4d, volume_ratio or empty dict on error.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="5d")
        if hist.empty or len(hist) < 2:
            return {}
        current = hist.iloc[-1]
        price = round(float(current["Close"]), 2)
        volume = int(current["Volume"])

        # Average volume of prior 4 days (everything except today)
        prior = hist.iloc[:-1]
        avg_vol = int(prior["Volume"].mean()) if len(prior) > 0 else 0
        vol_ratio = round(volume / avg_vol, 2) if avg_vol > 0 else 0.0

        return {
            "price": price,
            "volume": volume,
            "avg_volume_4d": avg_vol,
            "volume_ratio": vol_ratio,
        }
    except Exception:
        return {}


def scan_ticker(ticker, missing_sectors=None, owned_tickers=None):
    """Run all signal checks for a single ticker.

    Args:
        ticker: Stock ticker symbol
        missing_sectors: Set of sectors not in portfolio (gets +2 boost)
        owned_tickers: List of tickers already owned (skip these)

    Returns a dict with all data and detected signals, or None on failure.
    """
    # Skip tickers already in portfolio
    if owned_tickers and ticker in owned_tickers:
        return None

    tech = fetch_technicals(ticker)
    if not tech:
        return None

    pv = fetch_price_and_volume(ticker)
    if not pv:
        return None

    price = pv["price"]
    volume_ratio = pv["volume_ratio"]

    rsi = tech.get("rsi")
    dma_50 = tech.get("dma_50")
    dma_200 = tech.get("dma_200")
    high_52w = tech.get("high_52w")
    low_52w = tech.get("low_52w")

    signals = []
    score = 0

    # 1. RSI oversold
    if rsi is not None and rsi < 30:
        signals.append("Oversold")
        score += 2

    # 2. RSI overbought — flag for AVOID list, penalize ranking
    if rsi is not None and rsi > 70:
        signals.append("Overbought")  # AUTO-FIX: AVOID VALIDATION — AVOID calls validated at 3/3 accuracy
        score -= 1  # negative: overbought stocks should rank lower, not higher

    # 3. Golden cross
    if dma_50 is not None and dma_200 is not None and price > dma_50 > dma_200:
        spread_pct = abs(dma_50 - dma_200) / dma_200 * 100
        if spread_pct <= 2.0:
            signals.append("Golden Cross")
            score += 3

    # 4. Death cross
    if dma_50 is not None and dma_200 is not None and price < dma_50 < dma_200:
        spread_pct = abs(dma_50 - dma_200) / dma_200 * 100
        if spread_pct <= 2.0:
            signals.append("Death Cross")
            score -= 3

    # 5. Near 52-week low (within 5%)
    if low_52w is not None and low_52w > 0:
        pct_from_low = (price - low_52w) / low_52w * 100
        if pct_from_low <= 5.0:
            signals.append("Near 52wk Low")
            score += 2

    # 6. Near 52-week high (within 5%)
    if high_52w is not None and high_52w > 0:
        pct_from_high = (high_52w - price) / high_52w * 100
        if pct_from_high <= 5.0:
            signals.append("Near 52wk High")
            score += 1

    # 7. Unusual volume
    if volume_ratio >= 2.0:
        signals.append("Unusual Volume")
        score += 1

    # 8. Earnings within 7 days — WARNING, not a buy signal
    earnings_date = fetch_earnings_date(ticker)
    earnings_soon = False
    if earnings_date:
        try:
            ed = datetime.strptime(earnings_date, "%Y-%m-%d").date()
            today = datetime.now().date()
            days_to_earnings = (ed - today).days
            if 0 <= days_to_earnings <= 3:
                signals.append("⚠ Earnings <3d")
                earnings_soon = True
                score -= 1  # Penalize — system rule says don't buy 1-3 days before earnings
            elif 3 < days_to_earnings <= 7:
                signals.append("Earnings Soon")
                earnings_soon = True
        except (ValueError, TypeError):
            pass

    # 9. Sector gap bonus — boost stocks in sectors portfolio doesn't own
    sector = None
    if missing_sectors:
        sector = _get_ticker_sector(ticker)
        if sector and sector in missing_sectors:
            signals.append(f"Fills Gap: {sector}")
            score += 2

    if not signals:
        return None

    return {
        "ticker": ticker,
        "price": price,
        "rsi": rsi,
        "dma_50": dma_50,
        "dma_200": dma_200,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "volume": pv["volume"],
        "avg_volume_4d": pv["avg_volume_4d"],
        "volume_ratio": volume_ratio,
        "earnings_date": earnings_date,
        "earnings_soon": earnings_soon,
        "sector": sector,
        "signals": signals,
        "score": score,
        "is_etf": ticker in CORE_ETFS_SET,
    }


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _fmt_pct(price, ref):
    """Return formatted % diff between price and reference."""
    if ref is None or ref == 0:
        return "   -   "
    pct = (price - ref) / ref * 100
    return f"{pct:+.1f}%"


def _earnings_col(result):
    ed = result.get("earnings_date") or "-"
    if result.get("earnings_soon"):
        return f"{ed} !"
    return ed


def print_section(title, results, columns="default"):
    """Print a formatted section of results."""
    if not results:
        return
    print(f"\n{title}")
    if columns == "default":
        header = f"  {'Ticker':<8} {'Price':>9} {'RSI':>6} {'vs50DMA':>9} {'vs200DMA':>9} {'Earnings':>14}"
        print(header)
        print(f"  {'─' * 60}")
        for r in results:
            vs50 = _fmt_pct(r["price"], r.get("dma_50"))
            vs200 = _fmt_pct(r["price"], r.get("dma_200"))
            rsi_str = f"{r.get('rsi'):.1f}" if r.get("rsi") is not None else "-"
            print(f"  {r['ticker']:<8} {r['price']:>9.2f} {rsi_str:>6} {vs50:>9} {vs200:>9} {_earnings_col(r):>14}")
    elif columns == "volume":
        header = f"  {'Ticker':<8} {'Price':>9} {'Volume':>12} {'AvgVol(4d)':>12} {'Ratio':>7}"
        print(header)
        print(f"  {'─' * 52}")
        for r in results:
            print(f"  {r['ticker']:<8} {r['price']:>9.2f} {r['volume']:>12,} {r.get('avg_volume_4d', 0):>12,} {r['volume_ratio']:>6.1f}x")


def print_results(all_results, top_n):
    """Print the full screener output."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    total_signals = len(all_results)

    print(f"\n{'═' * 55}")
    print(f"  SCREENER RESULTS ({timestamp})")
    print(f"{'═' * 55}")
    print(f"  Scanned: {scan_count} | Signals found: {total_signals}")

    # Separate ETF results
    etf_results = [r for r in all_results if r.get("is_etf")]
    stock_results = [r for r in all_results if not r.get("is_etf")]

    # Core ETF signals section
    if etf_results:
        print(f"\nCORE ETF SIGNALS:")
        header = f"  {'Ticker':<8} {'Price':>9} {'RSI':>6} {'vs50DMA':>9} {'vs200DMA':>9} {'Signals'}"
        print(header)
        print(f"  {'─' * 70}")
        for r in sorted(etf_results, key=lambda x: x["score"], reverse=True):
            vs50 = _fmt_pct(r["price"], r.get("dma_50"))
            vs200 = _fmt_pct(r["price"], r.get("dma_200"))
            rsi_str = f"{r.get('rsi'):.1f}" if r.get("rsi") is not None else "-"
            sig_str = ", ".join(r["signals"])
            print(f"  {r['ticker']:<8} {r['price']:>9.2f} {rsi_str:>6} {vs50:>9} {vs200:>9}  {sig_str}")

    # Categorize (stocks only, ETFs already shown above)
    oversold = [r for r in stock_results if "Oversold" in r["signals"]]
    golden = [r for r in stock_results if "Golden Cross" in r["signals"]]
    near_low = [r for r in stock_results if "Near 52wk Low" in r["signals"]]
    overbought = [r for r in stock_results if "Overbought" in r["signals"]]
    unusual_vol = [r for r in stock_results if "Unusual Volume" in r["signals"]]

    print_section("OVERSOLD (RSI < 30):", oversold)
    print_section("GOLDEN CROSS:", golden)
    print_section("NEAR 52-WEEK LOW (within 5%):", near_low)
    print_section("OVERBOUGHT (RSI > 70) — AVOID candidates:", overbought)

    # Volume section with special columns
    if unusual_vol:
        print(f"\nUNUSUAL VOLUME (>2x avg):")
        header = f"  {'Ticker':<8} {'Price':>9} {'Volume':>12} {'AvgVol(4d)':>12} {'Ratio':>7}"
        print(header)
        print(f"  {'─' * 52}")
        for r in unusual_vol:
            avg_v = r.get("avg_volume_4d", 0)
            print(f"  {r['ticker']:<8} {r['price']:>9.2f} {r['volume']:>12,} {avg_v:>12,} {r['volume_ratio']:>6.1f}x")

    # Top candidates by composite score
    ranked = sorted(all_results, key=lambda x: x["score"], reverse=True)[:top_n]
    if ranked:
        # Load watchlist and active theses for overlap detection
        watchlist_tickers = set()
        thesis_tickers = set()
        try:
            with VaultDB() as db:
                for w in db.get_active_watchlist():
                    watchlist_tickers.add(w['ticker'])
                for t in db.get_active_theses():
                    thesis_tickers.add(t['ticker'])
        except Exception:
            pass

        print(f"\nTOP CANDIDATES (by composite score):")
        print(f"  {'Rank':<6} {'Ticker':<8} {'Score':>6} {'Signals'}")
        print(f"  {'─' * 55}")
        for i, r in enumerate(ranked, 1):
            sig_str = ", ".join(r["signals"])
            # Flag overlap with existing watchlist or theses
            tags = []
            if r.get('is_etf'):
                tags.append("ETF")
            if r['ticker'] in watchlist_tickers:
                tags.append("ON WATCHLIST")
            if r['ticker'] in thesis_tickers:
                tags.append("HAS THESIS")
            tag_str = f"  [{', '.join(tags)}]" if tags else ""
            print(f"  {i:<6} {r['ticker']:<8} {r['score']:>+5}  {sig_str}{tag_str}")

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

scan_count = 0  # module-level so print_results can reference it


def main():
    global scan_count

    parser = argparse.ArgumentParser(description="Vault Research Desk — S&P 500 Stock Screener")
    parser.add_argument("--sample", type=int, default=0,
                        help="Scan N random tickers instead of all 500")
    parser.add_argument("--top", type=int, default=20,
                        help="Show top N results (default 20)")
    parser.add_argument("--no-sectors", action="store_true",
                        help="Disable sector gap detection")
    args = parser.parse_args()

    tickers = SP500_TICKERS[:]
    if args.sample > 0:
        tickers = random.sample(tickers, min(args.sample, len(tickers)))

    # Always include CORE_ETFS (deduplicated against the stock list)
    stock_set = set(tickers)
    etfs_to_add = [etf for etf in CORE_ETFS if etf not in stock_set]
    tickers = tickers + etfs_to_add

    scan_count = len(tickers)
    total = len(tickers)

    # Detect portfolio sector gaps
    missing_sectors = None
    owned_tickers = None
    all_sectors = {
        "Technology", "Healthcare", "Financials", "Energy",
        "Consumer Discretionary", "Consumer Staples", "Industrials",
        "Materials", "Real Estate", "Utilities", "Communication Services",
    }
    if not args.no_sectors:
        try:
            owned_sectors, owned_tickers = _detect_portfolio_sectors()
            missing_sectors = all_sectors - owned_sectors
            if owned_sectors:
                print(f"Portfolio sectors: {', '.join(sorted(owned_sectors))}")
                if missing_sectors:
                    print(f"Missing sectors:  {', '.join(sorted(missing_sectors))} (+2 score boost)")
                print()
        except Exception:
            pass

    print(f"Vault Research Desk — Screener")
    print(f"Scanning {total} tickers...")
    print()

    all_results = []

    for i, ticker in enumerate(tickers, 1):
        if i % 50 == 0 or i == total:
            print(f"Scanning... {i}/{total}")

        result = scan_ticker(ticker, missing_sectors, owned_tickers)
        if result:
            all_results.append(result)

    print_results(all_results, args.top)

    # Save results to DB
    try:
        with VaultDB() as db:
            db_results = []
            for r in all_results:
                db_results.append({
                    'ticker': r['ticker'],
                    'price': r.get('price'),
                    'rsi': r.get('rsi'),
                    'dma_50': r.get('dma_50'),
                    'dma_200': r.get('dma_200'),
                    'high_52w': r.get('high_52w'),
                    'low_52w': r.get('low_52w'),
                    'volume_ratio': r.get('volume_ratio'),
                    'earnings_date': r.get('earnings_date'),
                    'signals': '; '.join(r.get('signals', [])),
                    'score': r.get('score'),
                    'sector': r.get('sector'),
                })
            db.save_screener_run(db_results)
    except Exception as e:
        print(f"Warning: could not save screener results to DB: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
