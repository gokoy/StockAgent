from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
import re

from app.agents.macro_agent import analyze_market_regime
from app.config import load_config
from app.data.market_data import fetch_latest_close_change
from app.data.news_data import fetch_market_event_news, fetch_market_news
from app.data.sector_data import get_sector_snapshot, get_sector_strength_details
from app.models.schemas import MacroSnapshot, MarketBriefing, MarketHeadline, MarketIndexSnapshot

try:
    from pykrx import stock as krx_stock
except Exception:  # pragma: no cover - optional dependency
    krx_stock = None


MARKET_LABELS = {
    "KR": "한국 시장",
    "US": "미국 시장",
}

INDEX_SYMBOLS = {
    "KR": [("KOSPI", "^KS11"), ("KOSDAQ", "^KQ11")],
    "US": [("S&P 500", "^GSPC"), ("Nasdaq", "^IXIC"), ("Dow", "^DJI"), ("Russell 2000", "^RUT")],
}

MACRO_SYMBOLS = {
    "KR": [("원/달러", "KRW=X"), ("미국 10년물", "^TNX"), ("WTI", "CL=F")],
    "US": [("달러인덱스", "DX-Y.NYB"), ("미국 10년물", "^TNX"), ("WTI", "CL=F")],
}


def build_market_briefing(market: str, run_at: datetime, max_news_age_hours: int) -> MarketBriefing:
    normalized = market.upper()
    title = MARKET_LABELS.get(normalized, normalized)
    index_snapshots = _build_index_snapshots(normalized)
    macro_snapshots = _build_macro_snapshots(normalized)
    sector_snapshot = get_sector_snapshot(normalized)
    news_items = fetch_market_news(normalized, max_age_hours=max_news_age_hours, limit=4)
    event_items = fetch_market_event_news(normalized, max_age_hours=max_news_age_hours, limit=8)
    market_briefing = MarketBriefing(
        market=normalized,
        title=title,
        market_summary="",
        index_snapshots=index_snapshots,
        macro_snapshots=macro_snapshots,
        flow_summary=_build_flow_summary(normalized, run_at),
        strong_sectors=sector_snapshot["strong"],
        weak_sectors=sector_snapshot["weak"],
        key_events=_build_key_events(event_items),
        key_headlines=[_to_market_headline(item, normalized) for item in news_items],
        sector_strength_details=get_sector_strength_details(normalized),
    )
    regime = analyze_market_regime(market_briefing)
    return market_briefing.model_copy(update={"market_summary": regime.market_summary or _compose_market_summary(market_briefing)})


def _build_index_snapshots(market: str) -> list[MarketIndexSnapshot]:
    snapshots: list[MarketIndexSnapshot] = []
    for label, symbol in INDEX_SYMBOLS.get(market, []):
        try:
            close, change_pct = fetch_latest_close_change(symbol)
            snapshots.append(
                MarketIndexSnapshot(
                    label=label,
                    symbol=symbol,
                    close=round(close, 2),
                    change_pct=round(change_pct, 2),
                )
            )
        except Exception:
            continue
    return snapshots


def _build_macro_snapshots(market: str) -> list[MacroSnapshot]:
    snapshots: list[MacroSnapshot] = []
    for label, symbol in MACRO_SYMBOLS.get(market, []):
        try:
            value, change_pct = fetch_latest_close_change(symbol)
            snapshots.append(
                MacroSnapshot(
                    label=label,
                    symbol=symbol,
                    value=round(value, 2),
                    change_pct=round(change_pct, 2),
                )
            )
        except Exception:
            continue
    return snapshots


def _build_flow_summary(market: str, run_at: datetime) -> list[str]:
    if market != "KR":
        return _build_us_flow_proxy()
    return _build_kr_flow_summary(run_at)


def _build_us_flow_proxy() -> list[str]:
    messages = []
    try:
        qqq_close, qqq_change = fetch_latest_close_change("QQQ")
        spy_close, spy_change = fetch_latest_close_change("SPY")
        messages.append(f"QQQ {qqq_change:+.2f}%, SPY {spy_change:+.2f}%로 대형 성장주와 시장 전체 흐름을 같이 확인한다.")
        if qqq_change > spy_change:
            messages.append("기술주 선호가 상대적으로 강해 성장주 중심 위험선호가 유지되는 흐름이다.")
        else:
            messages.append("광범위 지수 대비 기술주 상대강도는 강하지 않아 추격보다 선별 접근이 낫다.")
        _ = qqq_close  # suppress unused semantics
    except Exception:
        messages.append("미국 시장은 지수와 금리 방향을 우선 확인하고 개별 종목은 실적 일정 영향이 큰 구간으로 본다.")
    return messages


