from __future__ import annotations

from app.data.market_data import fetch_trailing_return


US_SECTOR_SYMBOLS: dict[str, list[str]] = {
    "기술": ["XLK", "SOXX", "AAPL", "MSFT"],
    "반도체": ["SOXX", "NVDA", "AVGO"],
    "금융": ["XLF"],
    "에너지": ["XLE"],
    "헬스케어": ["XLV"],
    "산업재": ["XLI"],
    "소비재": ["XLY", "XLP", "AMZN", "TSLA"],
    "커뮤니케이션": ["XLC", "META", "GOOGL"],
    "부동산": ["XLRE"],
}

KR_SECTOR_SYMBOLS: dict[str, list[str]] = {
    "반도체": ["005930.KS", "000660.KS"],
    "자동차": ["005380.KS", "000270.KS"],
    "인터넷": ["035420.KS", "035720.KS"],
    "2차전지": ["051910.KS", "006400.KS", "373220.KS"],
    "바이오": ["068270.KS", "207940.KS"],
    "방산": ["012450.KS", "079550.KS"],
    "전력기기": ["010120.KS", "267260.KS"],
}


def get_sector_snapshot(market: str, top_n: int = 2) -> dict[str, list[str]]:
    sector_map = KR_SECTOR_SYMBOLS if market.upper() == "KR" else US_SECTOR_SYMBOLS
    scores: list[tuple[str, float]] = []
    for sector_name, symbols in sector_map.items():
        returns = []
        for symbol in symbols:
            try:
                returns.append(fetch_trailing_return(symbol, lookback_days=5))
            except Exception:
                continue
        if not returns:
            continue
        scores.append((sector_name, sum(returns) / len(returns)))

    scores.sort(key=lambda item: item[1], reverse=True)
    strong = [f"{name} ({score:+.1f}%)" for name, score in scores[:top_n]]
    weak = [f"{name} ({score:+.1f}%)" for name, score in scores[-top_n:]][::-1]
    return {
        "strong": strong,
        "weak": weak,
    }


def get_sector_strength_details(market: str) -> list[dict]:
    sector_map = KR_SECTOR_SYMBOLS if market.upper() == "KR" else US_SECTOR_SYMBOLS
    scores: list[tuple[str, float]] = []
    for sector_name, symbols in sector_map.items():
        returns = []
        for symbol in symbols:
            try:
                returns.append(fetch_trailing_return(symbol, lookback_days=20))
            except Exception:
                continue
        if not returns:
            continue
        scores.append((sector_name, sum(returns) / len(returns)))

    if not scores:
        return []

    benchmark = sum(score for _, score in scores) / len(scores)
    details = []
    for name, score in sorted(scores, key=lambda item: item[1], reverse=True):
        if score >= benchmark + 2:
            label = "strong"
        elif score <= benchmark - 2:
            label = "weak"
        else:
            label = "mixed"
        details.append(
            {
                "sector_name": name,
                "sector_relative_strength": round(score - benchmark, 2),
                "sector_trend_label": label,
            }
        )
    return details


def infer_sector_name(market: str, ticker: str) -> str:
    sector_map = KR_SECTOR_SYMBOLS if market.upper() == "KR" else US_SECTOR_SYMBOLS
    normalized = ticker.upper()
    for sector_name, symbols in sector_map.items():
        if normalized in {symbol.upper() for symbol in symbols}:
            return sector_name
    return ""
