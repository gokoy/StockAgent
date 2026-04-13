from __future__ import annotations

from html import escape

from app.models.enums import CandidateStatus, HoldingStatus
from app.models.schemas import CandidateBrief, HoldingBrief, MarketBriefing, MarketRunSection, RunResult


def format_telegram_message(run_result: RunResult) -> str:
    date_str = run_result.run_at.strftime("%Y-%m-%d 데일리 브리핑")
    lines = [f"<b>📬 [{escape(date_str)}]</b>", ""]
    for section in run_result.market_sections:
        lines.extend(_format_market_section_html(section))
        lines.append("")
    return "\n".join(lines).strip()


def format_telegram_messages_by_market(run_result: RunResult) -> list[str]:
    date_str = run_result.run_at.strftime("%Y-%m-%d 데일리 브리핑")
    messages: list[str] = []
    for section in run_result.market_sections:
        lines = [f"<b>📬 [{escape(date_str)}]</b>", ""]
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
        "<b>🧭 시장 메모</b>",
        *[escape(line) for line in _market_lines_telegram(section)],
        "",
        "<b>📦 보유 종목</b>",
    ]
    if section.holdings:
        for item in section.holdings:
            lines.extend(_format_holding_html(item))
            lines.append("")
    else:
        lines.append("• 보유 종목 없음 (`holdings.json` 비어 있음 또는 미설정)")
        lines.append("")

    lines.append("<b>⚡ 단기 추천 종목</b>")
    if section.short_term_candidate_briefs:
        for item in section.short_term_candidate_briefs[:5]:
            lines.extend(_format_candidate_html(item))
            lines.append("")
        if section.short_term_portfolio_guidance:
            lines.extend(_format_portfolio_guidance_html(section.short_term_portfolio_guidance))
            lines.append("")
    else:
        lines.append("• 단기 추천 종목 없음")
        for reason in section.no_candidate_reason:
            lines.append(f"• {escape(_truncate(reason, 110))}")
        lines.append("")

    lines.append("<b>🏗️ 중기 추천 종목</b>")
    if section.mid_term_candidate_briefs:
        for item in section.mid_term_candidate_briefs[:5]:
            lines.extend(_format_candidate_html(item))
            lines.append("")
        if section.mid_term_portfolio_guidance:
            lines.extend(_format_portfolio_guidance_html(section.mid_term_portfolio_guidance))
    else:
        lines.append("• 중기 추천 종목 없음")
        for reason in section.no_candidate_reason:
            lines.append(f"• {escape(_truncate(reason, 110))}")
    return lines


def _format_market_section_text(section: MarketRunSection) -> list[str]:
    lines = [
        "========================",
        f"{_flag_for_market(section.market)} {section.title}",
        "========================",
        "",
        "🧭 시장 메모",
        *_market_lines(section),
        "",
        "📦 보유 종목",
    ]
    if section.holdings:
        for item in section.holdings:
            lines.extend(_format_holding_text(item))
            lines.append("")
    else:
        lines.append("- 보유 종목 없음 (`holdings.json` 비어 있음 또는 미설정)")
        lines.append("")

    lines.append("⚡ 단기 추천 종목")
    if section.short_term_candidate_briefs:
        for item in section.short_term_candidate_briefs[:5]:
            lines.extend(_format_candidate_text(item))
            lines.append("")
        if section.short_term_portfolio_guidance:
            lines.extend(_format_portfolio_guidance_text(section.short_term_portfolio_guidance))
            lines.append("")
    else:
        lines.append("- 단기 추천 종목 없음")
        for reason in section.no_candidate_reason:
            lines.append(f"  - {reason}")
        lines.append("")

    lines.append("🏗️ 중기 추천 종목")
    if section.mid_term_candidate_briefs:
        for item in section.mid_term_candidate_briefs[:5]:
            lines.extend(_format_candidate_text(item))
            lines.append("")
        if section.mid_term_portfolio_guidance:
            lines.extend(_format_portfolio_guidance_text(section.mid_term_portfolio_guidance))
    else:
        lines.append("- 중기 추천 종목 없음")
        for reason in section.no_candidate_reason:
            lines.append(f"  - {reason}")
    return lines


