from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
import html
from io import StringIO
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Literal
import warnings
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from app.web.market_sources import fetch_symbol_history


SeriesKind = Literal["risk_on", "risk_off", "neutral"]
ROOT_DIR = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = ROOT_DIR / "data" / "web" / "dashboard_snapshot.json"
MARKET_CALENDAR_PATH = ROOT_DIR / "data" / "web" / "market_calendar.json"
MARKET_CALENDAR_DIR = ROOT_DIR / "data" / "web" / "calendar"
FLOATING_EVENTS_PATH = ROOT_DIR / "data" / "web" / "floating_events.json"
FLOATING_EVENTS_DIR = ROOT_DIR / "data" / "web" / "floating_events"
FLOATING_EVENT_CANDIDATES_PATH = ROOT_DIR / "data" / "web" / "floating_event_candidates.json"
MACRO_HISTORY_PATH = ROOT_DIR / "data" / "history" / "macro_history.json"
SECTOR_HISTORY_PATH = ROOT_DIR / "data" / "history" / "sector_history.json"
MACRO_HISTORY_YEARS = 5
SECTOR_HISTORY_YEARS = 5
FRED_TIMEOUT_SECONDS = 60
KST = ZoneInfo("Asia/Seoul")
NEWSDATA_LATEST_API_URL = "https://newsdata.io/api/1/latest"
FED_FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
BEA_RELEASE_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
AUTO_FIXED_SOURCE_TYPE = "auto_fixed"


