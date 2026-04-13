# AGENT.md

## 목적

이 프로젝트는 개인용 스윙 투자 의사결정 보조 도구다. 자동매매 시스템이 아니며, 정량 계산은 Python이 수행하고 차트/뉴스 해석은 LLM agent가 수행한다. 모든 agent는 서로 직접 대화하지 않고 `orchestrator`가 순차적으로 호출한다.

## 공통 원칙

- 모든 agent 출력은 반드시 structured JSON이어야 한다.
- agent는 입력으로 제공되지 않은 사실을 추정하면 안 된다.
- feature에 없는 사실, 가격 수치, 뉴스 내용, 재무 수치, 시장 맥락을 임의로 만들어내면 안 된다.
- 모호하거나 부족한 정보는 불확실성으로 명시한다.
- 모든 종목은 동일한 출력 포맷을 유지한다.
- 후보가 없을 경우 `후보 없음` 또는 `관찰만`이 가능해야 한다.
- 최신 뉴스만 사용한다.
- 뉴스 source는 기본적으로 `Google News RSS`를 쓰되, 동일 검색 결과 안에서는 `Reuters`를 최우선 source로 다룬다.
- 근거 중심으로만 판단한다.
- 민감정보(`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`)는 agent 입력, 출력, 로그에 포함하지 않는다.
- 종목 universe는 `discovery pool`과 `watchlist`를 분리해 운영할 수 있어야 한다.
- watchlist는 서비스가 유지/제거를 판단하며, 사용자가 매번 종목을 직접 고르지 않아도 된다.
- 최종 출력은 `시장 브리핑 -> 보유 종목 브리핑 -> 신규 후보 브리핑` 순서를 따른다.
- 한국/미국 시장은 분리하되 출력 형식은 최대한 동일하게 유지한다.

## Orchestrator 호출 순서

1. `Discovery Universe` 수집
2. `Watchlist` 로드 및 병합
3. `Screening Engine` 실행
4. `Chart Feature Engine` 계산
5. `Chart Analysis Agent` 호출
6. `Latest News Fetcher` 실행
7. `News Agent` 호출
8. `Final Decision Agent` 호출
9. `Watchlist` 상태 갱신
10. 시장 브리핑 데이터 수집 및 정리
11. JSON 결과 저장
12. Telegram 메시지 포맷팅 및 전송

agent 간 직접 호출, 자유 대화, 멀티턴 협업은 허용하지 않는다.

## 입력 계약

### 1. Chart Analysis Agent

입력은 Python에서 계산된 차트 feature만 사용한다.

필수 입력 필드:

- `ticker`
- `name`
- `ma20`
- `ma60`
- `ma120`
- `above_ma20`
- `above_ma60`
- `above_ma120`
- `distance_from_20d_high_pct`
- `distance_from_60d_high_pct`
- `volume_ratio_20d`
- `atr_pct`
- `volatility_contracting`
- `breakout_setup`
- `pullback_setup`
- `range_bound`
- `overextended_pct`
- `recent_sharp_runup`
- `support_level_hint`

출력 JSON 스키마:

```json
{
  "chart_score": 0,
  "label": "watch",
  "positive_signals": [],
  "negative_signals": [],
  "why_now": "",
  "why_not_now": "",
  "invalid_if": "",
  "confidence": "low"
}
```

제약:

- `positive_signals`, `negative_signals`는 입력 feature 근거만 사용한다.
- `why_now`, `why_not_now`, `invalid_if`는 추상 표현보다 관측 가능한 조건 중심으로 작성한다.
- 점수 범위는 구현 시 `0~100`으로 고정한다.

### 2. News Agent

입력은 최신 뉴스 fetch 결과만 사용한다.

필수 입력 필드:

- `ticker`
- `name`
- `as_of`
- `headlines`
- `summaries`
- `published_at`

출력 JSON 스키마:

```json
{
  "news_score": 0,
  "bullish_points": [],
  "bearish_points": [],
  "uncertainties": [],
  "headline_summary": "",
  "event_risk": ""
}
```

제약:

- 최신 뉴스만 반영한다.
- 뉴스가 없으면 빈 배열/빈 문자열이 아니라 불확실성 또는 커버리지 부족을 명시한다.
- 오래된 뉴스는 필터링 대상이며, agent 판단 근거로 사용하지 않는다.

### 3. Final Decision Agent

입력은 정량 feature, chart agent 결과, news agent 결과를 조합한 단일 payload다.

출력 JSON 스키마:

```json
{
  "final_score": 0,
  "action_label": "observe",
  "summary_reason": "",
  "main_risks": [],
  "what_to_confirm_next": []
}
```