def _market_lines(section: MarketRunSection) -> list[str]:
    briefing = section.market_briefing
    lines = [f"- 요약: {briefing.market_summary}"]
    if section.macro_analysis:
        lines.append(f"- 추천 자세: {section.macro_analysis.recommended_posture}")
        if section.macro_analysis.risk_flags:
            lines.append("- 리스크 플래그:")
            lines.extend(f"  • {flag}" for flag in section.macro_analysis.risk_flags[:4])
    special_lines = _special_market_lines(briefing)
    if special_lines:
        lines.append("- 특이 흐름:")
        lines.extend(f"  • {line}" for line in special_lines)
    else:
        lines.append("- 특이 이벤트 없음: 지수/거시는 일상 범위로 보고 생략했다.")

    if briefing.key_events:
        lines.append("- 주요 이벤트:")
        for event in briefing.key_events:
            lines.append(f"  • {event}")

    if briefing.key_headlines:
        lines.append("- 핵심 뉴스:")
        for item in briefing.key_headlines[:3]:
            lines.append(f"  • {item.headline}")
            lines.append(f"    - 왜 중요한가: {item.why_it_matters}")
    if briefing.sector_strength_details:
        lines.append("- 섹터 강도:")
        for item in briefing.sector_strength_details[:3]:
            lines.append(
                f"  • {item['sector_name']}: 상대강도 {item['sector_relative_strength']:+.2f}, 추세 {item['sector_trend_label']}"
            )
    return lines


def _market_lines_telegram(section: MarketRunSection) -> list[str]:
    briefing = section.market_briefing
    lines = [f"• 요약: {_truncate(briefing.market_summary, 100)}"]
    if section.macro_analysis:
        lines.append(f"• 추천 자세: {_truncate(section.macro_analysis.recommended_posture, 90)}")
        if section.macro_analysis.risk_flags:
            lines.append("• 리스크 플래그")
            lines.extend(f"  - {_truncate(flag, 100)}" for flag in section.macro_analysis.risk_flags[:3])
    special_lines = _special_market_lines(briefing)
    if special_lines:
        lines.append("• 특이 흐름")
        lines.extend(f"  - {_truncate(line, 110)}" for line in special_lines)
    else:
        lines.append("• 특이 이벤트 없음: 지수/거시는 일상 범위로 보고 생략")

    if briefing.key_events:
        lines.append("• 주요 이벤트")
        lines.extend(f"  - {_truncate(event, 110)}" for event in briefing.key_events)

    if briefing.key_headlines:
        lines.append("• 핵심 뉴스")
        for item in briefing.key_headlines[:2]:
            lines.append(f"  - {_truncate(item.headline, 100)}")
            lines.append(f"    · {_truncate(item.why_it_matters, 100)}")
    if briefing.sector_strength_details:
        lines.append("• 섹터 강도")
        for item in briefing.sector_strength_details[:2]:
            lines.append(
                f"  - {item['sector_name']} | 상대강도 {item['sector_relative_strength']:+.2f} | {item['sector_trend_label']}"
            )
    return lines


def _special_market_lines(briefing: MarketBriefing) -> list[str]:
    lines: list[str] = []
    for item in briefing.index_snapshots:
        if abs(item.change_pct) >= 1.0:
            direction = "급등" if item.change_pct > 0 else "급락"
            lines.append(f"{item.label} {item.change_pct:+.2f}% {direction}")
    for item in briefing.macro_snapshots:
        if abs(item.change_pct) >= 1.0:
            direction = "상승" if item.change_pct > 0 else "하락"
            lines.append(f"{item.label} {item.change_pct:+.2f}% {direction}")
    for flow in briefing.flow_summary:
        if "optional 데이터" in flow or "best-effort" in flow:
            continue
        lines.append(flow)
    if briefing.strong_sectors or briefing.weak_sectors:
        strong = ", ".join(briefing.strong_sectors[:3]) or "데이터 부족"
        weak = ", ".join(briefing.weak_sectors[:3]) or "데이터 부족"
        lines.append(f"강한 섹터: {strong} / 약한 섹터: {weak}")
    return lines


def _format_holding_html(item: HoldingBrief) -> list[str]:
    lines = [
        f"<b>• {escape(item.name)} | {escape(item.ticker)}</b>",
        f"  ⏱ 단기: {escape(_holding_status_text(item.short_term_status_label))}",
        f"  🗓 중기: {escape(_holding_status_text(item.mid_term_status_label))}",
        f"  - 단기 판단: {escape(_truncate(item.short_term_summary, 110))}",
        f"  - 중기 판단: {escape(_truncate(item.mid_term_summary, 110))}",
    ]
    if item.key_points:
        lines.append("  - 근거")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.key_points[:4])
    if item.risks:
        lines.append("  - 리스크")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.risks[:3])
    if item.check_points:
        lines.append("  - 체크 포인트")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.check_points[:3])
    return lines


