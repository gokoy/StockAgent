from __future__ import annotations

from html import escape

from app.models.enums import CandidateStatus, HoldingStatus
from app.models.schemas import CandidateBrief, HoldingBrief, MarketBriefing, MarketRunSection, RunResult


def format_telegram_message(run_result: RunResult) -> str:
    date_str = run_result.run_at.strftime("%Y-%m-%d 데일리 브리핑")
    lines = [f"<b>[{escape(date_str)}]</b>", ""]
    for section in run_result.market_sections:
        lines.extend(_format_market_section_html(section))
        lines.append("")
    return "\n".join(lines).strip()


def format_telegram_messages_by_market(run_result: RunResult) -> list[str]:
    date_str = run_result.run_at.strftime("%Y-%m-%d 데일리 브리핑")
    messages: list[str] = []
    for section in run_result.market_sections:
        lines = [f"<b>[{escape(date_str)}]</b>", ""]
        lines.extend(_format_market_section_html(section))
        messages.append("\n".join(lines).strip())
    return messages


def format_console_report(run_result: RunResult) -> str:
    date_str = run_result.run_at.strftime("%Y-%m-%d %H:%M %Z")
    lines = [f"실행 시각: {date_str}", ""]
    for section in run_result.market_sections:
        lines.extend(_format_market_section_text(section))
        lines.append("")
    return "\n".join(lines).strip()


def _format_market_section_html(section: MarketRunSection) -> list[str]:
    lines = [
        f"<b>{escape(_flag_for_market(section.market))} {escape(section.title)}</b>",
        "",
        "<b>[1] 시장 상황</b>",
        *[escape(line) for line in _market_lines_telegram(section.market_briefing)],
        "",
        "<b>[2] 보유 종목 브리핑</b>",
    ]
    if section.holdings:
        for item in section.holdings[:2]:
            lines.extend(_format_holding_html(item))
            lines.append("")
    else:
        lines.append("보유 종목 없음")
        lines.append("")

    lines.append("<b>[3] 추가 매수 후보</b>")
    if section.candidate_briefs:
        for item in section.candidate_briefs[:2]:
            lines.extend(_format_candidate_html(item))
            lines.append("")
    elif section.observe_briefs:
        for item in section.observe_briefs[:2]:
            lines.extend(_format_candidate_html(item))
            lines.append("")
    else:
        lines.append("오늘은 신규 매수 후보 없음")
        for reason in section.no_candidate_reason[:2]:
            lines.append(f"• {escape(_truncate(reason, 90))}")
    return lines


def _format_market_section_text(section: MarketRunSection) -> list[str]:
    lines = [
        f"========================",
        f"{_flag_for_market(section.market)} {section.title}",
        f"========================",
        "",
        "[1] 시장 상황",
        *_market_lines(section.market_briefing),
        "",
        "[2] 보유 종목 브리핑",
    ]
    if section.holdings:
        for item in section.holdings:
            lines.extend(_format_holding_text(item))
            lines.append("")
    else:
        lines.append("- 보유 종목 없음")
        lines.append("")

    lines.append("[3] 추가 매수 후보")
    if section.candidate_briefs:
        for item in section.candidate_briefs:
            lines.extend(_format_candidate_text(item))
            lines.append("")
    elif section.observe_briefs:
        for item in section.observe_briefs:
            lines.extend(_format_candidate_text(item))
            lines.append("")
    else:
        lines.append("- 오늘은 신규 매수 후보 없음")
        for reason in section.no_candidate_reason[:3]:
            lines.append(f"  근거: {reason}")
    return lines


def _market_lines(briefing: MarketBriefing) -> list[str]:
    index_line = " / ".join(
        f"{item.label} {item.change_pct:+.2f}%"
        for item in briefing.index_snapshots
    ) or "지수 데이터 부족"
    macro_line = " / ".join(
        f"{item.label} {item.change_pct:+.2f}%"
        for item in briefing.macro_snapshots
    ) or "거시 데이터 부족"
    strong_line = ", ".join(briefing.strong_sectors[:2]) or "강한 섹터 데이터 부족"
    weak_line = ", ".join(briefing.weak_sectors[:2]) or "약한 섹터 데이터 부족"

    lines = [
        f"- 요약: {briefing.market_summary}",
        f"- 지수 흐름: {index_line}",
        f"- 거시 흐름: {macro_line}",
    ]
    for flow in briefing.flow_summary[:2]:
        lines.append(f"- 수급/체크: {flow}")
    lines.append(f"- 강한 섹터: {strong_line}")
    lines.append(f"- 약한 섹터: {weak_line}")

    if briefing.key_events:
        lines.append("- 주요 체크 이벤트:")
        for event in briefing.key_events[:3]:
            lines.append(f"  • {event}")

    if briefing.key_headlines:
        lines.append("- 핵심 뉴스:")
        for index, item in enumerate(briefing.key_headlines[:3], start=1):
            lines.append(f"  {index}. {item.headline}")
            lines.append(f"     → {item.why_it_matters}")
    return lines