def load_local_env(path: Path = ROOT_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_local_env()


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
    tracked_index: str = ""
    display_symbol: str = ""


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

MACRO_FACTOR_BUCKETS: dict[str, dict[str, object]] = {
    "equity_momentum": {
        "label": "주식 모멘텀",
        "weight": 18.0,
        "indicators": {"sp500", "nasdaq100", "russell_spy", "kospi", "kosdaq"},
    },
    "credit": {
        "label": "신용 리스크",
        "weight": 15.0,
        "indicators": {"hy_spread", "hyg_lqd"},
    },
    "volatility": {
        "label": "변동성",
        "weight": 12.0,
        "indicators": {"vix"},
    },
    "rates": {
        "label": "금리/정책",
        "weight": 8.0,
        "indicators": {"dgs10", "dgs2", "curve_10y2y", "fedfunds"},
    },
    "fx_liquidity": {
        "label": "달러/유동성",
        "weight": 8.0,
        "indicators": {"dxy", "usdkrw", "btc"},
    },
    "inflation_growth": {
        "label": "물가/성장",
        "weight": 6.0,
        "indicators": {"wti", "gold", "copper", "cpi_yoy", "unemployment"},
    },
}
MACRO_FACTOR_ORDER = tuple(MACRO_FACTOR_BUCKETS.keys())
MACRO_SCORE_WINDOWS: tuple[tuple[int, float], ...] = ((1, 0.10), (5, 0.25), (20, 0.45), (60, 0.20))
MACRO_LEVEL_SERIES = {"dgs10", "dgs2", "curve_10y2y", "hy_spread", "fedfunds", "cpi_yoy", "unemployment"}
MACRO_CUSTOM_DIRECTIONS = {
    "curve_10y2y": 1.0,
    "wti": -0.5,
    "gold": -0.3,
    "unemployment": -1.0,
}

NEWSDATA_QUERIES: tuple[dict[str, object], ...] = (
    {"market": "US", "query": "Trump Xi", "language": "en", "country": "us", "canonical": "us_china_summit", "axis": ("trade", "policy"), "required_any": ("trump xi", "trump-xi", "trump and xi", "xi meeting", "summit")},
    {"market": "US", "query": "US China summit", "language": "en", "country": "us", "canonical": "us_china_summit", "axis": ("trade", "policy"), "required_any": ("us china summit", "u.s. china summit", "china summit", "trump xi", "trump-xi")},
    {"market": "US", "query": "export controls", "language": "en", "country": "us", "canonical": "export_controls", "axis": ("trade", "semiconductor"), "required_any": ("export control", "export controls", "export restriction", "export restrictions")},
    {"market": "US", "query": "semiconductor sanctions", "language": "en", "country": "us", "canonical": "semiconductor_sanctions", "axis": ("semiconductor", "policy"), "required_any": ("semiconductor sanction", "semiconductor sanctions", "chip sanction", "chip sanctions")},
    {"market": "US", "query": "OPEC meeting", "language": "en", "country": "us", "canonical": "opec_meeting", "axis": ("oil", "geopolitics"), "required_any": ("opec meeting", "opec+", "oil output", "production cut")},
    {"market": "US", "query": "Federal Reserve", "language": "en", "country": "us", "canonical": "federal_reserve", "axis": ("rates", "policy"), "required_any": ("federal reserve", "fomc", "powell", "fed rate", "rate decision")},
    {"market": "KR", "query": "Bank of Korea", "language": "en", "country": "kr", "canonical": "bank_of_korea", "axis": ("rates", "policy"), "required_any": ("bank of korea", "bok rate", "rate decision", "monetary policy")},
    {"market": "KR", "query": "Korea exports", "language": "en", "country": "kr", "canonical": "korea_exports", "axis": ("growth", "fx"), "required_any": ("korea exports", "south korea exports", "export data", "trade data")},
    {"market": "KR", "query": "Korea short selling", "language": "en", "country": "kr", "canonical": "korea_short_selling", "axis": ("flow", "policy"), "required_any": ("short selling", "short-sale", "short sale")},
    {"market": "KR", "query": "MSCI Korea", "language": "en", "country": "kr", "canonical": "msci_korea", "axis": ("flow", "index"), "required_any": ("msci korea", "msci rebalancing", "msci rebalance")},
    {"market": "KR", "query": "South Korea semiconductor", "language": "en", "country": "kr", "canonical": "korea_semiconductor", "axis": ("semiconductor", "growth"), "required_any": ("south korea semiconductor", "korea semiconductor", "chip export", "memory chip")},
    {"market": "KR", "query": "미중 정상회담", "language": "ko", "country": "kr", "canonical": "us_china_summit", "axis": ("trade", "policy"), "required_any": ("미중 정상회담", "미·중 정상회담", "트럼프 시진핑")},
    {"market": "KR", "query": "관세", "language": "ko", "country": "kr", "canonical": "tariffs", "axis": ("trade", "policy"), "required_any": ("관세", "상호관세", "무역협상")},
    {"market": "KR", "query": "수출통제", "language": "ko", "country": "kr", "canonical": "export_controls", "axis": ("trade", "semiconductor"), "required_any": ("수출통제", "수출 규제", "수출규제")},
    {"market": "KR", "query": "금통위", "language": "ko", "country": "kr", "canonical": "bank_of_korea", "axis": ("rates", "policy"), "required_any": ("금통위", "한국은행", "기준금리")},
)
FLOATING_EVENT_BLOCKLIST = {"stock picks", "analyst says", "opinion", "사설", "추천주"}
FLOATING_EVENT_NOISE_TERMS = {
    "roadway",
    "roadways",
    "closed in",
    "armed robbery",
    "server rack",
    "casino",
    "covered call etf",
    "yield calculations",
    "deadline alert",
    "class action",
    "class actions",
    "law offices",
    "shareholders",
    "securities fraud",
    "reminds investors",
    "investors of",
    "lead plaintiff",
    "lawsuit",
}
HIGH_IMPACT_TERMS = {
    "summit",
    "tariff",
    "sanction",
    "export control",
    "fomc",
    "opec",
    "금통위",
    "공매도",
    "리밸런싱",
    "관세",
    "제재",
    "수출통제",
}
MARKET_AXIS_TERMS = {
    "rate",
    "fed",
    "fomc",
    "oil",
    "opec",
    "tariff",
    "sanction",
    "export",
    "semiconductor",
    "china",
    "korea",
    "msci",
    "금리",
    "환율",
    "유가",
    "관세",
    "제재",
    "반도체",
    "금통위",
    "공매도",
}


US_SECTOR_SPECS: tuple[SectorSpec, ...] = (
    SectorSpec("us-tech", "기술", "US", "SPY", ("XLK",), "소프트웨어, 하드웨어, 플랫폼 대형주의 흐름이다.", "시장보다 강하면 성장주 위험선호가 살아있다고 본다.", "Technology Select Sector Index", "XLK"),
    SectorSpec("us-semi", "반도체", "US", "SPY", ("SOXX",), "AI, 데이터센터, 메모리/장비 사이클을 압축해서 본다.", "강세는 시장의 공격성이 높다는 뜻이고, 약세 전환은 고베타 축소 신호다.", "ICE Semiconductor Index", "SOXX"),
    SectorSpec("us-financials", "금융", "US", "SPY", ("XLF",), "은행, 보험, 브로커리지의 흐름이다.", "금리곡선과 신용 스트레스에 민감해 경기 신뢰도를 함께 보여준다.", "Financial Select Sector Index", "XLF"),
    SectorSpec("us-energy", "에너지", "US", "SPY", ("XLE",), "원유/가스 가격과 에너지주 수급을 반영한다.", "강하면 인플레이션 재상승 가능성과 가치주 선호를 같이 점검한다.", "Energy Select Sector Index", "XLE"),
    SectorSpec("us-healthcare", "헬스케어", "US", "SPY", ("XLV",), "제약, 바이오, 의료장비의 방어적 성장 흐름이다.", "하락장에서도 강하면 방어적 자금 이동으로 해석한다.", "Health Care Select Sector Index", "XLV"),
    SectorSpec("us-industrials", "산업재", "US", "SPY", ("XLI",), "운송, 기계, 방산, 인프라 관련주 흐름이다.", "강세는 경기 확장 기대와 설비투자 기대를 반영할 수 있다.", "Industrial Select Sector Index", "XLI"),
    SectorSpec("us-discretionary", "경기소비재", "US", "SPY", ("XLY",), "자동차, 이커머스, 레저 등 소비 경기 민감주다.", "강세는 소비 여력과 위험선호 개선 신호다.", "Consumer Discretionary Select Sector Index", "XLY"),
    SectorSpec("us-staples", "필수소비재", "US", "SPY", ("XLP",), "식품, 생활용품 등 방어 섹터다.", "시장보다 강하면 방어적 로테이션일 가능성을 본다.", "Consumer Staples Select Sector Index", "XLP"),
    SectorSpec("us-communication", "커뮤니케이션", "US", "SPY", ("XLC",), "광고, 미디어, 플랫폼 기업 흐름이다.", "기술주와 함께 강하면 성장주 랠리의 폭을 확인하는 데 유용하다.", "Communication Services Select Sector Index", "XLC"),
    SectorSpec("us-utilities", "유틸리티", "US", "SPY", ("XLU",), "전력/가스 등 배당 방어 섹터다.", "강세는 방어 자금 또는 금리 하락 수혜를 의미할 수 있다.", "Utilities Select Sector Index", "XLU"),
)


KR_SECTOR_SPECS: tuple[SectorSpec, ...] = (
    SectorSpec("kr-semi", "반도체", "KR", "^KS11", ("091160.KS",), "KODEX 반도체 ETF 흐름이다.", "코스피보다 강하면 한국 시장의 주도축이 반도체로 모이는지 우선 확인한다.", "KRX 반도체", "KODEX 반도체"),
    SectorSpec("kr-it", "IT", "KR", "^KS11", ("266370.KS",), "KODEX IT ETF 흐름이다.", "반도체를 포함한 정보기술 전반으로 자금이 확산되는지 확인한다.", "KRX IT", "KODEX IT"),
    SectorSpec("kr-auto", "자동차", "KR", "^KS11", ("091180.KS",), "KODEX 자동차 ETF 흐름이다.", "강세는 수출주와 경기민감 대형주 수급 개선으로 해석할 수 있다.", "KRX 자동차", "KODEX 자동차"),
    SectorSpec("kr-bank", "은행", "KR", "^KS11", ("091170.KS",), "KODEX 은행 ETF 흐름이다.", "강세는 금리, 배당, 경기 신뢰 개선과 함께 본다.", "KRX 은행", "KODEX 은행"),
    SectorSpec("kr-securities", "증권", "KR", "^KS11", ("102970.KS",), "KODEX 증권 ETF 흐름이다.", "강세는 거래대금 증가와 위험선호 개선 가능성을 함께 보여준다.", "KRX 증권", "KODEX 증권"),
    SectorSpec("kr-insurance", "보험", "KR", "^KS11", ("140700.KS",), "KODEX 보험 ETF 흐름이다.", "강세는 금리 레벨, 배당 선호, 금융주 방어력을 함께 반영할 수 있다.", "KRX 보험", "KODEX 보험"),
    SectorSpec("kr-healthcare", "헬스케어", "KR", "^KS11", ("266420.KS",), "KODEX 헬스케어 ETF 흐름이다.", "시장보다 강하면 방어 성장주 또는 바이오 이벤트 수급을 확인한다.", "KRX 헬스케어", "KODEX 헬스케어"),
    SectorSpec("kr-discretionary", "경기소비재", "KR", "^KS11", ("266390.KS",), "KODEX 경기소비재 ETF 흐름이다.", "강세는 내수와 소비 경기 민감주로 자금이 이동하는 신호일 수 있다.", "KRX 경기소비재", "KODEX 경기소비재"),
    SectorSpec("kr-staples", "필수소비재", "KR", "^KS11", ("266410.KS",), "KODEX 필수소비재 ETF 흐름이다.", "하락장에서도 강하면 방어적 자금 이동으로 해석한다.", "KRX 필수소비재", "KODEX 필수소비재"),
    SectorSpec("kr-k-content", "미디어/엔터", "KR", "^KS11", ("266360.KS",), "KODEX K콘텐츠 ETF 흐름이다.", "강세는 콘텐츠, 미디어, 엔터테인먼트 테마 수급 회복으로 해석한다.", "KRX 미디어&엔터테인먼트", "KODEX K콘텐츠"),
    SectorSpec("kr-energy-chemical", "에너지/화학", "KR", "^KS11", ("117460.KS",), "KODEX 에너지화학 ETF 흐름이다.", "강세는 유가, 화학 스프레드, 소재 수요 기대와 함께 해석한다.", "KRX 에너지화학", "KODEX 에너지화학"),
    SectorSpec("kr-steel", "철강", "KR", "^KS11", ("117680.KS",), "KODEX 철강 ETF 흐름이다.", "강세는 경기민감 소재와 중국/인프라 수요 기대를 함께 점검한다.", "KRX 철강", "KODEX 철강"),
    SectorSpec("kr-machinery", "기계/장비", "KR", "^KS11", ("102960.KS",), "KODEX 기계장비 ETF 흐름이다.", "강세는 조선, 기계, 장비 업종으로 경기민감 수급이 확산되는 신호일 수 있다.", "KRX 기계장비", "KODEX 기계장비"),
    SectorSpec("kr-construction", "건설", "KR", "^KS11", ("117700.KS",), "KODEX 건설 ETF 흐름이다.", "강세는 건설, 인프라, 부동산 정책 기대를 함께 반영할 수 있다.", "KRX 건설", "KODEX 건설"),
    SectorSpec("kr-transportation", "운송", "KR", "^KS11", ("140710.KS",), "KODEX 운송 ETF 흐름이다.", "강세는 항공, 해운, 물류 수요와 글로벌 교역 기대를 함께 보여준다.", "KRX 운송", "KODEX 운송"),
)


def get_macro_dashboard() -> dict[str, object]:
    snapshot = load_dashboard_snapshot()
    if snapshot is not None:
        macro = snapshot.get("macro")
        if isinstance(macro, dict):
            return _rebuild_macro_snapshot_decision(macro)
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


def get_market_calendar(
    calendar_path: Path = MARKET_CALENDAR_DIR,
    floating_events_path: Path = FLOATING_EVENTS_DIR,
    floating_candidates_path: Path = FLOATING_EVENT_CANDIDATES_PATH,
    today: date | None = None,
    month: str | None = None,
) -> dict[str, object]:
    today_kst = today or datetime.now(KST).date()
    month_start = _month_start_from_key(month) if month else today_kst.replace(day=1)
    month_key = month_start.strftime("%Y-%m")
    fixed_events = _load_monthly_event_list(calendar_path, month_key, legacy_path=MARKET_CALENDAR_PATH)
    # Floating event collection is still kept for future tuning, but the
    # calendar page currently exposes only fixed releases.
    floating_events: list[dict[str, object]] = []
    normalized_fixed = sorted((_normalize_calendar_event(item) for item in fixed_events), key=_event_sort_key)
    normalized_floating = sorted((_normalize_floating_event(item) for item in floating_events), key=_event_sort_key)
    next_month = _add_months(month_start, 1)
    month_events = [item for item in normalized_fixed if month_start <= _parse_event_date(item["date"]) < next_month]
    month_floating_events = [
        item
        for item in normalized_floating
        if item["date"] == "날짜 미확정" or month_start <= _parse_event_date(item["date"]) < next_month
    ]
    events_by_date = _events_by_date(month_events)
    dated_floating_events = [item for item in month_floating_events if item["date"] != "날짜 미확정"]
    floating_by_date = _events_by_date(dated_floating_events)
    all_events_by_date = _events_by_date([*month_events, *dated_floating_events])
    calendar_days = _calendar_days(month_start, events_by_date, floating_by_date, today_kst)
    upcoming = [item for item in normalized_fixed if _parse_event_date(item["date"]) >= today_kst][:12]

    return {
        "today": today_kst.isoformat(),
        "month": {
            "label": f"{month_start.year}년 {month_start.month}월",
            "start": month_start.isoformat(),
            "key": month_key,
            "previous_key": _add_months(month_start, -1).strftime("%Y-%m"),
            "next_key": next_month.strftime("%Y-%m"),
            "is_current": month_key == today_kst.strftime("%Y-%m"),
        },
        "fixed_events": normalized_fixed,
        "floating_events": month_floating_events,
        "month_events": month_events,
        "events_by_date": all_events_by_date,
        "calendar_days": calendar_days,
        "upcoming_fixed": upcoming,
        "stats": {
            "fixed_total": len(month_events),
            "floating_total": len(month_floating_events),
            "high_total": sum(1 for item in month_events if item["importance"] == "high"),
        },
    }


def _rebuild_macro_snapshot_decision(macro: dict[str, object]) -> dict[str, object]:
    groups = macro.get("groups")
    if not isinstance(groups, dict):
        return macro
    indicators: list[dict[str, object]] = []
    for items in groups.values():
        if isinstance(items, list):
            indicators.extend(item for item in items if isinstance(item, dict) and item.get("points"))
    if not indicators:
        return macro

    rebuilt = dict(macro)
    decision = _build_macro_decision(indicators)
    rebuilt["decision"] = decision
    rebuilt["ai_summary"] = _fallback_macro_summary(decision)
    return rebuilt


def build_dashboard_snapshot(
    macro_history: dict[str, object] | None = None,
    sector_history: dict[str, object] | None = None,
) -> dict[str, object]:
    if macro_history is None:
        macro_history = build_macro_history(previous_history=load_json_file(MACRO_HISTORY_PATH))
    if sector_history is None:
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
    floating_candidates_path: Path = FLOATING_EVENT_CANDIDATES_PATH,
) -> dict[str, object]:
    previous_macro_history = load_json_file(macro_history_path)
    macro_history = build_macro_history(previous_history=previous_macro_history)
    sector_history = build_sector_history()
    refresh_fixed_calendar_events()
    refresh_floating_event_candidates(path=floating_candidates_path)
    snapshot = build_dashboard_snapshot(macro_history=macro_history, sector_history=sector_history)
    _write_json_atomic(path, snapshot)
    _write_json_atomic(macro_history_path, macro_history)
    _write_json_atomic(sector_history_path, sector_history)
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


