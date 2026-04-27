from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from io import StringIO
import json
import os
from pathlib import Path
from typing import Literal
import warnings

import pandas as pd
import requests

from app.web.market_sources import KR_SECTOR_SYMBOLS, fetch_symbol_history


SeriesKind = Literal["risk_on", "risk_off", "neutral"]
ROOT_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT_DIR / "data" / "web" / "dashboard_snapshot.json"
MACRO_HISTORY_PATH = ROOT_DIR / "data" / "history" / "macro_history.json"
SECTOR_HISTORY_PATH = ROOT_DIR / "data" / "history" / "sector_history.json"
MACRO_HISTORY_YEARS = 5
SECTOR_HISTORY_YEARS = 5


@dataclass(frozen=True)
class IndicatorSpec:
    id: str
    name: str
    group: str
    source: Literal["yahoo", "fred", "ratio"]
    symbol: str = ""
    numerator: str = ""
    denominator: str = ""
    unit: str = ""
    kind: SeriesKind = "neutral"
    fred_transform: Literal["level", "yoy_pct"] = "level"
    description: str = ""
    market_impact: str = ""


@dataclass(frozen=True)
class SectorSpec:
    id: str
    name: str
    market: Literal["US", "KR"]
    benchmark: str
    symbols: tuple[str, ...]
    description: str
    market_impact: str