def _market_lines_telegram(briefing: MarketBriefing) -> list[str]:
    index_line = " / ".join(
        f"{item.label} {item.change_pct:+.2f}%"
        for item in briefing.index_snapshots[:4]
    ) or "지수 데이터 부족"
    macro_line = " / ".join(
        f"{item.label} {item.change_pct:+.2f}%"
        for item in briefing.macro_snapshots[:3]
    ) or "거시 데이터 부족"
    strong_line = ", ".join(briefing.strong_sectors[:2]) or "강한 섹터 데이터 부족"
    weak_line = ", ".join(briefing.weak_sectors[:2]) or "약한 섹터 데이터 부족"

    lines = [
        f"- 요약: {_truncate(briefing.market_summary, 90)}",
        f"- 지수/거시: {_truncate(index_line, 120)} | {_truncate(macro_line, 100)}",
        f"- 강약 섹터: 강함 {strong_line} / 약함 {weak_line}",
    ]

    if briefing.flow_summary:
        lines.append(f"- 체크: {_truncate(briefing.flow_summary[0], 110)}")
    if briefing.key_events:
        lines.append(f"- 주요 이벤트: {_truncate(' / '.join(briefing.key_events[:2]), 120)}")
    if briefing.key_headlines:
        headline = briefing.key_headlines[0]
        lines.append(f"- 핵심 뉴스: {_truncate(headline.headline, 100)}")
        lines.append(f"  → {_truncate(headline.why_it_matters, 100)}")
    return lines


def _format_holding_html(item: HoldingBrief) -> list[str]:
    return [
        f"<b>- {escape(item.name)} | {escape(item.ticker)}</b>",
        f"상태: {escape(_holding_status_text(item.status_label))}",
        f"요약: {escape(_truncate(item.one_line_summary, 110))}",
        f"근거: {escape(_truncate(' / '.join(item.key_points[:2]) or '핵심 근거 부족', 120))}",
        f"리스크: {escape(_truncate(' / '.join(item.risks[:2]) or '주요 리스크 없음', 100))}",
        f"체크: {escape(_truncate(' / '.join(item.check_points[:2]) or '추가 확인 사항 없음', 100))}",
    ]


def _format_holding_text(item: HoldingBrief) -> list[str]:
    return [
        f"- {item.name} | {item.ticker}",
        f"  상태: {_holding_status_text(item.status_label)}",
        f"  요약: {item.one_line_summary}",
        "  근거:",
        *[f"  - {point}" for point in item.key_points[:3]],
        "  리스크:",
        *[f"  - {point}" for point in item.risks[:2]],
        "  체크 포인트:",
        *[f"  - {point}" for point in item.check_points[:2]],
    ]


def _format_candidate_html(item: CandidateBrief) -> list[str]:
    return [
        f"<b>- {escape(item.name)} | {escape(item.ticker)}</b>",
        f"상태: {escape(_candidate_status_text(item.status_label))}",
        f"왜 지금 보는가: {escape(_truncate(item.why_now, 110))}",
        f"진입 논리: {escape(_truncate(' / '.join(item.entry_logic[:2]) or '진입 논리 부족', 120))}",
        f"주의 리스크: {escape(_truncate(' / '.join(item.risks[:2]) or '주요 리스크 없음', 100))}",
        f"확인 조건: {escape(_truncate(' / '.join(item.confirm_conditions[:2]) or '추가 확인 사항 없음', 100))}",
    ]


def _format_candidate_text(item: CandidateBrief) -> list[str]:
    return [
        f"- {item.name} | {item.ticker}",
        f"  상태: {_candidate_status_text(item.status_label)}",
        f"  왜 지금 보는가: {item.why_now}",
        "  진입 논리:",
        *[f"  - {point}" for point in item.entry_logic[:3]],
        "  주의 리스크:",
        *[f"  - {point}" for point in item.risks[:2]],
        "  확인 조건:",
        *[f"  - {point}" for point in item.confirm_conditions[:2]],
    ]


def _holding_status_text(status: HoldingStatus) -> str:
    return {
        HoldingStatus.KEEP: "보유 유지",
        HoldingStatus.POSITIVE_WATCH: "긍정적 관찰",
        HoldingStatus.CAUTION: "경계",
        HoldingStatus.REDUCE: "비중 축소 검토",
        HoldingStatus.REVIEW: "재점검 필요",
    }[status]


def _candidate_status_text(status: CandidateStatus) -> str:
    return {
        CandidateStatus.BUY: "매수 후보",
        CandidateStatus.WATCH: "관찰 후보",
        CandidateStatus.NONE: "후보 없음",
    }[status]


def _flag_for_market(market: str) -> str:
    return "🇰🇷" if market.upper() == "KR" else "🇺🇸"


def _truncate(text: str, limit: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
