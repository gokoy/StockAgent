from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ActionLabel, CandidateStatus, ChartLabel, ConfidenceLabel, HoldingStatus


class UniverseStock(BaseModel):
    ticker: str
    name: str
    market: str = "US"
    source: str = "manual"
    in_watchlist: bool = False
    in_holdings: bool = False


class PriceHistory(BaseModel):
    ticker: str
    name: str
    rows: list[dict[str, Any]]


class ChartFeatures(BaseModel):
    ma20: float
    ma60: float
    ma120: float
    above_ma20: bool
    above_ma60: bool
    above_ma120: bool
    distance_from_20d_high_pct: float
    distance_from_60d_high_pct: float
    volume_ratio_20d: float
    atr_pct: float
    volatility_contracting: bool
    breakout_setup: bool
    pullback_setup: bool
    range_bound: bool
    overextended_pct: float
    recent_sharp_runup: bool
    support_level_hint: str


class ChartAnalysis(BaseModel):
    chart_score: int = Field(ge=0, le=100)
    label: ChartLabel
    positive_signals: list[str]
    negative_signals: list[str]
    why_now: str
    why_not_now: str
    invalid_if: str
    confidence: ConfidenceLabel


class NewsItem(BaseModel):
    headline: str
    summary: str
    published_at: datetime
    source: str
    url: str


class NewsAnalysis(BaseModel):
    news_score: int = Field(ge=0, le=100)
    bullish_points: list[str]
    bearish_points: list[str]
    uncertainties: list[str]
    headline_summary: str
    event_risk: str


class FinalAnalysis(BaseModel):
    final_score: int = Field(ge=0, le=100)
    action_label: ActionLabel
    summary_reason: str
    main_risks: list[str]
    what_to_confirm_next: list[str]


class EvaluatedStock(BaseModel):
    ticker: str
    name: str
    market: str = "US"
    source: str = "manual"
    in_watchlist: bool = False
    in_holdings: bool = False
    chart_features: ChartFeatures
    chart_analysis: ChartAnalysis
    news_analysis: NewsAnalysis
    final_analysis: FinalAnalysis


class RejectedStock(BaseModel):
    ticker: str
    name: str
    market: str = "US"
    source: str = "manual"
    in_holdings: bool = False
    reason: str


class HoldingInput(BaseModel):
    ticker: str
    market: str | None = None


class HoldingsInput(BaseModel):
    kr: list[HoldingInput] = Field(default_factory=list)
    us: list[HoldingInput] = Field(default_factory=list)


class MarketIndexSnapshot(BaseModel):
    label: str
    symbol: str
    close: float
    change_pct: float


class MacroSnapshot(BaseModel):
    label: str
    symbol: str
    value: float
    change_pct: float


class MarketHeadline(BaseModel):
    headline: str
    summary: str
    why_it_matters: str
    source: str
    published_at: datetime


class MarketBriefing(BaseModel):
    market: str
    title: str
    market_summary: str
    index_snapshots: list[MarketIndexSnapshot] = Field(default_factory=list)
    macro_snapshots: list[MacroSnapshot] = Field(default_factory=list)
    flow_summary: list[str] = Field(default_factory=list)
    strong_sectors: list[str] = Field(default_factory=list)
    weak_sectors: list[str] = Field(default_factory=list)
    key_events: list[str] = Field(default_factory=list)
    key_headlines: list[MarketHeadline] = Field(default_factory=list)
    sector_strength_details: list[dict] = Field(default_factory=list)


class HoldingBrief(BaseModel):
    ticker: str
    name: str
    market: str
    short_term_status_label: HoldingStatus
    mid_term_status_label: HoldingStatus
    short_term_summary: str
    mid_term_summary: str
    key_points: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    check_points: list[str] = Field(default_factory=list)


class CandidateBrief(BaseModel):
    ticker: str
    name: str
    market: str
    horizon: str
    score: int
    status_label: CandidateStatus
    rationale_points: list[str] = Field(default_factory=list)
    entry_logic: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    confirm_conditions: list[str] = Field(default_factory=list)


class RejectionSummary(BaseModel):
    reason: str
    count: int


class MarketRunSection(BaseModel):
    market: str
    title: str
    market_briefing: MarketBriefing
    macro_analysis: MarketRegimeAnalysis | None = None
    holdings: list[HoldingBrief] = Field(default_factory=list)
    short_term_candidate_briefs: list[CandidateBrief] = Field(default_factory=list)
    mid_term_candidate_briefs: list[CandidateBrief] = Field(default_factory=list)
    candidate_briefs: list[CandidateBrief] = Field(default_factory=list)
    observe_briefs: list[CandidateBrief] = Field(default_factory=list)
    rejection_summary: list[RejectionSummary] = Field(default_factory=list)
    no_candidate_reason: list[str] = Field(default_factory=list)


class RunResult(BaseModel):
    run_at: datetime
    candidate_count: int
    candidates: list[EvaluatedStock]
    non_candidates: list[EvaluatedStock]
    screened_out: list[RejectedStock] = Field(default_factory=list)
    market_sections: list[MarketRunSection] = Field(default_factory=list)


class WatchlistEntry(BaseModel):
    ticker: str
    name: str
    market: str = "US"
    source: str = "watchlist"
    added_at: datetime
    last_seen_at: datetime
    last_action: str = "observe"
    last_final_score: int | None = None
    active: bool = True
    consecutive_weak_runs: int = 0
    note: str = ""


class WatchlistState(BaseModel):
    updated_at: datetime
    entries: list[WatchlistEntry] = Field(default_factory=list)


class MarketRegimeAnalysis(BaseModel):
    market_regime: str = ""
    macro_score: int = 0
    market_summary: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    recommended_posture: str = ""