MACRO_SPECS: tuple[IndicatorSpec, ...] = (
    IndicatorSpec(
        id="sp500",
        name="S&P 500",
        group="주식 위험선호",
        source="yahoo",
        symbol="^GSPC",
        unit="pt",
        kind="risk_on",
        description="미국 대형주 전반의 방향성이다. 글로벌 위험자산의 기준선으로 본다.",
        market_impact="상승은 공격적 포지션에 유리하고, 하락은 현금/방어 섹터 비중을 높여야 한다는 신호가 된다.",
    ),
    IndicatorSpec(
        id="nasdaq100",
        name="Nasdaq 100",
        group="주식 위험선호",
        source="yahoo",
        symbol="^NDX",
        unit="pt",
        kind="risk_on",
        description="성장주와 빅테크 선호를 보여준다. 금리와 유동성 변화에 민감하다.",
        market_impact="나스닥이 시장을 이끌면 성장주/AI/반도체 쪽으로 자금이 붙는 경우가 많다.",
    ),
    IndicatorSpec(
        id="russell_spy",
        name="소형주 / 대형주",
        group="주식 위험선호",
        source="ratio",
        numerator="IWM",
        denominator="SPY",
        unit="ratio",
        kind="risk_on",
        description="소형주가 대형주보다 강한지 보는 상대강도다.",
        market_impact="상승하면 시장 참여 폭이 넓어지는 신호이고, 하락하면 대형 우량주 쏠림 또는 방어적 장세로 해석한다.",
    ),
    IndicatorSpec(
        id="vix",
        name="VIX 변동성",
        group="공포/헤지",
        source="yahoo",
        symbol="^VIX",
        unit="pt",
        kind="risk_off",
        description="S&P 500 옵션시장이 반영하는 단기 변동성 기대치다.",
        market_impact="급등하면 주식 비중 확대보다 리스크 관리가 우선이고, 하락 안정화는 공격 재개 조건이 된다.",
    ),
    IndicatorSpec(
        id="dgs10",
        name="미국 10년 금리",
        group="금리/할인율",
        source="fred",
        symbol="DGS10",
        unit="%",
        kind="risk_off",
        description="주식 가치평가의 할인율 기준이다. 특히 성장주 멀티플에 큰 영향을 준다.",
        market_impact="금리 상승은 성장주와 장기채에 부담이고, 금리 하락은 기술주/성장주 반등에 우호적이다.",
    ),
    IndicatorSpec(
        id="dgs2",
        name="미국 2년 금리",
        group="금리/할인율",
        source="fred",
        symbol="DGS2",
        unit="%",
        kind="risk_off",
        description="연준 정책금리 기대를 가장 민감하게 반영하는 구간이다.",
        market_impact="2년 금리 상승은 긴축 우려를 키우고, 하락은 정책 부담 완화로 해석한다.",
    ),
    IndicatorSpec(
        id="curve_10y2y",
        name="10년-2년 금리차",
        group="금리/할인율",
        source="fred",
        symbol="T10Y2Y",
        unit="%",
        kind="neutral",
        description="장단기 금리차다. 경기 기대와 침체 우려를 함께 읽는다.",
        market_impact="역전이 깊어지면 경기 둔화 위험을 경계하고, 정상화는 경기 회복 기대와도 연결된다.",
    ),
    IndicatorSpec(
        id="hy_spread",
        name="하이일드 스프레드",
        group="신용/유동성",
        source="fred",
        symbol="BAMLH0A0HYM2",
        unit="%",
        kind="risk_off",
        description="투기등급 회사채가 국채 대비 요구하는 추가 금리다.",
        market_impact="스프레드 확대는 신용 스트레스와 위험회피를 뜻하고, 축소는 위험자산에 우호적이다.",
    ),
    IndicatorSpec(
        id="hyg_lqd",
        name="하이일드 / 우량채",
        group="신용/유동성",
        source="ratio",
        numerator="HYG",
        denominator="LQD",
        unit="ratio",
        kind="risk_on",
        description="위험한 회사채가 우량 회사채보다 강한지 보는 시장 내부 신호다.",
        market_impact="상승하면 신용시장이 위험을 받아들이고 있다는 뜻이라 주식에도 우호적이다.",
    ),
    IndicatorSpec(
        id="dxy",
        name="달러 인덱스",
        group="환율/글로벌 자금",
        source="yahoo",
        symbol="DX-Y.NYB",
        unit="pt",
        kind="risk_off",
        description="달러 강세 여부를 보여준다. 글로벌 유동성과 신흥국 자금 흐름에 중요하다.",
        market_impact="달러 급등은 해외 위험자산과 원화자산에 부담이고, 달러 약세는 위험선호에 우호적이다.",
    ),
    IndicatorSpec(
        id="usdkrw",
        name="달러/원",
        group="환율/글로벌 자금",
        source="yahoo",
        symbol="USDKRW=X",
        unit="KRW",
        kind="risk_off",
        description="원화 약세/강세를 직접 보여준다. 한국 주식 외국인 수급과 연결된다.",
        market_impact="달러/원 상승은 외국인 매도 압력과 수입물가 부담으로 이어질 수 있다.",
    ),
    IndicatorSpec(
        id="wti",
        name="WTI 원유",
        group="원자재/인플레이션",
        source="yahoo",
        symbol="CL=F",
        unit="$",
        kind="neutral",
        description="에너지 가격과 인플레이션 압력을 같이 보여준다.",
        market_impact="완만한 상승은 경기 수요를 뜻할 수 있지만, 급등은 물가와 마진 부담으로 시장에 부정적이다.",
    ),
    IndicatorSpec(
        id="gold",
        name="금",
        group="원자재/인플레이션",
        source="yahoo",
        symbol="GC=F",
        unit="$",
        kind="neutral",
        description="실질금리, 달러, 안전자산 수요를 함께 반영한다.",
        market_impact="금이 강하면 인플레이션 헤지나 안전자산 선호가 커졌는지 확인해야 한다.",
    ),
    IndicatorSpec(
        id="copper",
        name="구리",
        group="원자재/경기",
        source="yahoo",
        symbol="HG=F",
        unit="$",
        kind="risk_on",
        description="제조업과 인프라 수요에 민감해 경기 민감 지표로 자주 본다.",
        market_impact="구리 강세는 경기민감주와 산업재에 우호적이고, 약세는 수요 둔화 신호가 될 수 있다.",
    ),
    IndicatorSpec(
        id="kospi",
        name="KOSPI",
        group="한국시장",
        source="yahoo",
        symbol="^KS11",
        unit="pt",
        kind="risk_on",
        description="한국 대형주 시장의 기준 지수다.",
        market_impact="코스피가 강하면 반도체/자동차/금융 등 한국 주도 섹터 추적이 필요하다.",
    ),
    IndicatorSpec(
        id="kosdaq",
        name="KOSDAQ",
        group="한국시장",
        source="yahoo",
        symbol="^KQ11",
        unit="pt",
        kind="risk_on",
        description="한국 성장주와 중소형주 위험선호를 보여준다.",
        market_impact="코스닥이 코스피보다 강하면 바이오, 2차전지, 테마 성장주로 수급이 이동했는지 본다.",
    ),
    IndicatorSpec(
        id="btc",
        name="Bitcoin",
        group="고베타/유동성",
        source="yahoo",
        symbol="BTC-USD",
        unit="$",
        kind="risk_on",
        description="고베타 유동성 자산의 대표 신호다.",
        market_impact="강세는 투기적 위험선호 회복 신호일 수 있고, 급락은 고베타 자산 축소 압력으로 본다.",
    ),
    IndicatorSpec(
        id="fedfunds",
        name="연방기금금리",
        group="정책/거시경제",
        source="fred",
        symbol="FEDFUNDS",
        unit="%",
        kind="risk_off",
        description="연준 정책금리의 실제 레벨이다.",
        market_impact="높은 정책금리는 현금의 기회비용을 높이고, 금리 인하 국면은 위험자산에 유동성 기대를 만든다.",
    ),
    IndicatorSpec(
        id="cpi_yoy",
        name="미국 CPI YoY",
        group="정책/거시경제",
        source="fred",
        symbol="CPIAUCSL",
        unit="%",
        kind="risk_off",
        fred_transform="yoy_pct",
        description="미국 소비자물가의 전년 대비 상승률이다.",
        market_impact="높게 유지되면 금리 인하 기대를 낮추고, 둔화되면 밸류에이션 부담을 줄인다.",
    ),
    IndicatorSpec(
        id="unemployment",
        name="미국 실업률",
        group="정책/거시경제",
        source="fred",
        symbol="UNRATE",
        unit="%",
        kind="neutral",
        description="미국 고용시장의 둔화 여부를 보여준다.",
        market_impact="완만한 상승은 긴축 완화 기대를 만들 수 있지만, 급등은 경기침체 리스크로 해석한다.",
    ),
)


