from __future__ import annotations

from app.models.enums import ActionLabel
from app.models.schemas import EvaluatedStock, RunResult


def format_telegram_message(run_result: RunResult) -> str:
    date_str = run_result.run_at.strftime("%Y-%m-%d %H:%M %Z")
    if run_result.candidate_count == 0:
        observe_stocks = [stock for stock in run_result.non_candidates if stock.final_analysis.action_label == ActionLabel.OBSERVE]
        if observe_stocks:
            lines = [f"[{date_str}] 관찰만", "", "조건을 강하게 통과한 후보는 없지만 관찰 대상은 있습니다.", ""]
            for stock in observe_stocks[:3]:
                lines.extend(_format_stock_block(stock))
                lines.append("")
            return "\n".join(lines).strip()
        return f"[{date_str}] 후보 없음\n\n스크리닝과 최종 판단을 통과한 종목이 없습니다."

    lines = [f"[{date_str}] 스윙 스캔", ""]
    for stock in run_result.candidates:
        lines.extend(_format_stock_block(stock))
        lines.append("")
    return "\n".join(lines).strip()


def _format_stock_block(stock: EvaluatedStock) -> list[str]:
    chart_points = stock.chart_analysis.positive_signals[:3] or [stock.chart_analysis.why_now]
    news_points = []
    if stock.news_analysis.headline_summary:
        news_points.append(stock.news_analysis.headline_summary)
    news_points.extend(stock.news_analysis.bullish_points[:1])
    risks = stock.final_analysis.main_risks[:2] or [stock.chart_analysis.why_not_now]
    invalid_line = stock.chart_analysis.invalid_if
    action_label = {
        ActionLabel.CANDIDATE: "후보",
        ActionLabel.OBSERVE: "관찰",
        ActionLabel.AVOID: "제외",
    }.get(stock.final_analysis.action_label, stock.final_analysis.action_label.value)
    return [
        f"{stock.ticker} | {stock.name}",
        f"- 종합 점수: {stock.final_analysis.final_score} | 상태: {action_label}",
        f"- 차트 근거: {' / '.join(chart_points[:3])}",
        f"- 뉴스 요약: {' / '.join(news_points[:2]) if news_points else '최근 뉴스 해석 근거 부족'}",
        f"- 주요 리스크: {' / '.join(risks)}",
        f"- 무효화 기준: {invalid_line}",
    ]


def format_console_summary(run_result: RunResult) -> str:
    label = "candidate" if run_result.candidate_count else "observe"
    return f"run_at={run_result.run_at.isoformat()} candidates={run_result.candidate_count} mode={label}"
