from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import ActionLabel, ChartLabel, ConfidenceLabel


class UniverseStock(BaseModel):
    ticker: str
    name: str


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
    chart_features: ChartFeatures
    chart_analysis: ChartAnalysis
    news_analysis: NewsAnalysis
    final_analysis: FinalAnalysis


class RejectedStock(BaseModel):
    ticker: str
    name: str
    reason: str


class RunResult(BaseModel):
    run_at: datetime
    candidate_count: int
    candidates: list[EvaluatedStock]
    non_candidates: list[EvaluatedStock]
    screened_out: list[RejectedStock] = Field(default_factory=list)


class MarketRegimeAnalysis(BaseModel):
    market_regime: str = ""
    macro_score: int = 0
    market_summary: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    recommended_posture: str = ""