US_SECTOR_SPECS: tuple[SectorSpec, ...] = (
    SectorSpec("us-tech", "기술", "US", "SPY", ("XLK",), "소프트웨어, 하드웨어, 플랫폼 대형주의 흐름이다.", "시장보다 강하면 성장주 위험선호가 살아있다고 본다."),
    SectorSpec("us-semi", "반도체", "US", "SPY", ("SOXX",), "AI, 데이터센터, 메모리/장비 사이클을 압축해서 본다.", "강세는 시장의 공격성이 높다는 뜻이고, 약세 전환은 고베타 축소 신호다."),
    SectorSpec("us-financials", "금융", "US", "SPY", ("XLF",), "은행, 보험, 브로커리지의 흐름이다.", "금리곡선과 신용 스트레스에 민감해 경기 신뢰도를 함께 보여준다."),
    SectorSpec("us-energy", "에너지", "US", "SPY", ("XLE",), "원유/가스 가격과 에너지주 수급을 반영한다.", "강하면 인플레이션 재상승 가능성과 가치주 선호를 같이 점검한다."),
    SectorSpec("us-healthcare", "헬스케어", "US", "SPY", ("XLV",), "제약, 바이오, 의료장비의 방어적 성장 흐름이다.", "하락장에서도 강하면 방어적 자금 이동으로 해석한다."),
    SectorSpec("us-industrials", "산업재", "US", "SPY", ("XLI",), "운송, 기계, 방산, 인프라 관련주 흐름이다.", "강세는 경기 확장 기대와 설비투자 기대를 반영할 수 있다."),
    SectorSpec("us-discretionary", "경기소비재", "US", "SPY", ("XLY",), "자동차, 이커머스, 레저 등 소비 경기 민감주다.", "강세는 소비 여력과 위험선호 개선 신호다."),
    SectorSpec("us-staples", "필수소비재", "US", "SPY", ("XLP",), "식품, 생활용품 등 방어 섹터다.", "시장보다 강하면 방어적 로테이션일 가능성을 본다."),
    SectorSpec("us-communication", "커뮤니케이션", "US", "SPY", ("XLC",), "광고, 미디어, 플랫폼 기업 흐름이다.", "기술주와 함께 강하면 성장주 랠리의 폭을 확인하는 데 유용하다."),
    SectorSpec("us-utilities", "유틸리티", "US", "SPY", ("XLU",), "전력/가스 등 배당 방어 섹터다.", "강세는 방어 자금 또는 금리 하락 수혜를 의미할 수 있다."),
)


KR_SECTOR_SPECS: tuple[SectorSpec, ...] = tuple(
    SectorSpec(
        id=f"kr-{name}",
        name=name,
        market="KR",
        benchmark="^KS11",
        symbols=tuple(symbols),
        description=f"한국 {name} 대표 종목 묶음의 평균 흐름이다.",
        market_impact="코스피보다 강하면 해당 업종으로 국내 수급이 몰리는지 확인할 우선순위가 올라간다.",
    )
    for name, symbols in KR_SECTOR_SYMBOLS.items()
)


def get_macro_dashboard() -> dict[str, object]:
    snapshot = load_dashboard_snapshot()
    if snapshot is not None:
        macro = snapshot.get("macro")
        if isinstance(macro, dict):
            return macro
    return _get_macro_dashboard_live()


def get_sector_dashboard(market: Literal["US", "KR"] = "US") -> dict[str, object]:
    snapshot = load_dashboard_snapshot()
    if snapshot is not None:
        sectors = snapshot.get("sectors")
        if isinstance(sectors, dict):
            dashboard = sectors.get(market)
            if isinstance(dashboard, dict):
                return dashboard
    return _get_sector_dashboard_live(market)


def build_dashboard_snapshot() -> dict[str, object]:
    macro_history = build_macro_history()
    sector_history = build_sector_history()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "macro": _get_macro_dashboard_live(macro_history=macro_history),
        "sectors": {
            "US": _get_sector_dashboard_live("US", sector_history=sector_history),
            "KR": _get_sector_dashboard_live("KR", sector_history=sector_history),
        },
    }


def refresh_dashboard_snapshot(
    path: Path = SNAPSHOT_PATH,
    macro_history_path: Path = MACRO_HISTORY_PATH,
    sector_history_path: Path = SECTOR_HISTORY_PATH,
) -> dict[str, object]:
    snapshot = build_dashboard_snapshot()
    _write_json_atomic(path, snapshot)
    _write_json_atomic(macro_history_path, build_macro_history())
    _write_json_atomic(sector_history_path, build_sector_history())
    return snapshot


def load_dashboard_snapshot(path: Path = SNAPSHOT_PATH) -> dict[str, object] | None:
    if not path.exists():
        if _live_fallback_enabled():
            return None
        raise FileNotFoundError(f"Dashboard snapshot not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid dashboard snapshot: {path}")
    return payload


def _get_macro_dashboard_live(macro_history: dict[str, object] | None = None) -> dict[str, object]:
    history_by_id = _history_series_by_id(macro_history or build_macro_history(), "indicators")
    indicators = [_build_indicator(spec) for spec in MACRO_SPECS]
    valid = [_attach_macro_history_stats(item, history_by_id.get(str(item["id"]), [])) for item in indicators if item["points"]]
    groups: dict[str, list[dict[str, object]]] = {}
    for item in valid:
        groups.setdefault(str(item["group"]), []).append(item)
    decision = _build_macro_decision(valid)
    ai_summary = _build_macro_ai_summary(decision, valid)

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "decision": decision,
        "ai_summary": ai_summary,
        "groups": groups,
        "failed_count": len(indicators) - len(valid),
    }


