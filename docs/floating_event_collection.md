# 유동 이벤트 후보 수집

유동 이벤트는 뉴스에서 발견되는 정책, 외교, 지정학, 수급 이벤트다. NewsData.io 자동 수집 결과는 `data/web/floating_event_candidates.json`에 저장한다. 현재 `/calendar` 화면은 주요 일정만 노출하므로 유동 이벤트 후보는 화면에 바로 표시하지 않는다.

## 데이터 흐름

1. 기존 GitHub Actions refresh가 매일 KST 07:00에 실행된다.
2. `scripts/refresh_web_data.py`가 NewsData.io를 호출한다.
3. 자동 후보는 `data/web/floating_event_candidates.json`에 저장한다.
4. 월별 승인 파일 `data/web/floating_events/YYYY-MM.json`은 보관 구조만 유지한다.
5. 현재 화면에는 후보/승인 유동 이벤트를 노출하지 않는다.

## NewsData.io 호출 정책

- `NEWSDATA_API_KEY`가 있으면 1차 수집기로 사용한다.
- 하루 1회 refresh 때만 호출한다.
- 미국/한국 뉴스 쿼리를 모두 본다.
- 기본값:
  - `NEWSDATA_MIN_REQUEST_INTERVAL_SECONDS=3`
  - `NEWSDATA_MAX_QUERIES_PER_REFRESH=15`
  - `NEWSDATA_TIMEOUT_SECONDS=30`
- 쿼리별 실패는 `errors`에 누적한다.
- `RateLimitExceeded`가 오면 남은 호출을 즉시 중단한다.
- rate limit처럼 전체 호출이 실패하면 기존 후보 파일을 빈 결과로 덮지 않고 이전 후보를 유지한다.

## 날짜 추론

유동 이벤트는 기사 발행일이 아니라 실제 이벤트 시작일에 표시한다.

- `published_date`: 기사 발행일
- `event_date`: 제목/설명에서 추론한 실제 이벤트 시작일
- `event_end_date`: 기간 이벤트 종료일
- `date_confidence`: `high`, `medium`, `low`

룰:

- `May 14-15`, `5월 14~15일`처럼 월/일이 명확하면 시작일과 종료일을 저장한다.
- `Thursday`, `목요일`처럼 요일만 있으면 기사 발행일 기준 다음 해당 요일로 계산한다.
- 요일/월일 표현이 있어도 회의, 결정, 발표, 예정 같은 이벤트 맥락이 없으면 달력에 표시하지 않는다.
- 날짜가 없거나 신뢰도가 낮으면 `event_date`를 비운다. 현재 화면에는 노출하지 않는다.
- `us_china_summit`에서 `Trump-Xi`, `US China summit`, `미중 정상회담`과 `May 14-15` 또는 `Thursday`가 함께 잡히면 시작일과 종료일을 함께 저장한다.

## 기본 쿼리

미국 뉴스:

- `"Trump Xi"`
- `"US China summit"`
- `"export controls"`
- `"semiconductor sanctions"`
- `"OPEC meeting"`
- `"Federal Reserve"`

한국 뉴스:

- `"Bank of Korea"`
- `"Korea exports"`
- `"Korea short selling"`
- `"MSCI Korea"`
- `"South Korea semiconductor"`
- `"미중 정상회담"`
- `"관세"`
- `"수출통제"`
- `"금통위"`

## Canonical 병합

한국어/영어 표현은 같은 이벤트 축으로 정규화한다.

- `US China summit`, `미중 정상회담`, `Trump Xi meeting` -> `us_china_summit`
- `export controls`, `수출통제` -> `export_controls`
- `Bank of Korea`, `금통위` -> `bank_of_korea`

## 동적 키워드 점수 공식

최근 후보 기사에서 제목, 설명, 도메인, 언어, 국가, NewsData.io 메타데이터를 사용한다.

```text
score =
  source_count * 3
  + article_count * 1
  + market_axis_bonus
  + date_detected_bonus
  + high_impact_term_bonus
  + bilingual_match_bonus
  - stale_penalty
  - noise_penalty
```

가산:

- `market_axis_bonus`: 금리, 환율, 유가, 무역, 제재, 반도체, 중앙은행, 지정학, 한국 수급 축이면 가산
- `date_detected_bonus`: 명확한 이벤트 날짜가 있으면 가산
- `high_impact_term_bonus`: `summit`, `tariff`, `sanction`, `export control`, `FOMC`, `OPEC`, `금통위`, `공매도`, `리밸런싱` 등
- `bilingual_match_bonus`: 미국/한국 뉴스 양쪽에서 같은 canonical 이벤트가 잡히면 가산

감점:

- `stale_penalty`: 최근성이 낮거나 같은 내용이 오래 반복되면 감점
- `noise_penalty`: 의견, 전망, 종목 추천, 일반 정치 기사, 날짜 없는 해설성 기사면 감점

승격 조건:

- `source_count >= 2`
- `article_count >= 2`
- `score >= 8`
- 시장 영향 축 1개 이상 연결
- blocklist 미포함

동적 키워드는 `first_seen`, `last_seen`, `hit_count`, `source_count`, `score`, `expires_at`, `status`를 저장한다. 14일간 재등장하지 않거나 `expires_at`이 지나면 비활성화한다.