def _format_holding_text(item: HoldingBrief) -> list[str]:
    lines = [
        f"- {item.name} | {item.ticker}",
        f"  ⏱ 단기: {_holding_status_text(item.short_term_status_label)}",
        f"  🗓 중기: {_holding_status_text(item.mid_term_status_label)}",
        f"  - 단기 판단: {item.short_term_summary}",
        f"  - 중기 판단: {item.mid_term_summary}",
    ]
    if item.key_points:
        lines.append("  - 근거")
        lines.extend(f"    • {point}" for point in item.key_points[:4])
    if item.risks:
        lines.append("  - 리스크")
        lines.extend(f"    • {point}" for point in item.risks[:3])
    if item.check_points:
        lines.append("  - 체크 포인트")
        lines.extend(f"    • {point}" for point in item.check_points[:3])
    return lines


def _format_candidate_html(item: CandidateBrief) -> list[str]:
    horizon_emoji = "⚡" if item.horizon == "short" else "🏗️"
    title = f"<b>• {escape(item.name)} | {escape(item.ticker)}</b>"
    if item.sector_name:
        title += f" <i>({escape(item.sector_name)})</i>"
    lines = [
        title,
        f"  {horizon_emoji} 점수: {item.score} | 상태: {escape(_candidate_status_text(item.status_label))}",
    ]
    if item.rationale_points:
        lines.append("  - 왜 지금 보는가")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.rationale_points[:3])
    if item.entry_logic:
        lines.append("  - 진입 논리")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.entry_logic[:3])
    if item.risks:
        lines.append("  - 리스크")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.risks[:3])
    if item.confirm_conditions:
        lines.append("  - 확인 조건")
        lines.extend(f"    • {escape(_truncate(point, 100))}" for point in item.confirm_conditions[:3])
    if item.suggested_weight_pct:
        lines.append(f"  - 제안 비중: {item.suggested_weight_pct}%")
        if item.sizing_reason:
            lines.append(f"    • {escape(_truncate(item.sizing_reason, 100))}")
    return lines


def _format_candidate_text(item: CandidateBrief) -> list[str]:
    horizon_emoji = "⚡" if item.horizon == "short" else "🏗️"
    title = f"- {item.name} | {item.ticker}"
    if item.sector_name:
        title += f" ({item.sector_name})"
    lines = [
        title,
        f"  {horizon_emoji} 점수: {item.score} | 상태: {_candidate_status_text(item.status_label)}",
    ]
    if item.rationale_points:
        lines.append("  - 왜 지금 보는가")
        lines.extend(f"    • {point}" for point in item.rationale_points[:3])
    if item.entry_logic:
        lines.append("  - 진입 논리")
        lines.extend(f"    • {point}" for point in item.entry_logic[:3])
    if item.risks:
        lines.append("  - 리스크")
        lines.extend(f"    • {point}" for point in item.risks[:3])
    if item.confirm_conditions:
        lines.append("  - 확인 조건")
        lines.extend(f"    • {point}" for point in item.confirm_conditions[:3])
    if item.suggested_weight_pct:
        lines.append(f"  - 제안 비중: {item.suggested_weight_pct}%")
        if item.sizing_reason:
            lines.append(f"    • {item.sizing_reason}")
    return lines


def _format_portfolio_guidance_html(guidance) -> list[str]:
    lines = [
        f"<b>🧮 포트폴리오 가이드 ({escape('단기' if guidance.horizon == 'short' else '중기')})</b>",
        f"• 추천 자세: {escape(guidance.stance)}",
        f"• 총 제안 비중: {guidance.total_suggested_weight_pct}% | 후보 수: {guidance.candidate_count} | 단일 최대: {guidance.max_single_position_pct}%",
    ]
    lines.extend(f"• {escape(_truncate(note, 100))}" for note in guidance.notes[:3])
    return lines


def _format_portfolio_guidance_text(guidance) -> list[str]:
    lines = [
        f"🧮 포트폴리오 가이드 ({'단기' if guidance.horizon == 'short' else '중기'})",
        f"- 추천 자세: {guidance.stance}",
        f"- 총 제안 비중: {guidance.total_suggested_weight_pct}% | 후보 수: {guidance.candidate_count} | 단일 최대: {guidance.max_single_position_pct}%",
    ]
    lines.extend(f"- {note}" for note in guidance.notes[:3])
    return lines


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