def _get_sector_dashboard_live(
    market: Literal["US", "KR"] = "US",
    sector_history: dict[str, object] | None = None,
) -> dict[str, object]:
    specs = US_SECTOR_SPECS if market == "US" else KR_SECTOR_SPECS
    history_by_id = _history_series_by_id(sector_history or build_sector_history(), "sectors")
    sectors = [_build_sector(spec, history_by_id.get(spec.id, [])) for spec in specs]
    valid = [item for item in sectors if item["points"]]
    leaders = [item for item in valid if float(item["relative_strength"]) > 0]
    leaders.sort(key=lambda item: float(item["relative_strength"]), reverse=True)
    valid.sort(key=lambda item: float(item["relative_strength"]), reverse=True)
    laggards = sorted(valid, key=lambda item: float(item["relative_strength"]))
    return {
        "market": market,
        "benchmark": "S&P 500" if market == "US" else "KOSPI",
        "as_of": datetime.now(UTC).isoformat(),
        "leaders": leaders[:5],
        "laggards": laggards[:5],
        "flow_summary": _sector_flow_summary(valid, leaders, laggards),
        "sectors": valid,
    }


def _live_fallback_enabled() -> bool:
    raw = os.getenv("STOCKAGENT_LIVE_FALLBACK", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_macro_history(years: int = MACRO_HISTORY_YEARS) -> dict[str, object]:
    indicators = []
    for spec in MACRO_SPECS:
        try:
            series = _fetch_indicator_series(spec, period=f"{years}y")
            points = _series_to_points(series)
            indicators.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "group": spec.group,
                    "kind": spec.kind,
                    "unit": spec.unit,
                    "points": points,
                }
            )
        except Exception as exc:
            indicators.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "group": spec.group,
                    "kind": spec.kind,
                    "unit": spec.unit,
                    "error": str(exc),
                    "points": [],
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "years": years,
        "indicators": indicators,
    }


def build_sector_history(years: int = SECTOR_HISTORY_YEARS) -> dict[str, object]:
    sectors = []
    for spec in (*US_SECTOR_SPECS, *KR_SECTOR_SPECS):
        try:
            sector = _fetch_sector_index(spec.symbols, period=f"{years}y")
            benchmark = _normalize_series(_fetch_yahoo_close(spec.benchmark, period=f"{years}y"))
            frame = pd.concat([sector.rename("sector"), benchmark.rename("benchmark")], axis=1).dropna()
            sectors.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "market": spec.market,
                    "benchmark": spec.benchmark,
                    "points": [
                        {
                            "date": str(index.date()),
                            "sector": round(float(row["sector"]), 2),
                            "benchmark": round(float(row["benchmark"]), 2),
                        }
                        for index, row in frame.iterrows()
                    ],
                }
            )
        except Exception as exc:
            sectors.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "market": spec.market,
                    "benchmark": spec.benchmark,
                    "error": str(exc),
                    "points": [],
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "years": years,
        "sectors": sectors,
    }


