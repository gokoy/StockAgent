from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.chart_agent import analyze_chart
from app.agents.final_agent import analyze_final_decision
from app.agents.llm_client import LLMClient
from app.agents.macro_agent import analyze_market_regime
from app.agents.news_agent import analyze_news
from app.chart.features import build_chart_features
from app.config import AppConfig
from app.data.market_briefing import build_market_briefing
from app.data.market_data import fetch_company_names, fetch_price_history, fetch_upcoming_earnings_date
from app.data.news_data import fetch_latest_news
from app.data.sector_data import infer_sector_name
from app.data.universe import resolve_scan_universe
from app.data.watchlist import load_watchlist, save_watchlist, update_watchlist_from_run
from app.evaluation.performance import summarize_performance
from app.evaluation.tracker import record_recommendation
from app.models.enums import ActionLabel, CandidateStatus, HoldingStatus
from app.models.schemas import CandidateBrief, EvaluatedStock, HoldingBrief, MarketRunSection, RejectedStock, RejectionSummary, RunResult
from app.portfolio.sizing_stub import suggest_position_size
from app.reporting.formatter import format_console_report, format_telegram_message, format_telegram_messages_by_market
from app.reporting.storage import save_run_result
from app.reporting.telegram import send_telegram_messages
from app.screening.screener import screen_stock


def run_scan(
    config: AppConfig,
    timezone_name: str = "Asia/Seoul",
    send_telegram: bool = True,
    max_stocks: int | None = None,
) -> tuple[RunResult, str]:
    llm_client = _build_llm_client(config)
    run_at = datetime.now(ZoneInfo(timezone_name))
    stocks = resolve_scan_universe(config)
    if max_stocks is not None:
        stocks = _limit_scan_stocks(stocks, max_stocks)
    company_names = fetch_company_names(stocks)
    stocks = [stock.model_copy(update={"name": company_names.get(stock.ticker, stock.name)}) for stock in stocks]
    candidates: list[EvaluatedStock] = []
    non_candidates: list[EvaluatedStock] = []
    screened_out: list[RejectedStock] = []

    for stock in stocks:
        try:
            history = fetch_price_history(stock)
            passed, reason = screen_stock(history, config.min_price_for_market(stock.market), config.min_avg_volume)
            if not passed and not (stock.in_holdings and reason in {"price_below_threshold", "volume_below_threshold"}):
                screened_out.append(
                    RejectedStock(
                        ticker=stock.ticker,
                        name=stock.name,
                        market=stock.market,
                        source=stock.source,
                        in_holdings=stock.in_holdings,
                        reason=reason,
                    )
                )
                continue

            chart_features = build_chart_features(history)
            chart_analysis = analyze_chart(stock.ticker, stock.name, chart_features, llm_client)
            news_items = fetch_latest_news(stock.ticker, stock.name, config.max_news_age_hours)
            news_analysis = analyze_news(stock.ticker, stock.name, news_items, llm_client)
            final_analysis = analyze_final_decision(
                stock.ticker,
                stock.name,
                chart_features,
                chart_analysis,
                news_analysis,
                llm_client,
                config,
            )
            evaluated = EvaluatedStock(
                ticker=stock.ticker,
                name=stock.name,
                market=stock.market,
                source=stock.source,
                in_watchlist=stock.in_watchlist,
                in_holdings=stock.in_holdings,
                chart_features=chart_features,
                chart_analysis=chart_analysis,
                news_analysis=news_analysis,
                final_analysis=final_analysis,
            )
            if final_analysis.action_label == ActionLabel.CANDIDATE:
                candidates.append(evaluated)
            else:
                non_candidates.append(evaluated)
        except Exception as exc:
            screened_out.append(
                RejectedStock(
                    ticker=stock.ticker,
                    name=stock.name,
                    market=stock.market,
                    source=stock.source,
                    in_holdings=stock.in_holdings,
                    reason=f"error:{exc}",
                )
            )

    candidates = sorted(candidates, key=lambda item: item.final_analysis.final_score, reverse=True)[: config.top_n_candidates]
    non_candidates = sorted(non_candidates, key=lambda item: item.final_analysis.final_score, reverse=True)
    result = RunResult(
        run_at=run_at,
        candidate_count=len(candidates),
        candidates=candidates,
        non_candidates=non_candidates,
        screened_out=screened_out,
        market_sections=_build_market_sections(run_at, candidates, non_candidates, screened_out, config),
    )
    save_run_result(result, config.output_dir)
    record_recommendation(result, config.performance_dir)
    summarize_performance(config.performance_dir)
    if config.include_watchlist:
        watchlist_state = load_watchlist(config.watchlist_path)
        updated_watchlist = update_watchlist_from_run(watchlist_state, result, config.watchlist_max_weak_runs)
        save_watchlist(updated_watchlist, config.watchlist_path)
    message = format_telegram_message(result)
    if send_telegram:
        try:
            send_telegram_messages(format_telegram_messages_by_market(result), config)
        except Exception:
            pass
    return result, message