def _build_kr_flow_summary(run_at: datetime) -> list[str]:
    snapshot_messages = _load_kr_flow_snapshot(load_config().kr_flow_path)
    if snapshot_messages:
        return snapshot_messages

    if krx_stock is None:
        return ["한국 시장 수급은 현재 optional 데이터다. kr_flow_snapshot.json이 비어 있고 pykrx도 사용할 수 없어 외국인/기관/개인 수급 집계를 제공하지 않는다."]

    end = run_at.strftime("%Y%m%d")
    start = (run_at - timedelta(days=7)).strftime("%Y%m%d")
    summaries: list[str] = []
    for market in ("KOSPI", "KOSDAQ"):
        try:
            fn = getattr(krx_stock, "get_market_trading_value_by_investor", None)
            if fn is None:
                raise AttributeError("get_market_trading_value_by_investor not available")
            frame = fn(start, end, market=market)
            if frame.empty:
                continue
            latest = frame.iloc[-1]
            foreign = float(latest.get("외국인합계", 0.0))
            inst = float(latest.get("기관합계", 0.0))
            personal = float(latest.get("개인", 0.0))
            summaries.append(
                f"{market}: 외국인 { _signed_korean_amount(foreign) }, 기관 { _signed_korean_amount(inst) }, 개인 { _signed_korean_amount(personal) }"
            )
        except Exception:
            continue
    return summaries or ["한국 시장 수급은 현재 best-effort optional 데이터다. kr_flow_snapshot.json이 비어 있고 pykrx/KRX 응답 공백 또는 네트워크 문제로 집계하지 못했다."]


def _load_kr_flow_snapshot(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    lines: list[str] = []
    for market in ("KOSPI", "KOSDAQ"):
        item = payload.get(market)
        if not isinstance(item, dict):
            continue
        as_of = str(item.get("as_of", "")).strip()
        foreign = str(item.get("foreign", "")).strip()
        institution = str(item.get("institution", "")).strip()
        individual = str(item.get("individual", "")).strip()
        if not any((foreign, institution, individual)):
            continue
        suffix = f" ({as_of})" if as_of else ""
        lines.append(f"{market}{suffix}: 외국인 {foreign or '-'}, 기관 {institution or '-'}, 개인 {individual or '-'}")
    return lines


def _to_market_headline(item, market: str) -> MarketHeadline:
    return MarketHeadline(
        headline=item.headline,
        summary=item.summary,
        why_it_matters=_why_it_matters(item.headline, item.summary, market),
        source=item.source,
        published_at=item.published_at,
    )


def _build_key_events(items) -> list[str]:
    events = []
    seen: set[str] = set()
    for item in items:
        label = _normalize_event_label(item.headline.strip(), item.published_at)
        if not label or label in seen:
            continue
        seen.add(label)
        events.append(label)
    return events


def _normalize_event_label(headline: str, published_at: datetime) -> str:
    text = re.sub(r"\s+", " ", headline).strip(" -")
    text = re.sub(r"\s+\|\s+.+$", "", text)
    text = re.sub(r"\s+-\s+[^-]+$", "", text)
    lowered = text.lower()
    korean_date = published_at.astimezone().strftime("%m월 %d일")
    english_date = published_at.strftime("%b %d")

    replacements = (
        ("cpi", "미국 CPI 관련 이벤트"),
        ("ppi", "미국 PPI 관련 이벤트"),
        ("fomc", "FOMC 관련 이벤트"),
        ("payroll", "미국 고용지표 관련 이벤트"),
        ("options expiration", "미국 옵션 만기 관련 이벤트"),
        ("treasury", "미국 국채금리 관련 이벤트"),
        ("earnings", "실적 발표 관련 이벤트"),
        ("실적", "실적 발표 관련 이벤트"),
        ("환율", "환율 관련 이벤트"),
        ("한국은행", "한국은행 관련 이벤트"),
        ("정부 정책", "정부 정책 관련 이벤트"),
    )
    for pattern, label in replacements:
        if pattern in lowered:
            date_label = korean_date if re.search(r"[가-힣]", text) else english_date
            return f"{date_label} {label}"
    date_label = korean_date if re.search(r"[가-힣]", text) else english_date
    return f"{date_label} {text}"


def _why_it_matters(headline: str, summary: str, market: str) -> str:
    text = f"{headline} {summary}".lower()
    if "cpi" in text or "inflation" in text:
        return "물가 지표는 금리 기대를 바꾸어 성장주와 위험자산 선호에 직접 영향을 줄 수 있다."
    if "fomc" in text or "fed" in text or "treasury" in text:
        return "통화정책과 금리 방향은 밸류에이션과 시장 위험선호를 동시에 흔드는 변수다."
    if "earnings" in text or "실적" in text:
        return "실적은 개별 종목뿐 아니라 섹터 전반 심리에도 영향을 줄 수 있다."
    if "환율" in text or "currency" in text or "dollar" in text:
        return "환율 방향은 외국인 수급과 수입 원가 기대에 바로 연결된다."
    if market == "KR":
        return "국내 증시는 반도체, 환율, 정책 뉴스에 민감해 시장 전체 심리에 파급될 수 있다."
    return "미국 증시는 금리, 대형 기술주, 경기 지표 뉴스에 따라 단기 방향성이 크게 달라질 수 있다."


def _compose_market_summary(market_briefing: MarketBriefing) -> str:
    positive = [item.label for item in market_briefing.index_snapshots if item.change_pct > 0]
    negative = [item.label for item in market_briefing.index_snapshots if item.change_pct < 0]
    if positive and not negative:
        tone = "주요 지수가 전반적으로 강세다."
    elif negative and not positive:
        tone = "주요 지수가 전반적으로 약세다."
    else:
        tone = "지수 방향이 혼조라 종목 선별이 더 중요하다."
    sector_line = ""
    if market_briefing.strong_sectors:
        sector_line = f" 강한 섹터는 {', '.join(market_briefing.strong_sectors[:2])}다."
    return f"{tone}{sector_line}"


def _signed_korean_amount(value: float) -> str:
    unit = "억"
    amount = value / 100_000_000
    return f"{amount:+,.0f}{unit}"