제약:

- 최종 결론은 chart/news 근거를 요약한 결과여야 한다.
- 새로운 사실을 추가 생성하면 안 된다.
- `action_label`은 최소한 `candidate`, `observe`, `avoid` 중 하나로 고정하는 것을 권장한다.
- 후보 없음 케이스를 지원해야 한다.
- 후속 watchlist 운영을 위해 `candidate`는 신규 편입 또는 강한 유지, `observe`는 유지 관찰, `avoid`는 약세 또는 제거 후보로 해석 가능해야 한다.

### 4. Phase 2 Placeholder Agent

`macro_agent.py`는 placeholder를 만들되 아래 JSON 계약을 문서화한다.

```json
{
  "market_regime": "",
  "macro_score": 0,
  "market_summary": "",
  "risk_flags": [],
  "recommended_posture": ""
}
```

## 결과 저장 계약

매 실행마다 JSON 결과를 저장한다.

필수 저장 필드:

- `run_at`
- `candidate_count`
- `ticker`
- `name`
- `chart_features`
- `chart_analysis`
- `news_analysis`
- `final_analysis`

권장 상위 구조:

```json
{
  "run_at": "2026-04-10T23:00:00+09:00",
  "candidate_count": 3,
  "candidates": [
    {
      "ticker": "AAPL",
      "name": "Apple Inc.",
      "chart_features": {},
      "chart_analysis": {},
      "news_analysis": {},
      "final_analysis": {}
    }
  ],
  "non_candidates": []
}
```

watchlist 저장은 아래 구조를 권장한다.

```json
{
  "updated_at": "2026-04-11T08:00:00+09:00",
  "entries": [
    {
      "ticker": "NVDA",
      "name": "NVIDIA",
      "market": "US",
      "source": "watchlist",
      "added_at": "2026-04-08T08:00:00+09:00",
      "last_seen_at": "2026-04-11T08:00:00+09:00",
      "last_action": "observe",
      "active": true,
      "consecutive_weak_runs": 0,
      "note": ""
    }
  ]
}
```

시장별 브리핑 섹션은 아래 구조를 권장한다.

```json
{
  "market": "KR",
  "title": "한국 시장",
  "market_briefing": {},
  "holdings": [],
  "candidate_briefs": [],
  "observe_briefs": [],
  "rejection_summary": [],
  "no_candidate_reason": []
}
```

## Telegram 출력 계약

메시지에는 아래 정보를 포함한다.

- 날짜
- 한국 시장 섹션
- 미국 시장 섹션
- 각 시장별 `시장 상황`
- 각 시장별 `보유 종목 브리핑`
- 각 시장별 `추가 매수 후보 브리핑`
- 후보가 없을 경우 `오늘은 신규 매수 후보 없음`과 그 이유

모든 종목 표시 순서는 동일해야 한다.

## 후보 없음 규칙

다음 두 케이스를 분리한다.

- `후보 없음`: 스크리닝 또는 최종 점수 기준을 통과한 종목이 없음
- `관찰만`: 일부 흥미 신호는 있으나 진입 후보로 승격할 정도의 근거가 부족함

watchlist 운영 상태:

- `candidate`: 신규 편입 또는 유지 강화
- `observe`: 계속 추적
- `avoid`: 즉시 삭제가 아니라 누적 약세 횟수 증가 후 제거 가능

이 상태는 Telegram과 JSON 모두에서 명시적으로 드러나야 한다.

보유 종목 상태 라벨:

- `보유 유지`
- `긍정적 관찰`
- `경계`
- `비중 축소 검토`
- `재점검 필요`

신규 후보 상태 라벨:

- `매수 후보`
- `관찰 후보`
- `후보 없음`

## 오류 및 로깅 규칙

- 네트워크/API 오류는 종목 단위로 격리한다.
- 일부 agent 실패 시 전체 실행을 무조건 중단하지 말고, 가능한 범위에서 `uncertainties` 또는 실패 사유를 구조화해 남긴다.
- 로그에는 민감정보를 남기지 않는다.
- raw prompt 전문을 기본 로그에 남기지 않는다.

## 구현 시 권장 Enum

- `action_label`: `candidate`, `observe`, `avoid`
- `chart label`: `breakout`, `pullback`, `range`, `extended`, `mixed`
- `confidence`: `low`, `medium`, `high`

## 완료 기준

- 각 agent 파일이 존재한다.
- 각 agent는 입력/출력 스키마를 코드로 강제한다.
- orchestrator가 순차 호출한다.
- JSON 저장과 Telegram 출력이 동일한 근거 구조를 공유한다.
- 후보 없음 시나리오가 테스트 가능하다.