def _build_llm_client(config: AppConfig) -> LLMClient | None:
    if not config.llm_enabled:
        return None
    try:
        return LLMClient(config)
    except Exception:
        return None


def _limit_scan_stocks(stocks: list, max_stocks: int) -> list:
    holdings = [stock for stock in stocks if getattr(stock, "in_holdings", False)]
    others = [stock for stock in stocks if not getattr(stock, "in_holdings", False)]
    if max_stocks <= 0:
        return holdings
    return holdings + others[:max_stocks]


def build_console_output(result: RunResult) -> str:
    return format_console_report(result)


def _build_market_sections(
    run_at: datetime,
    candidates: list[EvaluatedStock],
    non_candidates: list[EvaluatedStock],
    screened_out: list[RejectedStock],
    config: AppConfig,
) -> list[MarketRunSection]:
    sections: list[MarketRunSection] = []
    for market, title in (("KR", "한국 시장"), ("US", "미국 시장")):
        market_candidates = [stock for stock in candidates if stock.market == market]
        market_non_candidates = [stock for stock in non_candidates if stock.market == market]
        holdings = [stock for stock in market_candidates + market_non_candidates if stock.in_holdings]
        new_candidates = [stock for stock in market_candidates if not stock.in_holdings]
        observe_candidates = [
            stock
            for stock in market_non_candidates
            if stock.final_analysis.action_label == ActionLabel.OBSERVE and not stock.in_holdings
        ]
        recommendation_pool = market_candidates + observe_candidates
        rejected = [item for item in screened_out if item.market == market and not item.in_holdings]
        rejection_summary = _summarize_rejections(rejected)
        no_candidate_reason = _build_no_candidate_reason(market_candidates, observe_candidates, rejection_summary)

        market_briefing = build_market_briefing(market, run_at, config.max_news_age_hours)
        macro_analysis = analyze_market_regime(market_briefing)
        sector_biases = _sector_bias_map(market_briefing.sector_strength_details)

        sections.append(
            MarketRunSection(
                market=market,
                title=title,
                market_briefing=market_briefing,
                macro_analysis=macro_analysis,
                holdings=[
                    _to_holding_brief(
                        stock,
                        macro_score=macro_analysis.macro_score,
                        sector_biases=sector_biases,
                    )
                    for stock in holdings
                ],
                short_term_candidate_briefs=_build_horizon_candidate_briefs(
                    recommendation_pool,
                    "short",
                    config,
                    macro_analysis.macro_score,
                    sector_biases,
                ),
                mid_term_candidate_briefs=_build_horizon_candidate_briefs(
                    recommendation_pool,
                    "mid",
                    config,
                    macro_analysis.macro_score,
                    sector_biases,
                ),
                candidate_briefs=[
                    _to_candidate_brief(
                        stock,
                        CandidateStatus.BUY,
                        macro_score=macro_analysis.macro_score,
                        sector_biases=sector_biases,
                    )
                    for stock in new_candidates
                ],
                observe_briefs=[
                    _to_candidate_brief(
                        stock,
                        CandidateStatus.WATCH,
                        macro_score=macro_analysis.macro_score,
                        sector_biases=sector_biases,
                    )
                    for stock in observe_candidates[:3]
                ],
                rejection_summary=rejection_summary,
                no_candidate_reason=no_candidate_reason,
            )
        )
    return sections