def _history_series_by_id(history: dict[str, object], key: str) -> dict[str, list[dict[str, object]]]:
    entries = history.get(key)
    if not isinstance(entries, list):
        return {}
    result: dict[str, list[dict[str, object]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        points = entry.get("points")
        if isinstance(entry_id, str) and isinstance(points, list):
            result[entry_id] = [point for point in points if isinstance(point, dict)]
    return result


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def _build_indicator(spec: IndicatorSpec) -> dict[str, object]:
    try:
        series = _fetch_indicator_series(spec)
        points = _series_to_points(series.tail(260))
        latest = float(series.iloc[-1])
        previous = float(series.iloc[-2]) if len(series) >= 2 else latest
        latest_date = str(series.index[-1].date())
        previous_date = str(series.index[-2].date()) if len(series) >= 2 else latest_date
        change_abs = latest - previous
        change_pct = ((latest / previous) - 1.0) * 100 if previous else 0.0
        signal = _classify_signal(spec.kind, change_pct, change_abs)
        return {
            "id": spec.id,
            "name": spec.name,
            "group": spec.group,
            "kind": spec.kind,
            "unit": spec.unit,
            "value": _round_value(latest),
            "change_abs": _round_value(change_abs),
            "change_pct": round(change_pct, 2),
            "latest_date": latest_date,
            "previous_date": previous_date,
            "data_frequency": _data_frequency_label(spec),
            "signal": signal,
            "description": spec.description,
            "market_impact": spec.market_impact,
            "points": points,
        }
    except Exception as exc:
        return {
            "id": spec.id,
            "name": spec.name,
            "group": spec.group,
            "kind": spec.kind,
            "unit": spec.unit,
            "value": None,
            "change_abs": None,
            "change_pct": None,
            "latest_date": "",
            "previous_date": "",
            "data_frequency": _data_frequency_label(spec),
            "signal": f"데이터 실패: {exc}",
            "description": spec.description,
            "market_impact": spec.market_impact,
            "points": [],
        }


def _attach_macro_history_stats(item: dict[str, object], history_points: list[dict[str, object]]) -> dict[str, object]:
    enriched = dict(item)
    values = [float(point["value"]) for point in history_points if _is_number(point.get("value"))]
    current = item.get("value")
    if not values or not _is_number(current):
        enriched["history_stats"] = _empty_history_stats()
        return enriched
    percentile = _percentile_rank(values, float(current))
    enriched["history_stats"] = {
        "lookback_years": MACRO_HISTORY_YEARS,
        "percentile": round(percentile, 1),
        "position_label": _history_position_label(percentile),
        "zone": _history_zone(str(item.get("kind", "neutral")), percentile),
        "min": _round_value(min(values)),
        "max": _round_value(max(values)),
        "observations": len(values),
    }
    return enriched


def _build_macro_decision(indicators: list[dict[str, object]]) -> dict[str, object]:
    weights = {
        "sp500": 9,
        "nasdaq100": 8,
        "russell_spy": 6,
        "vix": 9,
        "dgs10": 5,
        "dgs2": 5,
        "curve_10y2y": 4,
        "hy_spread": 10,
        "hyg_lqd": 8,
        "dxy": 6,
        "usdkrw": 5,
        "wti": 2,
        "gold": 2,
        "copper": 4,
        "kospi": 4,
        "kosdaq": 4,
        "btc": 3,
        "fedfunds": 3,
        "cpi_yoy": 4,
        "unemployment": 3,
    }
    score = 50.0
    positive: list[tuple[float, str]] = []
    negative: list[tuple[float, str]] = []

    for item in indicators:
        item_id = str(item["id"])
        weight = weights.get(item_id, 3)
        contribution = _macro_contribution(item)
        contribution += _history_contribution(item)
        points = contribution * weight
        score += points
        note = _decision_note(item)
        if contribution > 0:
            positive.append((points, note))
        elif contribution < 0:
            negative.append((points, note))

    final_score = max(0, min(100, round(score)))
    regime_label, action_title, posture, regime_description = _decision_labels(final_score, len(negative))
    positive_sorted = sorted(positive, key=lambda item: item[0], reverse=True)
    negative_sorted = sorted(negative, key=lambda item: item[0])
    risk_flags = [note for _, note in negative_sorted[:4]]
    supportive_signals = [note for _, note in positive_sorted[:4]]
    confirm_conditions = _confirm_conditions(final_score, risk_flags, supportive_signals)
    dates = sorted({str(item["latest_date"]) for item in indicators if item.get("latest_date")})

    return {
        "score": final_score,
        "regime_label": regime_label,
        "action_title": action_title,
        "posture": posture,
        "regime_description": regime_description,
        "risk_flags": risk_flags,
        "supportive_signals": supportive_signals,
        "score_up_drivers": _score_driver_items(positive_sorted[:4]),
        "score_down_drivers": _score_driver_items(negative_sorted[:4]),
        "confirm_conditions": confirm_conditions,
        "freshness": {
            "latest": dates[-1] if dates else "",
            "oldest": dates[0] if dates else "",
        },
    }


def _build_macro_ai_summary(decision: dict[str, object], indicators: list[dict[str, object]]) -> dict[str, object]:
    fallback = _fallback_macro_summary(decision)
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return fallback

    try:
        from openai import OpenAI

        model = os.getenv("OPENAI_MODEL_MACRO_SUMMARY", "gpt-4.1-mini").strip() or "gpt-4.1-mini"
        client = OpenAI(api_key=api_key)
        prompt = _macro_summary_prompt(decision, indicators)
        response = client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise Korean market dashboard summaries for individual investors. "
                        "Do not give guaranteed returns or direct buy/sell orders. "
                        "Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        parsed = json.loads(content)
        return _normalize_ai_summary(parsed, fallback, source=f"openai:{model}")
    except Exception as exc:
        fallback["source"] = f"fallback:{type(exc).__name__}"
        return fallback


def _score_driver_items(items: list[tuple[float, str]]) -> list[dict[str, object]]:
    return [{"points": round(points, 1), "note": note} for points, note in items]


def _macro_summary_prompt(decision: dict[str, object], indicators: list[dict[str, object]]) -> str:
    compact_indicators = [
        {
            "name": item["name"],
            "group": item["group"],
            "signal": item["signal"],
            "change_pct": item["change_pct"],
            "history_stats": item.get("history_stats"),
            "latest_date": item["latest_date"],
        }
        for item in indicators
    ]
    payload = {
        "decision": decision,
        "indicators": compact_indicators,
        "required_json_schema": {
            "headline": "한 문장 제목",
            "summary": "2문장 이내 최종 정리",
            "stance": "오늘의 대응 방향 한 문장",
            "watch_points": ["확인할 지점 2~3개"],
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _normalize_ai_summary(parsed: dict[str, object], fallback: dict[str, object], source: str) -> dict[str, object]:
    headline = _clean_summary_text(parsed.get("headline"), fallback["headline"], max_len=42)
    summary = _clean_summary_text(parsed.get("summary"), fallback["summary"], max_len=180)
    stance = _clean_summary_text(parsed.get("stance"), fallback["stance"], max_len=110)
    watch_points_raw = parsed.get("watch_points")
    watch_points: list[str] = []
    if isinstance(watch_points_raw, list):
        for item in watch_points_raw:
            if isinstance(item, str) and item.strip():
                watch_points.append(item.strip()[:90])
    if not watch_points:
        watch_points = list(fallback["watch_points"])
    return {
        "headline": headline,
        "summary": summary,
        "stance": stance,
        "watch_points": watch_points[:3],
        "source": source,
    }


def _clean_summary_text(value: object, fallback: object, max_len: int) -> str:
    if not isinstance(value, str) or not value.strip():
        return str(fallback)
    return value.strip().replace("\n", " ")[:max_len]


def _fallback_macro_summary(decision: dict[str, object]) -> dict[str, object]:
    risks = decision.get("risk_flags") or []
    supports = decision.get("supportive_signals") or []
    risk_text = str(risks[0]) if isinstance(risks, list) and risks else "뚜렷한 방어 신호"
    support_text = str(supports[0]) if isinstance(supports, list) and supports else "뚜렷한 우호 신호"
    return {
        "headline": str(decision["action_title"]),
        "summary": f"우호 지표: {support_text}. 부담 지표: {risk_text}. 전체 시장 추격보다 강한 섹터 중심으로 좁게 보는 편이 낫습니다.",
        "stance": str(decision["posture"]),
        "watch_points": list(decision.get("confirm_conditions") or [])[:3],
        "source": "fallback",
    }


def _macro_contribution(item: dict[str, object]) -> float:
    signal = str(item.get("signal", ""))
    item_id = str(item.get("id", ""))
    change_pct = float(item.get("change_pct") or 0.0)
    change_abs = float(item.get("change_abs") or 0.0)

    if signal in {"매수 우세", "매수 부담 감소", "강함", "부담 줄어듦", "살 때 유리", "부담 완화", "공격 우위", "공격 여건 개선"}:
        return 1.0
    if signal in {"매도 우세", "매수 부담 증가", "약함", "부담 커짐", "조심", "방어 필요"}:
        return -1.0
    if item_id == "curve_10y2y":
        return 0.6 if change_abs > 0 else -0.6 if change_abs < 0 else 0.0
    if item_id == "unemployment":
        if abs(change_abs) < 0.05:
            return 0.0
        return -0.6 if change_abs > 0 else 0.4
    if item_id == "wti":
        if abs(change_pct) < 1.0:
            return 0.0
        return -0.4 if change_pct > 0 else 0.2
    if item_id == "gold":
        if abs(change_pct) < 0.8:
            return 0.0
        return -0.2 if change_pct > 0 else 0.1
    return 0.0


def _history_contribution(item: dict[str, object]) -> float:
    stats = item.get("history_stats")
    if not isinstance(stats, dict):
        return 0.0
    percentile = stats.get("percentile")
    if not _is_number(percentile):
        return 0.0
    kind = str(item.get("kind", "neutral"))
    value = float(percentile)
    if kind == "risk_on":
        if value >= 80:
            return 0.35
        if value <= 20:
            return -0.35
    if kind == "risk_off":
        if value >= 80:
            return -0.35
        if value <= 20:
            return 0.25
    return 0.0


def _decision_note(item: dict[str, object]) -> str:
    change_pct = float(item.get("change_pct") or 0.0)
    stats = item.get("history_stats")
    if isinstance(stats, dict) and _is_number(stats.get("percentile")):
        return f"{item['name']} {change_pct:+.2f}% · {_history_position_label(float(stats['percentile']))}"
    return f"{item['name']} {change_pct:+.2f}%"


def _decision_labels(score: int, risk_count: int) -> tuple[str, str, str, str]:
    if score >= 72 and risk_count <= 3:
        return (
            "비중 늘릴 구간",
            "비중 늘리기",
            "주식 비중 확대가 가능하지만, 시장보다 강한 섹터 중심으로 좁게 접근합니다.",
            "위험자산을 사도 되는 조건이 비교적 많은 상태입니다.",
        )
    if score >= 58:
        return (
            "좋은 종목만 매수 구간",
            "좋은 종목만 매수",
            "전체 시장 추격보다 상대강도 상위 섹터와 주도주만 선별합니다.",
            "시장 전체가 모두 좋은 것은 아니지만 일부 강한 자산에는 돈이 몰리는 상태입니다.",
        )
    if score >= 45:
        return (
            "기다릴 구간",
            "확인 후 진입",
            "방향성이 충분히 강하지 않습니다. 신규 비중 확대보다 확인 후 진입이 낫습니다.",
            "공격과 방어 신호가 섞여 있어 결론을 서두르기 어려운 상태입니다.",
        )
    if score >= 32:
        return (
            "비중 줄일 구간",
            "리스크 관리",
            "위험 신호가 우세합니다. 현금 비중과 손절 기준을 먼저 점검합니다.",
            "불리한 지표가 많아 신규 공격보다 리스크 관리가 중요한 상태입니다.",
        )
    return (
        "현금 지킬 구간",
        "신규 매수 보류",
        "변동성, 신용, 달러 흐름이 부담입니다. 신규 공격보다 방어와 관망이 우선입니다.",
        "위험자산을 늘리기보다 손실 방어와 현금 확보가 우선인 상태입니다.",
    )


def _confirm_conditions(score: int, risk_flags: list[str], supportive_signals: list[str]) -> list[str]:
    if score >= 72:
        return [
            "주도 섹터의 20일 상대강도가 플러스를 유지하는지 확인",
            "VIX와 신용 스프레드가 동시에 재상승하지 않는지 확인",
            "지수 상승이 대형주 한쪽 쏠림인지 시장 폭 확장인지 확인",
        ]
    if score >= 58:
        return [
            "강한 섹터만 추적하고 약한 섹터 추격은 피하기",
            "S&P 500과 Nasdaq 100이 함께 상승하는지 확인",
            "매도 우세 신호가 2개 이상 추가되면 신규 비중 확대 보류",
        ]
    if risk_flags:
        return [
            f"{risk_flags[0]} 신호가 완화되는지 확인",
            "VIX 또는 하이일드 스프레드가 안정되는지 확인",
            "섹터 리더가 방어주로만 쏠리는지 확인",
        ]
    return supportive_signals[:2] or ["지수, 신용, 달러 중 최소 2개 축이 같은 방향으로 개선되는지 확인"]


def _build_sector(spec: SectorSpec, history_points: list[dict[str, object]] | None = None) -> dict[str, object]:
    sector = _fetch_sector_index(spec.symbols, period="6mo")
    benchmark = _normalize_series(_fetch_yahoo_close(spec.benchmark, period="6mo"))
    frame = pd.concat([sector.rename("sector"), benchmark.rename("benchmark")], axis=1).dropna()
    if len(frame) < 22:
        return _empty_sector(spec)

    sector_return_20d = _window_return(frame["sector"], 20)
    benchmark_return_20d = _window_return(frame["benchmark"], 20)
    relative_strength = sector_return_20d - benchmark_return_20d
    trend_label = "시장보다 강함" if relative_strength > 0 else "시장보다 약함"
    return {
        "id": spec.id,
        "name": spec.name,
        "market": spec.market,
        "benchmark": spec.benchmark,
        "latest_date": str(frame.index[-1].date()),
        "sector_return_20d": round(sector_return_20d, 2),
        "benchmark_return_20d": round(benchmark_return_20d, 2),
        "relative_strength": round(relative_strength, 2),
        "trend_label": trend_label,
        "description": spec.description,
        "market_impact": spec.market_impact,
        "history_stats": _sector_history_stats(history_points or [], relative_strength),
        "points": [
            {
                "date": str(index.date()),
                "sector": round(float(row["sector"]), 2),
                "benchmark": round(float(row["benchmark"]), 2),
            }
            for index, row in frame.tail(126).iterrows()
        ],
    }


def _sector_flow_summary(
    sectors: list[dict[str, object]],
    leaders: list[dict[str, object]],
    laggards: list[dict[str, object]],
) -> dict[str, object]:
    total = len(sectors)
    leader_count = len(leaders)
    breadth_pct = round((leader_count / total) * 100) if total else 0
    leader_names = [str(item["name"]) for item in leaders[:3]]
    laggard_names = [str(item["name"]) for item in laggards[:3]]

    if leader_count == 0:
        breadth_label = "시장보다 강한 섹터가 없습니다"
    elif breadth_pct >= 60:
        breadth_label = "강세가 여러 섹터로 퍼져 있습니다"
    elif breadth_pct >= 35:
        breadth_label = "일부 섹터에만 돈이 몰립니다"
    else:
        breadth_label = "소수 섹터 쏠림이 강합니다"

    return {
        "leader_count": leader_count,
        "total_count": total,
        "breadth_pct": breadth_pct,
        "breadth_label": breadth_label,
        "leader_names": leader_names,
        "laggard_names": laggard_names,
        "leader_text": ", ".join(leader_names) if leader_names else "없음",
        "laggard_text": ", ".join(laggard_names) if laggard_names else "없음",
    }


def _sector_history_stats(history_points: list[dict[str, object]], current_relative_strength: float) -> dict[str, object]:
    values: list[float] = []
    for idx in range(20, len(history_points)):
        current = history_points[idx]
        previous = history_points[idx - 20]
        if not (_is_number(current.get("sector")) and _is_number(current.get("benchmark"))):
            continue
        if not (_is_number(previous.get("sector")) and _is_number(previous.get("benchmark"))):
            continue
        sector_return = _return_between(float(previous["sector"]), float(current["sector"]))
        benchmark_return = _return_between(float(previous["benchmark"]), float(current["benchmark"]))
        values.append(sector_return - benchmark_return)
    if not values:
        return _empty_history_stats()
    percentile = _percentile_rank(values, current_relative_strength)
    return {
        "lookback_years": SECTOR_HISTORY_YEARS,
        "percentile": round(percentile, 1),
        "position_label": _history_position_label(percentile),
        "zone": _relative_strength_zone(percentile),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "observations": len(values),
    }


def _empty_sector(spec: SectorSpec) -> dict[str, object]:
    return {
        "id": spec.id,
        "name": spec.name,
        "market": spec.market,
        "benchmark": spec.benchmark,
        "latest_date": "",
        "sector_return_20d": 0.0,
        "benchmark_return_20d": 0.0,
        "relative_strength": -999.0,
        "trend_label": "데이터 부족",
        "description": spec.description,
        "market_impact": spec.market_impact,
        "points": [],
    }


def _fetch_indicator_series(spec: IndicatorSpec, period: str = "1y") -> pd.Series:
    if spec.source == "fred":
        return _fetch_fred_series(spec.symbol, spec.fred_transform)
    if spec.source == "ratio":
        numerator = _fetch_yahoo_close(spec.numerator, period=period)
        denominator = _fetch_yahoo_close(spec.denominator, period=period)
        frame = pd.concat([numerator.rename("numerator"), denominator.rename("denominator")], axis=1).dropna()
        series = frame["numerator"] / frame["denominator"]
        return _clean_series(series)
    return _fetch_yahoo_close(spec.symbol, period=period)


def _data_frequency_label(spec: IndicatorSpec) -> str:
    if spec.id in {"fedfunds", "cpi_yoy", "unemployment"}:
        return "월간·지연 발표"
    if spec.source == "fred":
        return "일간·지연 가능"
    return "일간"


@lru_cache(maxsize=128)
def _fetch_yahoo_close(symbol: str, period: str = "1y") -> pd.Series:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=FutureWarning)
        history = fetch_symbol_history(symbol, period=period, interval="1d", min_rows=2)
    series = history.set_index("date")["close"].astype(float)
    return _clean_series(series)


@lru_cache(maxsize=64)
def _fetch_fred_series(symbol: str, transform: str = "level") -> pd.Series:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={symbol}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    frame = pd.read_csv(StringIO(response.text))
    if frame.empty or symbol not in frame.columns:
        raise ValueError(f"No FRED data for {symbol}")
    frame = pd.DataFrame(
        {
            "observation_date": pd.to_datetime(frame["observation_date"].to_numpy(), errors="coerce"),
            symbol: pd.to_numeric(frame[symbol].replace(".", pd.NA).to_numpy(), errors="coerce"),
        }
    )
    frame = frame.dropna(subset=["observation_date", symbol]).sort_values("observation_date")
    series = frame.set_index("observation_date")[symbol].astype(float)
    if transform == "yoy_pct":
        series = ((series / series.shift(12)) - 1.0) * 100
    return _clean_series(series)


def _fetch_sector_index(symbols: tuple[str, ...], period: str) -> pd.Series:
    normalized: list[pd.Series] = []
    for symbol in symbols:
        try:
            normalized.append(_normalize_series(_fetch_yahoo_close(symbol, period=period)).rename(symbol))
        except Exception:
            continue
    if not normalized:
        raise ValueError("No sector constituents")
    frame = pd.concat(normalized, axis=1).dropna(how="all")
    return frame.mean(axis=1).dropna()


def _normalize_series(series: pd.Series) -> pd.Series:
    clean = _clean_series(series)
    if clean.empty:
        return clean
    first = float(clean.iloc[0])
    if not first:
        return clean
    return (clean / first) * 100


def _clean_series(series: pd.Series) -> pd.Series:
    clean = series.dropna().sort_index()
    clean.index = pd.to_datetime(clean.index)
    clean = clean[~clean.index.duplicated(keep="last")]
    return clean


def _series_to_points(series: pd.Series) -> list[dict[str, object]]:
    return [{"date": str(index.date()), "value": _round_value(float(value))} for index, value in series.items()]


def _window_return(series: pd.Series, days: int) -> float:
    if len(series) <= days:
        return 0.0
    latest = float(series.iloc[-1])
    base = float(series.iloc[-(days + 1)])
    return ((latest / base) - 1.0) * 100 if base else 0.0


def _return_between(base: float, latest: float) -> float:
    return ((latest / base) - 1.0) * 100 if base else 0.0


def _percentile_rank(values: list[float], current: float) -> float:
    if not values:
        return 50.0
    below_or_equal = sum(1 for value in values if value <= current)
    return (below_or_equal / len(values)) * 100


def _history_zone(kind: str, percentile: float) -> str:
    if percentile >= 80:
        return "장기 상단 위험권" if kind == "risk_off" else "장기 상단 강세권"
    if percentile <= 20:
        return "장기 하단 안정권" if kind == "risk_off" else "장기 하단 약세권"
    return "장기 중립권"


def _relative_strength_zone(percentile: float) -> str:
    if percentile >= 80:
        return "5년 기준 강한 구간"
    if percentile <= 20:
        return "5년 기준 약한 구간"
    return "5년 기준 보통 구간"


def _history_position_label(percentile: float) -> str:
    if percentile >= 50:
        top = max(1, round(100 - percentile))
        return f"5년 중 상위 {top}% 수준"
    bottom = max(1, round(percentile))
    return f"5년 중 하위 {bottom}% 수준"


def _empty_history_stats() -> dict[str, object]:
    return {
        "lookback_years": 0,
        "percentile": None,
        "position_label": "장기 데이터 부족",
        "zone": "장기 데이터 부족",
        "min": None,
        "max": None,
        "observations": 0,
    }


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not pd.isna(value)


def _classify_signal(kind: SeriesKind, change_pct: float, change_abs: float) -> str:
    threshold = 0.15
    if abs(change_pct) < threshold and abs(change_abs) < threshold:
        return "관망"
    if kind == "risk_on":
        return "매수 우세" if change_pct > 0 else "매도 우세"
    if kind == "risk_off":
        return "매수 부담 증가" if change_pct > 0 or change_abs > 0 else "매수 부담 감소"
    return "가격 상승" if change_pct > 0 else "가격 하락"


def _round_value(value: float) -> float:
    if abs(value) >= 1000:
        return round(value, 1)
    if abs(value) >= 100:
        return round(value, 2)
    return round(value, 3)