def load_json_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return payload


def refresh_floating_event_candidates(path: Path = FLOATING_EVENT_CANDIDATES_PATH) -> dict[str, object]:
    if not _news_collection_enabled():
        payload = _floating_candidates_status("disabled", "News collection disabled by environment.", [])
        _write_json_atomic(path, payload)
        return payload

    previous = load_json_file(path)
    previous_candidates = previous.get("candidates", []) if isinstance(previous, dict) else []
    try:
        payload = _collect_news_candidates()
    except Exception as exc:
        kept = previous_candidates if isinstance(previous_candidates, list) else []
        payload = _floating_candidates_status("failed", str(exc), kept)
    else:
        status = payload.get("collection_status") if isinstance(payload, dict) else {}
        kept = previous_candidates if isinstance(previous_candidates, list) else []
        if kept and _should_keep_previous_candidates(status):
            payload = _floating_candidates_status("failed", _collection_status_message(status), kept)
    _write_json_atomic(path, payload)
    return payload


def refresh_fixed_calendar_events(calendar_dir: Path = MARKET_CALENDAR_DIR, year: int | None = None) -> dict[str, object]:
    target_year = year or datetime.now(KST).year
    if not _fixed_calendar_collection_enabled():
        return {"status": "disabled", "events": []}
    events: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    for collector in (_collect_fomc_events, _collect_bea_events):
        try:
            events.extend(collector(target_year))
        except Exception as exc:
            errors.append({"source": collector.__name__, "error": str(exc)})
    events = _dedupe_calendar_events(events)
    _write_monthly_auto_events(calendar_dir, target_year, events)
    return {
        "status": "ok" if events else "empty",
        "year": target_year,
        "events": events,
        "errors": errors,
    }


def _collect_fomc_events(year: int) -> list[dict[str, object]]:
    response = requests.get(FED_FOMC_CALENDAR_URL, timeout=_env_int("FIXED_CALENDAR_TIMEOUT_SECONDS", 30))
    response.raise_for_status()
    text = response.text
    panel_match = re.search(rf'{year} FOMC Meetings</a>.*?(?=<div class="panel panel-default"|<div class="panel-footer")', text, re.S)
    if not panel_match:
        return []
    panel = panel_match.group(0)
    pattern = re.compile(
        r'fomc-meeting[^>]*month[^>]*>\s*<strong>(?P<month>[A-Za-z]+)</strong>.*?'
        r'fomc-meeting__date[^>]*>(?P<days>[^<]+)</div>',
        re.S,
    )
    events = []
    for match in pattern.finditer(panel):
        month_name = match.group("month")
        days_text = html.unescape(match.group("days")).strip().replace("*", "")
        day = int(days_text.split("-")[-1])
        event_date = date(year, _month_number(month_name), day)
        has_projection = "*" in match.group("days")
        events.append(
            {
                "date": event_date.isoformat(),
                "time_kst": "03:00",
                "market": "US",
                "category": "정책",
                "title": "FOMC 기준금리 결정",
                "importance": "high",
                "source_name": "Federal Reserve",
                "source_url": FED_FOMC_CALENDAR_URL,
                "why_it_matters": "연준 정책금리와 기자회견은 미국 금리 기대, 달러, 성장주 밸류에이션에 직접 영향을 준다.",
                "source_type": AUTO_FIXED_SOURCE_TYPE,
            }
        )
        if has_projection:
            events[-1]["title"] = "FOMC 기준금리 결정 및 점도표"
    return events


def _collect_bea_events(year: int) -> list[dict[str, object]]:
    response = requests.get(BEA_RELEASE_SCHEDULE_URL, timeout=_env_int("FIXED_CALENDAR_TIMEOUT_SECONDS", 30))
    response.raise_for_status()
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", response.text, flags=re.S)
    events = []
    for row in rows:
        date_match = re.search(r'<div class="release-date">([^<]+)</div>\s*<small[^>]*>([^<]+)</small>', row, re.S)
        title_match = re.search(r'class="release-title[^"]*"[^>]*>(.*?)</td>', row, re.S)
        if not date_match or not title_match:
            continue
        title = _clean_html(title_match.group(1))
        if not _is_tracked_bea_release(title):
            continue
        release_date = _parse_month_day(year, date_match.group(1))
        time_kst = _us_eastern_to_kst(release_date, date_match.group(2))
        category = "성장" if "GDP" in title or "Trade" in title else "소비"
        importance = "high" if "GDP" in title or "Personal Income and Outlays" in title else "medium"
        events.append(
            {
                "date": release_date.isoformat(),
                "time_kst": time_kst,
                "market": "US",
                "category": category,
                "title": _bea_display_title(title),
                "importance": importance,
                "source_name": "BEA",
                "source_url": BEA_RELEASE_SCHEDULE_URL,
                "why_it_matters": _bea_market_note(title),
                "source_type": AUTO_FIXED_SOURCE_TYPE,
            }
        )
    return events


def _write_monthly_auto_events(calendar_dir: Path, year: int, auto_events: list[dict[str, object]]) -> None:
    by_month: dict[str, list[dict[str, object]]] = {}
    for event in auto_events:
        by_month.setdefault(str(event["date"])[:7], []).append(event)
    calendar_dir.mkdir(parents=True, exist_ok=True)
    for month in [f"{year}-{month:02d}" for month in range(1, 13)]:
        path = calendar_dir / f"{month}.json"
        existing = _load_event_list(path)
        manual_events = [event for event in existing if event.get("source_type") != AUTO_FIXED_SOURCE_TYPE]
        merged = sorted([*manual_events, *by_month.get(month, [])], key=_event_sort_key)
        _write_json_atomic(path, {"month": month, "events": merged})


def _dedupe_calendar_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    result = []
    for event in events:
        key = (str(event.get("date", "")), str(event.get("title", "")), str(event.get("source_name", "")))
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return sorted(result, key=_event_sort_key)


def _month_number(month_name: str) -> int:
    return datetime.strptime(month_name[:3], "%b").month


def _parse_month_day(year: int, value: str) -> date:
    parsed = datetime.strptime(f"{value.strip()} {year}", "%B %d %Y")
    return date(parsed.year, parsed.month, parsed.day)


def _us_eastern_to_kst(release_date: date, time_text: str) -> str:
    eastern = ZoneInfo("America/New_York")
    parsed_time = datetime.strptime(time_text.strip(), "%I:%M %p").time()
    release_dt = datetime.combine(release_date, parsed_time, tzinfo=eastern)
    return release_dt.astimezone(KST).strftime("%H:%M")


def _clean_html(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()


def _is_tracked_bea_release(title: str) -> bool:
    return any(
        token in title
        for token in (
            "GDP",
            "Personal Income and Outlays",
            "U.S. International Trade in Goods and Services",
        )
    )


def _bea_display_title(title: str) -> str:
    if title.startswith("GDP"):
        return f"미국 {title}"
    if title.startswith("Personal Income and Outlays"):
        return f"미국 PCE/개인소득 - {title}"
    if title.startswith("U.S. International Trade"):
        return f"미국 무역수지 - {title}"
    return title


def _bea_market_note(title: str) -> str:
    if title.startswith("GDP"):
        return "미국 성장률은 경기 둔화/확장 기대와 주식시장 위험선호에 직접 영향을 준다."
    if title.startswith("Personal Income and Outlays"):
        return "개인소득과 PCE 물가는 소비 경기와 연준 금리 기대를 함께 움직인다."
    if title.startswith("U.S. International Trade"):
        return "무역수지는 달러, 글로벌 수요, 경기민감 섹터 해석에 영향을 준다."
    return "미국 경제 지표 발표는 금리 기대와 시장 위험선호에 영향을 줄 수 있다."


def _collect_news_candidates() -> dict[str, object]:
    api_key = os.getenv("NEWSDATA_API_KEY", "").strip()
    if not api_key:
        return _floating_candidates_status("disabled", "NEWSDATA_API_KEY is not configured.", [])
    return _collect_newsdata_candidates(api_key)


def _collect_newsdata_candidates(api_key: str) -> dict[str, object]:
    max_queries = _env_int("NEWSDATA_MAX_QUERIES_PER_REFRESH", 15)
    timeout = _env_int("NEWSDATA_TIMEOUT_SECONDS", 30)
    min_interval = _env_float("NEWSDATA_MIN_REQUEST_INTERVAL_SECONDS", 3.0)
    candidates_by_key: dict[str, dict[str, object]] = {}
    queries_run: list[str] = []
    errors: list[dict[str, str]] = []

    for index, config in enumerate(NEWSDATA_QUERIES[:max_queries]):
        if index:
            time.sleep(min_interval)
        query = str(config["query"])
        try:
            payload = _fetch_newsdata_articles(api_key, config, timeout=timeout)
        except Exception as exc:
            error = str(exc)
            errors.append({"query": query, "error": error})
            if _is_newsdata_rate_limit_error(error):
                break
            continue
        articles = payload.get("results", [])
        if not isinstance(articles, list):
            continue
        queries_run.append(query)
        for article in articles:
            if not isinstance(article, dict):
                continue
            candidate = _newsdata_article_candidate(article, config)
            if candidate is None:
                continue
            key = str(candidate["canonical_key"])
            existing = candidates_by_key.get(key)
            if existing is None:
                candidates_by_key[key] = candidate
            else:
                _merge_candidate(existing, candidate)

    candidates = sorted(candidates_by_key.values(), key=lambda item: (-int(item["score"]), str(item["title"])))
    return {
        "collection_status": {
            "status": "ok" if candidates else "empty",
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "newsdata_io",
            "queries_run": queries_run,
            "query_count": len(queries_run),
            "errors": errors[:10],
        },
        "candidates": candidates,
    }


def _fetch_newsdata_articles(api_key: str, config: dict[str, object], timeout: int) -> dict[str, object]:
    params = {
        "apikey": api_key,
        "q": str(config["query"]),
        "language": str(config.get("language", "")),
        "country": str(config.get("country", "")),
    }
    response = requests.get(NEWSDATA_LATEST_API_URL, params=params, timeout=timeout)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"NewsData.io returned non-JSON response: {response.text[:120]}") from exc
    if response.status_code >= 400:
        raise RuntimeError(str(payload.get("message") or payload.get("results") or response.status_code))
    if payload.get("status") == "error":
        raise RuntimeError(str(payload.get("results") or payload.get("message") or "NewsData.io error"))
    if not isinstance(payload, dict):
        raise RuntimeError("NewsData.io returned an invalid payload.")
    return payload


