from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.chart_agent import analyze_chart
from app.agents.final_agent import analyze_final_decision
from app.agents.llm_client import LLMClient
from app.agents.news_agent import analyze_news
from app.chart.features import build_chart_features
from app.config import AppConfig
from app.data.market_briefing import build_market_briefing
from app.data.market_data import fetch_company_names, fetch_price_history
from app.data.news_data import fetch_latest_news
from app.data.universe import resolve_scan_universe
from app.data.watchlist import load_watchlist, save_watchlist, update_watchlist_from_run
from app.models.enums import ActionLabel, CandidateStatus, HoldingStatus
from app.models.schemas import CandidateBrief, EvaluatedStock, HoldingBrief, MarketRunSection, RejectedStock, RejectionSummary, RunResult
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
        stocks = stocks[:max_stocks]
    company_names = fetch_company_names(stocks)
    stocks = [stock.model_copy(update={"name": company_names.get(stock.ticker, stock.name)}) for stock in stocks]
    candidates: list[EvaluatedStock] = []
    non_candidates: list[EvaluatedStock] = []
    screened_out: list[RejectedStock] = []

    for stock in stocks:
        try:
            history = fetch_price_history(stock)
            passed, reason = screen_stock(history, config.min_price, config.min_avg_volume)
            if not passed:
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
        rejected = [item for item in screened_out if item.market == market and not item.in_holdings]
        rejection_summary = _summarize_rejections(rejected)
        no_candidate_reason = _build_no_candidate_reason(market_candidates, observe_candidates, rejection_summary)

        sections.append(
            MarketRunSection(
                market=market,
                title=title,
                market_briefing=build_market_briefing(market, run_at, config.max_news_age_hours),
                holdings=[_to_holding_brief(stock) for stock in holdings],
                candidate_briefs=[_to_candidate_brief(stock, CandidateStatus.BUY) for stock in new_candidates],
                observe_briefs=[_to_candidate_brief(stock, CandidateStatus.WATCH) for stock in observe_candidates[:3]],
                rejection_summary=rejection_summary,
                no_candidate_reason=no_candidate_reason,
            )
        )
    return sections


def _to_holding_brief(stock: EvaluatedStock) -> HoldingBrief:
    score = stock.final_analysis.final_score
    if score >= 75:
        status = HoldingStatus.KEEP
    elif score >= 65:
        status = HoldingStatus.POSITIVE_WATCH
    elif score >= 55:
        status = HoldingStatus.CAUTION
    elif score >= 45:
        status = HoldingStatus.REDUCE
    else:
        status = HoldingStatus.REVIEW
    return HoldingBrief(
        ticker=stock.ticker,
        name=stock.name,
        market=stock.market,
        status_label=status,
        one_line_summary=stock.final_analysis.summary_reason,
        key_points=_limit_points(stock.chart_analysis.positive_signals + [stock.news_analysis.headline_summary], 4),
        risks=_limit_points(stock.final_analysis.main_risks, 3),
        check_points=_limit_points(stock.final_analysis.what_to_confirm_next + [stock.chart_analysis.invalid_if], 3),
    )


def _to_candidate_brief(stock: EvaluatedStock, status: CandidateStatus) -> CandidateBrief:
    return CandidateBrief(
        ticker=stock.ticker,
        name=stock.name,
        market=stock.market,
        status_label=status,
        why_now=stock.final_analysis.summary_reason,
        entry_logic=_limit_points(stock.chart_analysis.positive_signals + [stock.chart_analysis.why_now], 3),
        risks=_limit_points(stock.final_analysis.main_risks, 3),
        confirm_conditions=_limit_points(stock.final_analysis.what_to_confirm_next + [stock.chart_analysis.invalid_if], 3),
    )


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