def _to_holding_brief(
    stock: EvaluatedStock,
    macro_score: int = 50,
    sector_biases: dict[str, int] | None = None,
) -> HoldingBrief:
    biases = sector_biases or {}
    short_score = _short_term_score(stock, macro_score, biases)
    mid_score = _mid_term_score(stock, macro_score, biases)
    short_status = _holding_status_for_score(short_score)
    mid_status = _holding_status_for_score(mid_score)
    earnings_note = _earnings_event_note(stock.ticker)
    return HoldingBrief(
        ticker=stock.ticker,
        name=stock.name,
        market=stock.market,
        short_term_status_label=short_status,
        mid_term_status_label=mid_status,
        short_term_summary=_holding_summary_for_horizon(stock, "short", short_score),
        mid_term_summary=_holding_summary_for_horizon(stock, "mid", mid_score),
        key_points=_limit_points(stock.chart_analysis.positive_signals + [stock.news_analysis.headline_summary], 4),
        risks=_limit_points(stock.final_analysis.main_risks, 3),
        check_points=_limit_points(stock.final_analysis.what_to_confirm_next + [stock.chart_analysis.invalid_if, earnings_note], 4),
    )


def _to_candidate_brief(
    stock: EvaluatedStock,
    status: CandidateStatus,
    horizon: str = "swing",
    score: int | None = None,
    macro_score: int = 50,
    sector_biases: dict[str, int] | None = None,
) -> CandidateBrief:
    earnings_note = _earnings_event_note(stock.ticker)
    sector_name, sector_score_adjustment, sector_note = _sector_adjustment(stock, sector_biases or {})
    effective_score = score if score is not None else stock.final_analysis.final_score
    sizing = suggest_position_size(
        final_score=effective_score,
        macro_score=macro_score,
        action_label=stock.final_analysis.action_label.value,
        horizon=horizon,
    )
    return CandidateBrief(
        ticker=stock.ticker,
        name=stock.name,
        market=stock.market,
        sector_name=sector_name,
        horizon=horizon,
        score=effective_score,
        status_label=status,
        rationale_points=_limit_points(
            [
                stock.final_analysis.summary_reason,
                stock.chart_analysis.why_now,
                stock.news_analysis.headline_summary,
                sector_note,
                _macro_note(macro_score),
            ],
            3,
        ),
        entry_logic=_limit_points(stock.chart_analysis.positive_signals + [stock.chart_analysis.why_now, sector_note], 3),
        risks=_limit_points(stock.final_analysis.main_risks, 3),
        confirm_conditions=_limit_points(stock.final_analysis.what_to_confirm_next + [stock.chart_analysis.invalid_if, earnings_note], 4),
        suggested_weight_pct=sizing.get("suggested_weight_pct"),
        sizing_reason=_join_non_empty(
            [
                sizing.get("reason", ""),
                f"섹터 보정 {sector_score_adjustment:+d}점 반영" if sector_name and sector_score_adjustment else "",
            ]
        ),
    )


def _build_horizon_candidate_briefs(
    stocks: list[EvaluatedStock],
    horizon: str,
    config: AppConfig,
    macro_score: int,
    sector_biases: dict[str, int],
) -> list[CandidateBrief]:
    scored: list[tuple[int, CandidateBrief]] = []
    for stock in stocks:
        score = (
            _short_term_score(stock, macro_score, sector_biases)
            if horizon == "short"
            else _mid_term_score(stock, macro_score, sector_biases)
        )
        status = _candidate_status_for_score(
            score,
            config.short_term_buy_score if horizon == "short" else config.mid_term_buy_score,
            config.short_term_watch_score if horizon == "short" else config.mid_term_watch_score,
        )
        if stock.final_analysis.action_label != ActionLabel.CANDIDATE and status == CandidateStatus.BUY:
            status = CandidateStatus.WATCH
        if status == CandidateStatus.NONE:
            continue
        scored.append(
            (
                score,
                _to_candidate_brief(
                    stock,
                    status,
                    horizon=horizon,
                    score=score,
                    macro_score=macro_score,
                    sector_biases=sector_biases,
                ),
            )
        )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in scored[: config.top_n_candidates]]