def _should_keep_previous_candidates(status: object) -> bool:
    if not isinstance(status, dict):
        return False
    errors = status.get("errors")
    query_count = int(status.get("query_count", 0) or 0)
    if query_count > 0 or not isinstance(errors, list) or not errors:
        return False
    return any(_is_newsdata_rate_limit_error(str(item.get("error", ""))) for item in errors if isinstance(item, dict))


def _collection_status_message(status: object) -> str:
    if not isinstance(status, dict):
        return "NewsData.io collection failed; kept previous candidates."
    errors = status.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        return f"NewsData.io collection failed; kept previous candidates. First error: {errors[0].get('error', '')}"
    return "NewsData.io collection failed; kept previous candidates."


def _is_newsdata_rate_limit_error(message: str) -> bool:
    lowered = message.lower()
    return "rate limit" in lowered or "ratelimitexceeded" in lowered


def _load_event_list(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
    raise ValueError(f"Invalid event JSON: {path}")


def _load_monthly_event_list(path: Path, month_key: str, legacy_path: Path | None = None) -> list[dict[str, object]]:
    if path.is_dir() or path.suffix == "":
        monthly_path = path / f"{month_key}.json"
        events = _load_event_list(monthly_path)
        if events:
            return events
        if legacy_path is not None:
            return [
                item
                for item in _load_event_list(legacy_path)
                if str(item.get("date", "")).startswith(month_key)
            ]
        return []
    return [
        item
        for item in _load_event_list(path)
        if str(item.get("date", "")).startswith(month_key)
    ]


def _candidate_events_for_month(path: Path, month_key: str) -> list[dict[str, object]]:
    payload = load_json_file(path)
    if not isinstance(payload, dict):
        return []
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        return []
    events = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        event_date = _candidate_event_date(candidate)
        if not event_date:
            event_date = "날짜 미확정"
        if event_date != "날짜 미확정" and not event_date.startswith(month_key):
            continue
        if event_date == "날짜 미확정" and not _candidate_published_date(candidate).startswith(month_key):
            continue
        sources = candidate.get("sources")
        first_source = sources[0] if isinstance(sources, list) and sources and isinstance(sources[0], dict) else {}
        events.append(
            {
                "date": event_date,
                "published_date": _candidate_published_date(candidate),
                "event_date": event_date if event_date != "날짜 미확정" else "",
                "event_end_date": _candidate_event_end_date(candidate),
                "date_confidence": _candidate_date_confidence(candidate),
                "time_kst": "",
                "status": _candidate_event_status(candidate),
                "market": _normalize_choice(candidate.get("market"), {"US", "KR", "GLOBAL"}, "GLOBAL"),
                "category": _candidate_event_category(candidate),
                "title": str(candidate.get("title", "")),
                "short_label": _candidate_short_label(candidate),
                "importance": "high" if int(candidate.get("score", 0)) >= 25 else "medium",
                "source_name": str(first_source.get("domain", "NewsData.io")),
                "source_url": str(first_source.get("url", "")),
                "why_it_matters": _candidate_market_note(candidate),
            }
        )
    return events


def _candidate_event_date(candidate: dict[str, object]) -> str:
    event_date = str(candidate.get("event_date", ""))
    if event_date:
        return event_date
    inferred = _infer_candidate_date(
        title=str(candidate.get("title", "")),
        description=" ".join(
            str(source.get("title", ""))
            for source in candidate.get("sources", [])
            if isinstance(source, dict)
        )
        if isinstance(candidate.get("sources"), list)
        else "",
        canonical_key=str(candidate.get("canonical_key", "")),
        published_date=_candidate_published_date(candidate),
    )
    return inferred["event_date"]


def _candidate_published_date(candidate: dict[str, object]) -> str:
    published_date = str(candidate.get("published_date", ""))
    if published_date:
        return published_date
    sources = candidate.get("sources")
    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue
            seen = str(source.get("seendate", ""))
            if len(seen) >= 10:
                return seen[:10]
    seen = str(candidate.get("last_seen", ""))
    return seen[:10] if len(seen) >= 10 else datetime.now(KST).date().isoformat()


def _candidate_event_end_date(candidate: dict[str, object]) -> str:
    if candidate.get("event_end_date"):
        return str(candidate.get("event_end_date", ""))
    inferred = _infer_candidate_date(
        title=str(candidate.get("title", "")),
        description="",
        canonical_key=str(candidate.get("canonical_key", "")),
        published_date=_candidate_published_date(candidate),
    )
    return inferred["event_end_date"]


def _candidate_date_confidence(candidate: dict[str, object]) -> str:
    if candidate.get("date_confidence"):
        return str(candidate.get("date_confidence", "low"))
    inferred = _infer_candidate_date(
        title=str(candidate.get("title", "")),
        description="",
        canonical_key=str(candidate.get("canonical_key", "")),
        published_date=_candidate_published_date(candidate),
    )
    return inferred["date_confidence"]


def _candidate_event_status(candidate: dict[str, object]) -> str:
    score = int(candidate.get("score", 0))
    if score >= 25:
        return "예정"
    return "관측"


def _candidate_event_category(candidate: dict[str, object]) -> str:
    axes = {str(axis) for axis in candidate.get("axis", []) if str(axis)}
    key = str(candidate.get("canonical_key", ""))
    if "rates" in axes:
        return "정책"
    if "oil" in axes:
        return "원자재"
    if "flow" in axes or "index" in axes:
        return "금리/수급"
    if "semiconductor" in axes or "trade" in axes or key in {"us_china_summit", "export_controls", "tariffs"}:
        return "정책"
    return "정책"


def _candidate_market_note(candidate: dict[str, object]) -> str:
    key = str(candidate.get("canonical_key", ""))
    if key == "us_china_summit":
        return "미중 협상 의제는 관세, 대만, AI/반도체 정책 기대를 통해 지수와 섹터 변동성을 키울 수 있다."
    if key == "bank_of_korea":
        return "한국은행 관련 뉴스는 기준금리 기대, 금융 안정, 원화와 한국 증시 수급에 영향을 줄 수 있다."
    if key == "federal_reserve":
        return "연준 관련 뉴스는 미국 금리 기대와 성장주 밸류에이션에 영향을 줄 수 있다."
    if key in {"export_controls", "semiconductor_policy", "semiconductor_sanctions"}:
        return "수출통제와 반도체 정책 뉴스는 AI/반도체 공급망과 관련 섹터 심리에 영향을 줄 수 있다."
    return "뉴스 흐름에 따라 시장 심리와 관련 섹터 변동성에 영향을 줄 수 있다."


def _candidate_short_label(candidate: dict[str, object]) -> str:
    key = str(candidate.get("canonical_key", ""))
    if key == "us_china_summit":
        return "미중"
    if key == "bank_of_korea":
        return "BOK"
    if key == "federal_reserve":
        return "Fed"
    if key in {"export_controls", "semiconductor_policy", "semiconductor_sanctions"}:
        return "수출통제"
    if key == "opec_meeting":
        return "OPEC"
    return _compact_label(str(candidate.get("title", "")))


def _event_short_label(event: dict[str, object]) -> str:
    title = str(event.get("title", ""))
    lowered = title.lower()
    if "fomc" in lowered:
        return "FOMC"
    if "pce" in lowered or "personal income and outlays" in lowered:
        return "PCE"
    if "gdp" in lowered:
        return "GDP"
    if "trade" in lowered or "무역" in title:
        return "무역"
    if "cpi" in lowered:
        return "CPI"
    if "employment" in lowered or "고용" in title:
        return "고용"
    if "bank of korea" in lowered or "금통위" in title or "한국은행" in title:
        return "BOK"
    return _compact_label(title)


def _compact_label(title: str) -> str:
    words = re.findall(r"[A-Za-z0-9가-힣]+", title)
    if not words:
        return "이벤트"
    if len(words[0]) >= 2:
        return words[0][:8]
    return " ".join(words[:2])[:8]


def _normalize_calendar_event(item: dict[str, object]) -> dict[str, object]:
    event = {
        "date": str(item.get("date", "")),
        "time_kst": str(item.get("time_kst", "")),
        "market": _normalize_choice(item.get("market"), {"US", "KR", "GLOBAL"}, "GLOBAL"),
        "category": str(item.get("category", "정책")),
        "title": str(item.get("title", "")),
        "importance": _normalize_choice(item.get("importance"), {"high", "medium", "low"}, "medium"),
        "source_name": str(item.get("source_name", "")),
        "source_url": str(item.get("source_url", "")),
        "why_it_matters": str(item.get("why_it_matters", "")),
    }
    for optional_key in ("published_date", "event_date", "event_end_date", "date_confidence"):
        if item.get(optional_key):
            event[optional_key] = str(item.get(optional_key, ""))
    event["short_label"] = str(item.get("short_label") or _event_short_label(event))
    return event


def _normalize_floating_event(item: dict[str, object]) -> dict[str, object]:
    event = _normalize_calendar_event(item)
    event["status"] = _normalize_choice(item.get("status"), {"확정", "예정", "관측"}, "예정")
    event["short_label"] = str(item.get("short_label") or _event_short_label(event))
    return event


def _normalize_choice(value: object, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _event_sort_key(item: dict[str, object]) -> tuple[str, str, str]:
    return (str(item.get("date", "")), str(item.get("time_kst", "")), str(item.get("title", "")))


def _parse_event_date(value: object) -> date:
    if str(value) == "날짜 미확정":
        return date.max
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return date.max


def _add_months(value: date, months: int) -> date:
    month_index = (value.month - 1) + months
    year = value.year + (month_index // 12)
    month = (month_index % 12) + 1
    return date(year, month, 1)


def _month_start_from_key(value: str | None) -> date:
    if not value:
        return datetime.now(KST).date().replace(day=1)
    try:
        parsed = datetime.strptime(value, "%Y-%m")
    except ValueError:
        return datetime.now(KST).date().replace(day=1)
    return date(parsed.year, parsed.month, 1)


def _events_by_date(events: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for item in events:
        grouped.setdefault(str(item["date"]), []).append(item)
    return grouped


def _calendar_days(
    month_start: date,
    events_by_date: dict[str, list[dict[str, object]]],
    floating_by_date: dict[str, list[dict[str, object]]],
    today: date,
) -> list[dict[str, object]]:
    next_month = _add_months(month_start, 1)
    first_day = month_start - timedelta(days=month_start.weekday())
    last_month_day = next_month - timedelta(days=1)
    last_day = last_month_day + timedelta(days=6 - last_month_day.weekday())
    days = []
    current = first_day
    while current <= last_day:
        events = events_by_date.get(current.isoformat(), [])
        floating_events = floating_by_date.get(current.isoformat(), [])
        visible_events = [*events, *floating_events]
        all_events = visible_events
        days.append(
            {
                "date": current.isoformat(),
                "day": current.day,
                "in_month": current.month == month_start.month,
                "is_today": current == today,
                "events": events[:3],
                "all_events": all_events,
                "floating_events": floating_events[: max(0, 3 - len(events[:3]))],
                "fixed_count": len(events),
                "floating_count": len(floating_events),
                "total_count": len(all_events),
                "hidden_count": max(0, len(visible_events) - 3),
                "has_high": any(item["importance"] == "high" for item in all_events),
            }
        )
        current += timedelta(days=1)
    return days


def _newsdata_article_candidate(article: dict[str, object], config: dict[str, object]) -> dict[str, object] | None:
    title = str(article.get("title", "")).strip()
    if not title:
        return None
    description = str(article.get("description") or "")
    haystack = " ".join([title, description, str(article.get("source_id", "")), str(article.get("country", ""))]).lower()
    if any(blocked in haystack for blocked in FLOATING_EVENT_BLOCKLIST | FLOATING_EVENT_NOISE_TERMS):
        return None
    if str(config.get("canonical", "")) == "opec_meeting" and not any(
        term in title.lower() for term in ("opec", "opec+", "production cut", "oil output")
    ):
        return None
    if not _article_matches_query_gate(haystack, config):
        return None
    canonical_key = _canonical_event_key(f"{title} {description}", str(config.get("canonical", "")), strict=True)
    axes = tuple(str(axis) for axis in config.get("axis", ()) if str(axis))
    article_date = str(article.get("pubDate", "")).split(" ")[0] or datetime.now(KST).date().isoformat()
    date_info = _infer_candidate_date(
        title=title,
        description=description,
        canonical_key=canonical_key,
        published_date=article_date,
    )
    source = str(article.get("source_id") or article.get("source_name") or "")
    market = str(config.get("market", "GLOBAL"))
    score = _floating_keyword_score(
        title=f"{title} {description}",
        axes=axes,
        source_count=1 if source else 0,
        article_count=1,
        bilingual_match=False,
    )
    return {
        "canonical_key": canonical_key,
        "title": title,
        "market": market,
        "axis": list(axes),
        "score": score,
        "hit_count": 1,
        "source_count": 1 if source else 0,
        "first_seen": article_date,
        "last_seen": article_date,
        "published_date": article_date,
        "event_date": date_info["event_date"],
        "event_end_date": date_info["event_end_date"],
        "date_confidence": date_info["date_confidence"],
        "expires_at": (datetime.now(KST).date() + timedelta(days=14)).isoformat(),
        "status": "candidate",
        "sources": [
            {
                "title": title,
                "url": str(article.get("link", "")),
                "domain": source,
                "language": str(article.get("language", "")),
                "sourcecountry": ",".join(str(item) for item in article.get("country", []) if item) if isinstance(article.get("country"), list) else str(article.get("country", "")),
                "seendate": str(article.get("pubDate", "")),
            }
        ],
    }


def _canonical_event_key(title: str, fallback: str, strict: bool = False) -> str:
    lowered = title.lower()
    if any(token in lowered for token in ("trump xi", "trump-xi", "미중 정상회담", "미·중 정상회담", "트럼프 시진핑")):
        return "us_china_summit"
    if "export control" in lowered or "수출통제" in title:
        return "export_controls"
    if "semiconductor" in lowered or "반도체" in title:
        return "semiconductor_policy"
    if "opec" in lowered:
        return "opec_meeting"
    if "bank of korea" in lowered or "금통위" in title:
        return "bank_of_korea"
    return fallback or re.sub(r"[^a-z0-9가-힣]+", "_", lowered).strip("_")[:80]


def _article_matches_query_gate(haystack: str, config: dict[str, object]) -> bool:
    required_any = tuple(str(item).lower() for item in config.get("required_any", ()) if str(item))
    if required_any and not any(term in haystack for term in required_any):
        return False
    canonical = str(config.get("canonical", ""))
    if canonical == "export_controls":
        policy_terms = ("export control", "export controls", "export restriction", "export restrictions", "수출통제", "수출 규제", "수출규제")
        market_terms = ("china", "semiconductor", "chip", "ai", "중국", "반도체")
        return any(term in haystack for term in policy_terms) and any(term in haystack for term in market_terms)
    if canonical == "federal_reserve":
        return any(term in haystack for term in ("federal reserve", "fomc", "powell", "fed rate", "rate decision", "inflation", "treasury yield"))
    if canonical == "bank_of_korea":
        return any(term in haystack for term in ("bank of korea", "bok", "금통위", "한국은행", "기준금리", "monetary policy"))
    if canonical == "korea_exports":
        return any(term in haystack for term in ("export", "exports", "trade data", "수출", "무역"))
    if canonical == "us_china_summit":
        return any(term in haystack for term in ("trump xi", "trump-xi", "summit", " 정상회담", "시진핑"))
    return True


def _merge_candidate(existing: dict[str, object], incoming: dict[str, object]) -> None:
    sources = existing.setdefault("sources", [])
    if isinstance(sources, list):
        seen_urls = {str(item.get("url", "")) for item in sources if isinstance(item, dict)}
        for source in incoming.get("sources", []):
            if isinstance(source, dict) and str(source.get("url", "")) not in seen_urls:
                sources.append(source)
    existing["hit_count"] = int(existing.get("hit_count", 0)) + int(incoming.get("hit_count", 0))
    domains = {
        str(source.get("domain", ""))
        for source in existing.get("sources", [])
        if isinstance(source, dict) and source.get("domain")
    }
    existing["source_count"] = len(domains)
    existing["first_seen"] = min(str(existing.get("first_seen", "")), str(incoming.get("first_seen", "")))
    existing["last_seen"] = max(str(existing.get("last_seen", "")), str(incoming.get("last_seen", "")))
    _merge_candidate_date_info(existing, incoming)
    markets = {str(existing.get("market", "")), str(incoming.get("market", ""))}
    existing["market"] = "GLOBAL" if {"US", "KR"}.issubset(markets) else str(existing.get("market") or incoming.get("market"))
    existing["score"] = _floating_keyword_score(
        title=str(existing.get("title", "")),
        axes=tuple(str(axis) for axis in existing.get("axis", []) if str(axis)),
        source_count=int(existing["source_count"]),
        article_count=int(existing["hit_count"]),
        bilingual_match=existing["market"] == "GLOBAL",
    )


def _merge_candidate_date_info(existing: dict[str, object], incoming: dict[str, object]) -> None:
    confidence_rank = {"": 0, "low": 1, "medium": 2, "high": 3}
    existing_confidence = str(existing.get("date_confidence", ""))
    incoming_confidence = str(incoming.get("date_confidence", ""))
    if confidence_rank.get(incoming_confidence, 0) > confidence_rank.get(existing_confidence, 0):
        existing["event_date"] = incoming.get("event_date", "")
        existing["event_end_date"] = incoming.get("event_end_date", "")
        existing["date_confidence"] = incoming_confidence
    if not existing.get("published_date"):
        existing["published_date"] = incoming.get("published_date", "")


def _floating_keyword_score(
    title: str,
    axes: tuple[str, ...],
    source_count: int,
    article_count: int,
    bilingual_match: bool,
) -> int:
    lowered = title.lower()
    market_axis_bonus = 3 if axes or any(term in lowered for term in MARKET_AXIS_TERMS) else 0
    high_impact_term_bonus = 3 if any(term in lowered or term in title for term in HIGH_IMPACT_TERMS) else 0
    date_detected_bonus = 2 if _contains_date_expression(title) else 0
    bilingual_match_bonus = 2 if bilingual_match else 0
    noise_penalty = 4 if any(term in lowered for term in FLOATING_EVENT_BLOCKLIST) else 0
    stale_penalty = 0
    return (
        (source_count * 3)
        + article_count
        + market_axis_bonus
        + date_detected_bonus
        + high_impact_term_bonus
        + bilingual_match_bonus
        - stale_penalty
        - noise_penalty
    )


def _contains_date_expression(text: str) -> bool:
    return bool(re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{1,2}월|\d{4}-\d{2}-\d{2})\b", text, re.IGNORECASE))


def _infer_candidate_date(title: str, description: str, canonical_key: str, published_date: str) -> dict[str, str]:
    text = f"{title} {description}"
    published = _safe_date_fromiso(published_date) or datetime.now(KST).date()
    explicit = _infer_explicit_month_day(text, published.year)
    if explicit and _has_event_date_context(text, canonical_key):
        start, end = explicit
        confidence = "high" if end else "medium"
        return {"event_date": start.isoformat(), "event_end_date": end.isoformat() if end else "", "date_confidence": confidence}
    weekday_date = _infer_weekday_date(text, published)
    if weekday_date and _has_event_date_context(text, canonical_key):
        end_date = weekday_date + timedelta(days=1) if canonical_key == "us_china_summit" else None
        confidence = "high" if canonical_key == "us_china_summit" else "medium"
        return {"event_date": weekday_date.isoformat(), "event_end_date": end_date.isoformat() if end_date else "", "date_confidence": confidence}
    return {"event_date": "", "event_end_date": "", "date_confidence": "low"}


def _infer_explicit_month_day(text: str, default_year: int) -> tuple[date, date | None] | None:
    english_months = "|".join(
        [
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
    )
    match = re.search(rf"\b(?P<month>{english_months})\.?\s+(?P<start>\d{{1,2}})(?:\s*[-–~]\s*(?P<end>\d{{1,2}}))?", text, re.I)
    if match:
        month = _month_number(match.group("month"))
        start = date(default_year, month, int(match.group("start")))
        end = date(default_year, month, int(match.group("end"))) if match.group("end") else None
        return start, end
    korean_match = re.search(r"(?:(?P<month>\d{1,2})월\s*)?(?P<start>\d{1,2})\s*(?:일)?\s*(?:[-–~]\s*(?P<end>\d{1,2})\s*일?)?", text)
    if korean_match and ("월" in korean_match.group(0) or "일" in korean_match.group(0)):
        month = int(korean_match.group("month") or datetime.now(KST).month)
        start = date(default_year, month, int(korean_match.group("start")))
        end = date(default_year, month, int(korean_match.group("end"))) if korean_match.group("end") else None
        return start, end
    return None


def _infer_weekday_date(text: str, published: date) -> date | None:
    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
        "월요일": 0,
        "화요일": 1,
        "수요일": 2,
        "목요일": 3,
        "금요일": 4,
        "토요일": 5,
        "일요일": 6,
    }
    lowered = text.lower()
    if not _has_weekday_event_context(lowered, text):
        return None
    for label, weekday in weekday_map.items():
        if label in lowered or label in text:
            days_ahead = (weekday - published.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7 if any(token in lowered for token in ("next", "ahead", "set to", "to meet")) else 0
            return published + timedelta(days=days_ahead)
    return None


def _has_event_date_context(text: str, canonical_key: str) -> bool:
    lowered = text.lower()
    if canonical_key == "opec_meeting":
        return any(
            token in lowered or token in text
            for token in (
                "opec meeting",
                "opec+ meeting",
                "meeting",
                "scheduled",
                "set for",
                "decision",
                "output decision",
                "production decision",
                "회의",
                "예정",
                "개최",
            )
        )
    if canonical_key in {"us_china_summit", "bank_of_korea", "federal_reserve"}:
        return any(
            token in lowered or token in text
            for token in (
                "summit",
                "meeting",
                "meet",
                "talks",
                "scheduled",
                "set for",
                "to meet",
                "decision",
                "fomc",
                "정상회담",
                "회담",
                "회의",
                "예정",
                "열리는",
                "개최",
            )
        )
    if canonical_key in {"export_controls", "semiconductor_sanctions", "semiconductor_policy", "korea_semiconductor"}:
        return any(
            token in lowered or token in text
            for token in (
                "announce",
                "announced",
                "scheduled",
                "set for",
                "deadline",
                "takes effect",
                "effective",
                "export control",
                "export restriction",
                "sanction",
                "발표",
                "시행",
                "예정",
                "수출통제",
                "수출 규제",
                "제재",
            )
        )
    return True


def _has_weekday_event_context(lowered: str, text: str) -> bool:
    return any(
        token in lowered or token in text
        for token in (
            "to meet",
            "will meet",
            "set to",
            "set for",
            "scheduled",
            "on monday",
            "on tuesday",
            "on wednesday",
            "on thursday",
            "on friday",
            "on saturday",
            "on sunday",
            "this monday",
            "this tuesday",
            "this wednesday",
            "this thursday",
            "this friday",
            "next monday",
            "next tuesday",
            "next wednesday",
            "next thursday",
            "next friday",
            "목요일",
            "월요일",
            "화요일",
            "수요일",
            "금요일",
            "토요일",
            "일요일",
            "열리는",
            "예정",
            "개최",
        )
    )


def _safe_date_fromiso(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _floating_candidates_status(status: str, message: str, candidates: list[object]) -> dict[str, object]:
    return {
        "collection_status": {
            "status": status,
            "generated_at": datetime.now(UTC).isoformat(),
            "source": "newsdata_io",
            "message": message,
        },
        "candidates": candidates,
    }


def _news_collection_enabled() -> bool:
    raw = os.getenv("STOCKAGENT_NEWS_COLLECTION_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _fixed_calendar_collection_enabled() -> bool:
    raw = os.getenv("STOCKAGENT_FIXED_CALENDAR_ENABLED", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _get_macro_dashboard_live(macro_history: dict[str, object] | None = None) -> dict[str, object]:
    history_source = macro_history or build_macro_history()
    history_by_id = _history_series_by_id(history_source, "indicators")
    indicators = [_with_history_fallback(_build_indicator(spec), spec, history_by_id.get(spec.id, [])) for spec in MACRO_SPECS]
    valid = [_attach_macro_history_stats(item, history_by_id.get(str(item["id"]), [])) for item in indicators if item["points"]]
    failed_indicators = [_failed_indicator_item(item) for item in indicators if item.get("error")]
    groups: dict[str, list[dict[str, object]]] = {}
    for item in valid:
        groups.setdefault(str(item["group"]), []).append(item)
    decision = _build_macro_decision(valid)
    ai_summary = _build_macro_ai_summary(decision, valid)

    return {
        "as_of": datetime.now(UTC).isoformat(),
        "decision": decision,
        "ai_summary": ai_summary,
        "score_history": _build_macro_score_history(history_source),
        "groups": groups,
        "failed_count": len(failed_indicators),
        "failed_indicators": failed_indicators,
    }


def _get_sector_dashboard_live(
    market: Literal["US", "KR"] = "US",
    sector_history: dict[str, object] | None = None,
) -> dict[str, object]:
    specs = US_SECTOR_SPECS if market == "US" else KR_SECTOR_SPECS
    benchmark_name = "S&P 500" if market == "US" else "KOSPI"
    history_by_id = _history_series_by_id(sector_history or build_sector_history(), "sectors")
    sectors = [_build_sector(spec, history_by_id.get(spec.id, [])) for spec in specs]
    valid = [item for item in sectors if item["points"]]
    leaders = [item for item in valid if float(item["relative_strength"]) > 0]
    leaders.sort(key=lambda item: float(item["relative_strength"]), reverse=True)
    valid.sort(key=lambda item: float(item["relative_strength"]), reverse=True)
    laggards = sorted(valid, key=lambda item: float(item["relative_strength"]))
    return {
        "market": market,
        "benchmark": benchmark_name,
        "as_of": datetime.now(UTC).isoformat(),
        "leaders": leaders[:5],
        "laggards": laggards[:5],
        "flow_summary": _sector_flow_summary(valid, leaders, laggards),
        "comparison_chart": _sector_comparison_chart(valid, benchmark_name),
        "sectors": valid,
    }


def _live_fallback_enabled() -> bool:
    raw = os.getenv("STOCKAGENT_LIVE_FALLBACK", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def build_macro_history(
    years: int = MACRO_HISTORY_YEARS,
    previous_history: dict[str, object] | None = None,
) -> dict[str, object]:
    indicators = []
    previous_by_id = _history_entry_by_id(previous_history, "indicators")
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
            indicators.append(_history_failure_entry(spec, str(exc), previous_by_id.get(spec.id)))
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


def _history_entry_by_id(history: dict[str, object] | None, key: str) -> dict[str, dict[str, object]]:
    if not isinstance(history, dict):
        return {}
    entries = history.get(key)
    if not isinstance(entries, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_id = entry.get("id")
        if isinstance(entry_id, str):
            result[entry_id] = entry
    return result


def _history_failure_entry(
    spec: IndicatorSpec,
    error: str,
    previous_entry: dict[str, object] | None,
) -> dict[str, object]:
    if isinstance(previous_entry, dict) and isinstance(previous_entry.get("points"), list) and previous_entry["points"]:
        return {
            "id": spec.id,
            "name": spec.name,
            "group": spec.group,
            "kind": spec.kind,
            "unit": spec.unit,
            "error": error,
            "stale": True,
            "stale_reason": "latest_fetch_failed",
            "points": previous_entry["points"],
        }
    return {
        "id": spec.id,
        "name": spec.name,
        "group": spec.group,
        "kind": spec.kind,
        "unit": spec.unit,
        "error": error,
        "points": [],
    }


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
            "error": str(exc),
            "description": spec.description,
            "market_impact": spec.market_impact,
            "points": [],
        }


def _with_history_fallback(
    item: dict[str, object],
    spec: IndicatorSpec,
    history_points: list[dict[str, object]],
) -> dict[str, object]:
    if item.get("points"):
        return item
    if not item.get("error"):
        return item
    fallback_points = [point for point in history_points if _is_number(point.get("value"))]
    if not fallback_points:
        return item
    series = _points_to_series(fallback_points)
    if series.empty:
        return item
    latest = float(series.iloc[-1])
    previous = float(series.iloc[-2]) if len(series) >= 2 else latest
    latest_date = str(series.index[-1].date())
    previous_date = str(series.index[-2].date()) if len(series) >= 2 else latest_date
    change_abs = latest - previous
    change_pct = ((latest / previous) - 1.0) * 100 if previous else 0.0
    fallback = dict(item)
    fallback.update(
        {
            "value": _round_value(latest),
            "change_abs": _round_value(change_abs),
            "change_pct": round(change_pct, 2),
            "latest_date": latest_date,
            "previous_date": previous_date,
            "signal": _classify_signal(spec.kind, change_pct, change_abs),
            "points": _series_to_points(series.tail(260)),
            "stale": True,
            "stale_reason": "latest_fetch_failed",
        }
    )
    return fallback


def _failed_indicator_item(item: dict[str, object]) -> dict[str, object]:
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "latest_date": item.get("latest_date", ""),
        "stale": bool(item.get("stale")),
        "error": item.get("error", ""),
    }


def _build_macro_score_history(macro_history: dict[str, object]) -> list[dict[str, object]]:
    history_by_id = _history_series_by_id(macro_history, "indicators")
    series_by_id = {
        item_id: _points_to_series(points)
        for item_id, points in history_by_id.items()
        if points
    }
    dates = sorted({date for series in series_by_id.values() for date in series.index})
    if not dates:
        return []
    history_cutoff = dates[-1] - pd.DateOffset(years=MACRO_HISTORY_YEARS)
    series_by_id = {item_id: series.loc[series.index >= history_cutoff] for item_id, series in series_by_id.items()}
    dates = sorted({date for series in series_by_id.values() for date in series.index})
    if not dates:
        return []
    dates = _macro_score_history_dates(dates)

    specs_by_id = {spec.id: spec for spec in MACRO_SPECS}
    score_points: list[dict[str, object]] = []
    for date in dates:
        scored_by_id: dict[str, dict[str, object]] = {}
        for item_id, series in series_by_id.items():
            spec = specs_by_id.get(item_id)
            if spec is None:
                continue
            as_of_series = series.loc[:date]
            if as_of_series.empty:
                continue
            latest = float(as_of_series.iloc[-1])
            percentile = _percentile_rank([float(value) for value in as_of_series if _is_number(value)], latest)
            scored_by_id[item_id] = _standardized_macro_series_score(spec, as_of_series, percentile)
        if not scored_by_id:
            continue
        score, negative_count = _macro_score_from_standardized_scores(scored_by_id)
        regime_label, _, _, _ = _decision_labels(score, negative_count)
        score_points.append(
            {
                "date": str(date.date()),
                "score": score,
                "regime_label": regime_label,
                "indicator_count": len(scored_by_id),
            }
        )
    return score_points


def _standardized_macro_series_score(spec: IndicatorSpec, series: pd.Series, percentile: float) -> dict[str, object]:
    use_level_change = spec.id in MACRO_LEVEL_SERIES
    direction = _macro_score_direction({"id": spec.id, "kind": spec.kind})
    window_scores: list[float] = []
    if len(series) >= 3 and direction:
        step_changes = series.diff().dropna() if use_level_change else series.pct_change().dropna() * 100
        volatility = float(step_changes.tail(252).std()) if len(step_changes) >= 2 else 0.0
        if volatility > 0:
            for days, weight in MACRO_SCORE_WINDOWS:
                if len(series) <= days:
                    continue
                current = float(series.iloc[-1])
                base = float(series.iloc[-(days + 1)])
                raw_change = current - base if use_level_change else _return_between(base, current)
                normalized = raw_change / (volatility * math.sqrt(days))
                oriented = _clamp(normalized * direction, -3.0, 3.0)
                window_scores.append(math.tanh(oriented / 1.25) * weight)
    denominator = sum(weight for days, weight in MACRO_SCORE_WINDOWS if len(series) > days)
    momentum_score = sum(window_scores) / denominator if window_scores and denominator else 0.0
    level_score = _macro_level_score_from_percentile(spec, percentile)
    final_score = _clamp((momentum_score * 0.80) + (level_score * 0.20), -1.0, 1.0)
    return {"id": spec.id, "name": spec.name, "score": final_score}


def _macro_level_score_from_percentile(spec: IndicatorSpec, percentile: float) -> float:
    direction = _macro_score_direction({"id": spec.id, "kind": spec.kind})
    if not direction:
        return 0.0
    centered = ((percentile - 50.0) / 50.0) * direction
    return _clamp(centered, -1.0, 1.0)


def _macro_score_from_standardized_scores(scored_by_id: dict[str, dict[str, object]]) -> tuple[int, int]:
    score = 50.0
    negative_count = 0
    for factor_id in MACRO_FACTOR_ORDER:
        config = MACRO_FACTOR_BUCKETS[factor_id]
        bucket_ids = config["indicators"]
        bucket_scores = [
            scored
            for item_id, scored in scored_by_id.items()
            if item_id in bucket_ids and _is_number(scored.get("score"))
        ]
        if not bucket_scores:
            continue
        factor_value = sum(float(item["score"]) for item in bucket_scores) / len(bucket_scores)
        factor_value = _clamp(factor_value, -1.0, 1.0)
        points = factor_value * float(config["weight"])
        score += points
        if points < 0:
            negative_count += 1
    return max(0, min(100, round(score))), negative_count


def _macro_score_history_dates(dates: list[pd.Timestamp]) -> list[pd.Timestamp]:
    return dates


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
    score = 50.0
    positive: list[tuple[float, str]] = []
    negative: list[tuple[float, str]] = []
    factor_scores: list[dict[str, object]] = []
    scored_by_id = {str(item["id"]): _standardized_macro_indicator_score(item) for item in indicators}

    for factor_id in MACRO_FACTOR_ORDER:
        config = MACRO_FACTOR_BUCKETS[factor_id]
        bucket_ids = config["indicators"]
        bucket_scores = [
            scored
            for item_id, scored in scored_by_id.items()
            if item_id in bucket_ids and _is_number(scored.get("score"))
        ]
        if not bucket_scores:
            continue
        factor_value = sum(float(item["score"]) for item in bucket_scores) / len(bucket_scores)
        factor_value = _clamp(factor_value, -1.0, 1.0)
        weight = float(config["weight"])
        points = factor_value * weight
        score += points
        leaders = sorted(bucket_scores, key=lambda item: abs(float(item["score"])), reverse=True)[:2]
        note = _factor_decision_note(str(config["label"]), factor_value, leaders)
        factor_scores.append(
            {
                "id": factor_id,
                "label": config["label"],
                "score": round(factor_value, 2),
                "points": round(points, 1),
                "leaders": leaders,
            }
        )
        if points > 0:
            positive.append((points, note))
        elif points < 0:
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
        "positive_factors": _factor_explanation_items(factor_scores, positive_only=True),
        "negative_factors": _factor_explanation_items(factor_scores, positive_only=False),
        "factor_scores": factor_scores,
        "score_model": "standardized_factor_v2",
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


def _standardized_macro_indicator_score(item: dict[str, object]) -> dict[str, object]:
    series = _points_to_series(item.get("points"))
    item_id = str(item.get("id", ""))
    use_level_change = item_id in MACRO_LEVEL_SERIES
    direction = _macro_score_direction(item)
    window_scores: list[float] = []
    window_details: list[dict[str, object]] = []

    if len(series) >= 3 and direction:
        step_changes = series.diff().dropna() if use_level_change else series.pct_change().dropna() * 100
        volatility = float(step_changes.tail(252).std()) if len(step_changes) >= 2 else 0.0
        if volatility > 0:
            for days, weight in MACRO_SCORE_WINDOWS:
                if len(series) <= days:
                    continue
                current = float(series.iloc[-1])
                base = float(series.iloc[-(days + 1)])
                raw_change = current - base if use_level_change else _return_between(base, current)
                normalized = raw_change / (volatility * math.sqrt(days))
                oriented = _clamp(normalized * direction, -3.0, 3.0)
                scaled = math.tanh(oriented / 1.25)
                window_scores.append(scaled * weight)
                window_details.append(
                    {
                        "days": days,
                        "change": round(raw_change, 3),
                        "z_score": round(oriented, 2),
                    }
                )

    momentum_score = sum(window_scores) / sum(weight for days, weight in MACRO_SCORE_WINDOWS if len(series) > days) if window_scores else 0.0
    level_score = _history_level_score(item)
    final_score = _clamp((momentum_score * 0.80) + (level_score * 0.20), -1.0, 1.0)
    return {
        "id": item_id,
        "name": item.get("name", item_id),
        "score": final_score,
        "momentum_score": round(momentum_score, 2),
        "level_score": round(level_score, 2),
        "windows": window_details,
    }


def _points_to_series(points: object) -> pd.Series:
    if not isinstance(points, list):
        return pd.Series(dtype=float)
    dates = []
    values = []
    for point in points:
        if not isinstance(point, dict) or not _is_number(point.get("value")):
            continue
        dates.append(point.get("date"))
        values.append(float(point["value"]))
    if not values:
        return pd.Series(dtype=float)
    parsed_dates = pd.to_datetime(dates, errors="coerce")
    series = pd.Series(values, index=parsed_dates)
    series = series.loc[~pd.isna(series.index)]
    return _clean_series(series)


def _macro_score_direction(item: dict[str, object]) -> float:
    item_id = str(item.get("id", ""))
    if item_id in MACRO_CUSTOM_DIRECTIONS:
        return MACRO_CUSTOM_DIRECTIONS[item_id]
    kind = str(item.get("kind", "neutral"))
    if kind == "risk_on":
        return 1.0
    if kind == "risk_off":
        return -1.0
    return 0.0


def _history_level_score(item: dict[str, object]) -> float:
    stats = item.get("history_stats")
    if not isinstance(stats, dict) or not _is_number(stats.get("percentile")):
        return 0.0
    direction = _macro_score_direction(item)
    if not direction:
        return 0.0
    percentile = float(stats["percentile"])
    centered = ((percentile - 50.0) / 50.0) * direction
    return _clamp(centered, -1.0, 1.0)


def _factor_decision_note(label: str, factor_value: float, leaders: list[dict[str, object]]) -> str:
    leader_text = ", ".join(f"{item['name']} {float(item['score']):+.2f}" for item in leaders)
    if not leader_text:
        leader_text = "유효 지표 부족"
    if factor_value > 0:
        return f"{label} 개선 · {leader_text}"
    return f"{label} 부담 · {leader_text}"


def _factor_explanation_items(factor_scores: list[dict[str, object]], positive_only: bool) -> list[dict[str, str]]:
    candidates = [
        item
        for item in factor_scores
        if _is_number(item.get("points")) and ((float(item["points"]) > 0) if positive_only else (float(item["points"]) < 0))
    ]
    candidates.sort(key=lambda item: abs(float(item["points"])), reverse=True)
    return [
        {
            "label": str(item.get("label", "")),
            "text": _factor_explanation_text(str(item.get("id", "")), positive_only),
        }
        for item in candidates[:4]
    ]


def _factor_explanation_text(factor_id: str, positive: bool) -> str:
    explanations = {
        ("equity_momentum", True): "주요 지수와 성장주 흐름이 함께 살아 있어 위험자산 선호가 개선된 상태입니다.",
        ("equity_momentum", False): "주요 지수와 성장주 흐름이 약해져 시장을 넓게 추격하기 어렵습니다.",
        ("credit", True): "하이일드 시장 스트레스가 제한적이라 위험자산을 버티는 힘이 남아 있습니다.",
        ("credit", False): "신용시장이 흔들리면 주식시장도 빠르게 방어적으로 바뀔 수 있습니다.",
        ("volatility", True): "변동성이 안정되며 단기 공포는 줄어든 상태입니다.",
        ("volatility", False): "변동성이 높아져 단기 급락과 흔들림을 경계해야 합니다.",
        ("rates", True): "금리와 정책 부담이 완화되면 성장주와 위험자산에 숨통이 트입니다.",
        ("rates", False): "금리와 정책 부담이 남아 있어 성장주 무리한 추격은 조심해야 합니다.",
        ("fx_liquidity", True): "달러와 유동성 흐름이 위험자산에 비교적 우호적입니다.",
        ("fx_liquidity", False): "달러 강세나 유동성 부담이 커지면 해외 위험자산과 원화자산에 부담이 됩니다.",
        ("inflation_growth", True): "물가와 성장 관련 지표가 시장 부담을 크게 키우지 않는 상태입니다.",
        ("inflation_growth", False): "물가나 경기 부담이 커지면 주식 비중 확대의 질이 떨어질 수 있습니다.",
    }
    return explanations.get((factor_id, positive), "시장 판단에 영향을 주는 조건입니다.")


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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
            "summary": "숫자를 쓰지 않는 2문장 이내 시장 상황과 대응 방향",
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
    factor_scores = decision.get("factor_scores")
    positive: list[str] = []
    negative: list[str] = []
    if isinstance(factor_scores, list):
        for item in factor_scores:
            if not isinstance(item, dict) or not _is_number(item.get("points")):
                continue
            label = str(item.get("label", "")).strip()
            if not label:
                continue
            points = float(item["points"])
            if points > 0:
                positive.append(label)
            elif points < 0:
                negative.append(label)
    support_text = _natural_join(positive[:2]) if positive else "뚜렷한 우호 축"
    risk_text = _natural_join(negative[:2]) if negative else "뚜렷한 부담 축"
    return {
        "headline": str(decision["action_title"]),
        "summary": (
            f"우호적인 축은 {support_text}이고, 부담 요인은 {risk_text}입니다. "
            "지수 전체를 추격하기보다 강한 섹터와 주도주 중심으로 좁게 접근하는 편이 낫습니다."
        ),
        "stance": str(decision["posture"]),
        "watch_points": list(decision.get("confirm_conditions") or [])[:3],
        "source": "fallback",
    }


def _natural_join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return "과 ".join(items)


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
    chart_points = _sector_chart_points(history_points or [], frame)
    return {
        "id": spec.id,
        "name": spec.name,
        "market": spec.market,
        "benchmark": spec.benchmark,
        "tracked_index": _sector_tracked_index_label(spec),
        "latest_date": str(frame.index[-1].date()),
        "sector_return_20d": round(sector_return_20d, 2),
        "benchmark_return_20d": round(benchmark_return_20d, 2),
        "relative_strength": round(relative_strength, 2),
        "trend_label": trend_label,
        "description": spec.description,
        "market_impact": spec.market_impact,
        "history_stats": _sector_history_stats(history_points or [], relative_strength),
        "points": chart_points,
    }


def _sector_chart_points(history_points: list[dict[str, object]], fallback_frame: pd.DataFrame) -> list[dict[str, object]]:
    points = [
        {
            "date": str(point["date"]),
            "sector": round(float(point["sector"]), 2),
            "benchmark": round(float(point["benchmark"]), 2),
        }
        for point in history_points
        if isinstance(point.get("date"), str) and _is_number(point.get("sector")) and _is_number(point.get("benchmark"))
    ]
    if points:
        return points[-1260:]
    return [
        {
            "date": str(index.date()),
            "sector": round(float(row["sector"]), 2),
            "benchmark": round(float(row["benchmark"]), 2),
        }
        for index, row in fallback_frame.tail(126).iterrows()
    ]


def _sector_tracked_index_label(spec: SectorSpec) -> str:
    symbol = spec.display_symbol or ", ".join(spec.symbols)
    return f"{symbol} · 추종지수: {spec.tracked_index}"


def _sector_comparison_chart(sectors: list[dict[str, object]], benchmark_label: str) -> dict[str, object]:
    date_set: set[str] = set()
    benchmark_by_date: dict[str, float] = {}
    sector_maps: list[tuple[str, str, dict[str, float]]] = []
    for item in sectors:
        points = item.get("points")
        if not isinstance(points, list):
            continue
        values: dict[str, float] = {}
        for point in points:
            if not isinstance(point, dict):
                continue
            date = point.get("date")
            sector_value = point.get("sector")
            benchmark_value = point.get("benchmark")
            if not isinstance(date, str):
                continue
            if _is_number(sector_value):
                values[date] = round(float(sector_value), 2)
                date_set.add(date)
            if _is_number(benchmark_value):
                benchmark_by_date[date] = round(float(benchmark_value), 2)
                date_set.add(date)
        if values:
            sector_maps.append((str(item.get("id", "")), str(item.get("name", "")), values))

    dates = sorted(date_set)[-1260:]
    series = [
        {
            "id": "benchmark",
            "label": benchmark_label,
            "values": [benchmark_by_date.get(date) for date in dates],
        }
    ]
    series.extend(
        {
            "id": sector_id,
            "label": label,
            "values": [values.get(date) for date in dates],
        }
        for sector_id, label, values in sector_maps
    )
    return {"dates": dates, "series": series}


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
        "tracked_index": _sector_tracked_index_label(spec),
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
        return _filter_series_period(_fetch_fred_series(spec.symbol, spec.fred_transform), period)
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
    response = requests.get(url, timeout=FRED_TIMEOUT_SECONDS)
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


def _filter_series_period(series: pd.Series, period: str) -> pd.Series:
    clean = _clean_series(series)
    if clean.empty or not period.endswith("y"):
        return clean
    try:
        years = int(period[:-1])
    except ValueError:
        return clean
    cutoff = clean.index.max() - pd.DateOffset(years=years)
    return clean.loc[clean.index >= cutoff]


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
