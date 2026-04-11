from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.agents.chart_agent import analyze_chart
from app.agents.final_agent import analyze_final_decision
from app.agents.llm_client import LLMClient
from app.agents.news_agent import analyze_news
from app.chart.features import build_chart_features
from app.config import AppConfig
from app.data.market_data import fetch_company_names, fetch_price_history
from app.data.news_data import fetch_latest_news
from app.data.universe import resolve_scan_universe
from app.data.watchlist import load_watchlist, save_watchlist, update_watchlist_from_run
from app.models.enums import ActionLabel
from app.models.schemas import EvaluatedStock, RejectedStock, RunResult
from app.reporting.formatter import format_telegram_message
from app.reporting.storage import save_run_result
from app.reporting.telegram import send_telegram_message
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
                screened_out.append(RejectedStock(ticker=stock.ticker, name=stock.name, reason=reason))
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
            screened_out.append(RejectedStock(ticker=stock.ticker, name=stock.name, reason=f"error:{exc}"))

    candidates = sorted(candidates, key=lambda item: item.final_analysis.final_score, reverse=True)[: config.top_n_candidates]
    non_candidates = sorted(non_candidates, key=lambda item: item.final_analysis.final_score, reverse=True)
    result = RunResult(
        run_at=run_at,
        candidate_count=len(candidates),
        candidates=candidates,
        non_candidates=non_candidates,
        screened_out=screened_out,
    )
    save_run_result(result, config.output_dir)
    if config.include_watchlist:
        watchlist_state = load_watchlist(config.watchlist_path)
        updated_watchlist = update_watchlist_from_run(watchlist_state, result, config.watchlist_max_weak_runs)
        save_watchlist(updated_watchlist, config.watchlist_path)
    message = format_telegram_message(result)
    if send_telegram:
        try:
            send_telegram_message(message, config)
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