def _summarize_rejections(rejected: list[RejectedStock]) -> list[RejectionSummary]:
    counts: dict[str, int] = {}
    for item in rejected:
        reason = _normalize_rejection_reason(item.reason)
        counts[reason] = counts.get(reason, 0) + 1
    return [RejectionSummary(reason=reason, count=count) for reason, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:5]]


def _build_no_candidate_reason(
    market_candidates: list[EvaluatedStock],
    observe_candidates: list[EvaluatedStock],
    rejection_summary: list[RejectionSummary],
) -> list[str]:
    if market_candidates:
        return []
    reasons = []
    if observe_candidates:
        reasons.append("조건을 일부 만족한 관찰 후보는 있지만 신규 매수 후보로 승격할 정도의 근거는 부족하다.")
    if rejection_summary:
        labels = ", ".join(f"{item.reason} {item.count}개" for item in rejection_summary[:3])
        reasons.append(f"1차 스크리닝 탈락 사유는 {labels} 중심이다.")
    if not reasons:
        reasons.append("시장 전체에서 추세, 거래량, 뉴스 조건을 함께 만족하는 종목이 부족하다.")
    return reasons


def _limit_points(values: list[str], limit: int) -> list[str]:
    items = []
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        if normalized not in items:
            items.append(normalized)
        if len(items) >= limit:
            break
    return items


def _normalize_rejection_reason(reason: str) -> str:
    if reason.startswith("error:"):
        lowered = reason.lower()
        if "could not resolve host" in lowered or "curl" in lowered:
            return "시장 데이터 수집 실패"
        return "분석 중 예외 발생"
    mapping = {
        "insufficient_history": "가격 이력 부족",
        "price_below_threshold": "최소 가격 기준 미달",
        "volume_below_threshold": "최소 거래량 기준 미달",
    }
    return mapping.get(reason, reason)

def _short_term_score(stock: EvaluatedStock, macro_score: int, sector_biases: dict[str, int]) -> int:
    features = stock.chart_features
    score = stock.chart_analysis.chart_score * 0.45 + stock.news_analysis.news_score * 0.2 + stock.final_analysis.final_score * 0.35
    if features.above_ma20:
        score += 4
    if features.volume_ratio_20d >= 1.2:
        score += 5
    if features.distance_from_20d_high_pct >= -3:
        score += 5
    if features.volatility_contracting:
        score += 4
    if features.breakout_setup:
        score += 5
    if features.pullback_setup:
        score += 3
    if features.range_bound:
        score -= 5
    if features.overextended_pct >= 12:
        score -= 8
    if features.recent_sharp_runup:
        score -= 6
    score += _macro_score_adjustment(macro_score, horizon="short")
    score += _sector_adjustment(stock, sector_biases)[1]
    return max(0, min(100, int(round(score))))


def _mid_term_score(stock: EvaluatedStock, macro_score: int, sector_biases: dict[str, int]) -> int:
    features = stock.chart_features
    score = stock.chart_analysis.chart_score * 0.4 + stock.news_analysis.news_score * 0.2 + stock.final_analysis.final_score * 0.4
    if features.above_ma60:
        score += 5
    if features.above_ma120:
        score += 6
    if features.distance_from_60d_high_pct >= -8:
        score += 4
    if features.pullback_setup:
        score += 4
    if features.breakout_setup:
        score += 2
    if features.range_bound:
        score -= 4
    if features.overextended_pct >= 15:
        score -= 5
    if features.recent_sharp_runup:
        score -= 3
    score += _macro_score_adjustment(macro_score, horizon="mid")
    score += _sector_adjustment(stock, sector_biases)[1]
    return max(0, min(100, int(round(score))))


def _holding_status_for_score(score: int) -> HoldingStatus:
    if score >= 75:
        return HoldingStatus.KEEP
    if score >= 65:
        return HoldingStatus.POSITIVE_WATCH
    if score >= 55:
        return HoldingStatus.CAUTION
    if score >= 45:
        return HoldingStatus.REDUCE
    return HoldingStatus.REVIEW


def _candidate_status_for_score(score: int, buy_threshold: int, watch_threshold: int) -> CandidateStatus:
    if score >= buy_threshold:
        return CandidateStatus.BUY
    if score >= watch_threshold:
        return CandidateStatus.WATCH
    return CandidateStatus.NONE


def _holding_summary_for_horizon(stock: EvaluatedStock, horizon: str, score: int) -> str:
    features = stock.chart_features
    if horizon == "short":
        if score >= 75:
            return "한 달 이내 관점에서 모멘텀과 추세가 모두 살아 있어 유지 또는 추가 관찰이 가능한 구간이다."
        if score >= 65:
            return "단기 추세는 남아 있지만 거래량과 고점 돌파 확인이 더 필요하다."
        if score >= 55:
            return "단기 반등 가능성은 있지만 눌림과 변동성 확대에 주의해야 한다."
        if score >= 45:
            return "단기 관점에서는 추세 신뢰도가 약해 비중 조절을 검토할 만하다."
        return "단기 관점에서는 추세와 모멘텀이 모두 약해 재점검이 필요하다."
    if score >= 75:
        return "1개월에서 6개월 관점에서 중기 추세가 유지되고 있어 보유 논리가 비교적 안정적이다."
    if score >= 65:
        return "중기 추세는 아직 살아 있으나 추가 상승 전에 조정이나 재정렬이 나올 수 있다."
    if score >= 55:
        return "중기 관점에서는 방향성은 남아 있지만 확신이 강한 구간은 아니다."
    if score >= 45:
        return "중기 기준 핵심 추세가 약해지고 있어 비중 축소 검토가 가능하다."
    if not features.above_ma120:
        return "중기 기준 장기 이동평균 아래에 머물러 재점검이 필요하다."
    return "중기 기준 보유 논리가 약해져 다시 점검해야 한다."


def _earnings_event_note(ticker: str) -> str:
    earnings_date = fetch_upcoming_earnings_date(ticker)
    if not earnings_date:
        return ""
    return f"예상 실적 발표일 {earnings_date} 전후 변동성 확대 가능성을 확인한다."


def _sector_bias_map(details: list[dict]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for item in details:
        sector_name = str(item.get("sector_name", "")).strip()
        label = str(item.get("sector_trend_label", "")).strip()
        if not sector_name or not label:
            continue
        if label == "strong":
            mapping[sector_name] = 3
        elif label == "weak":
            mapping[sector_name] = -3
        else:
            mapping[sector_name] = 0
    return mapping


def _sector_adjustment(stock: EvaluatedStock, sector_biases: dict[str, int]) -> tuple[str, int, str]:
    sector_name = infer_sector_name(stock.market, stock.ticker)
    if not sector_name:
        return "", 0, ""
    bias = sector_biases.get(sector_name, 0)
    if bias > 0:
        return sector_name, bias, f"{sector_name} 섹터 강도가 우호적이라 추천 점수에 가산했다."
    if bias < 0:
        return sector_name, bias, f"{sector_name} 섹터 강도가 약해 추천 점수에 감산했다."
    return sector_name, 0, f"{sector_name} 섹터 흐름은 중립 수준이다."


def _macro_score_adjustment(macro_score: int, horizon: str) -> int:
    if macro_score >= 70:
        return 4 if horizon == "short" else 5
    if macro_score >= 60:
        return 2 if horizon == "short" else 3
    if macro_score < 40:
        return -5 if horizon == "short" else -6
    if macro_score < 50:
        return -2 if horizon == "short" else -3
    return 0


def _macro_note(macro_score: int) -> str:
    if macro_score >= 65:
        return "시장 국면 점수가 우호적이라 신규 접근 부담이 낮은 편이다."
    if macro_score < 45:
        return "시장 국면 점수가 낮아 신규 접근은 보수적으로 보는 편이 좋다."
    return "시장 국면은 중립 수준이라 종목 단위 선별이 중요하다."


def _join_non_empty(values: list[str]) -> str:
    return " / ".join([value for value in values if value])
