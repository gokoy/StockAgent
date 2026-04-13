# StockAgent

개인용 스윙 투자 의사결정 보조 도구다. 자동매매가 아니라 Python 기반 정량 스크리닝과 LLM 기반 차트/뉴스 해석을 결합해 근거 중심 후보를 정리한다. 현재는 `시장 브리핑 → 보유 종목 → 신규 후보` 구조와 `discovery universe + dynamic watchlist`를 함께 운영하는 방향으로 확장 중이다.

## 핵심 원칙

- 정량 계산은 Python에서 수행
- 차트 해석과 뉴스 해석은 LLM agent가 수행
- agent 간 자유 대화 없이 `orchestrator`가 순차 호출
- 모든 종목 동일 포맷 유지
- 후보 없음/관찰만 허용
- 최신 뉴스만 사용
- 매 실행 결과 JSON 저장
- 서비스가 종목을 발굴하고 watchlist를 유지/제거할 수 있게 확장
- 한국/미국 시장을 분리하고 동일한 브리핑 구조 유지
- 보유 종목과 신규 후보를 분리해 출력

## 디렉터리 구조

```text
repo/
  app/
    main.py
    config.py
    orchestrator.py
    models/schemas.py
    models/enums.py
    data/holdings.py
    data/universe.py
    data/market_briefing.py
    data/market_data.py
    data/news_data.py
    data/watchlist.py
    data/sector_data.py
    screening/screener.py
    screening/filters.py
    chart/features.py
    chart/indicators.py
    chart/patterns.py
    agents/llm_client.py
    agents/chart_agent.py
    agents/news_agent.py
    agents/final_agent.py
    agents/macro_agent.py
    evaluation/tracker.py
    evaluation/performance.py
    evaluation/backtest_stub.py
    reporting/formatter.py
    reporting/telegram.py
    reporting/storage.py
    portfolio/sizing_stub.py
  data/outputs/
  data/inputs/
  data/logs/
  data/performance/
  requirements.txt
  README.md
  .github/workflows/stock_scan.yml
```

## 시스템 다이어그램

![System Diagram](docs/system-diagram.svg)

Mermaid 원본: [docs/system-diagram.mmd](/Users/young/PycharmProjects/StockAgent/docs/system-diagram.mmd)

## 환경변수

- `LLM_PROVIDER` 선택사항, `openai|anthropic|gemini`, 기본값 `openai`
- `LLM_MODEL_DEFAULT` 선택사항, 공통 기본 모델
- `LLM_MODEL_CHART` 선택사항, Chart Agent 모델
- `LLM_MODEL_NEWS` 선택사항, News Agent 모델
- `LLM_MODEL_FINAL` 선택사항, Final Agent 모델
- `LLM_MODEL_MACRO` 선택사항, Macro Agent 모델 placeholder
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `STOCK_UNIVERSE` 선택사항, 예: `AAPL,MSFT,NVDA`
- `US_STOCK_UNIVERSE` 선택사항, 미장 discovery pool
- `KR_STOCK_UNIVERSE` 선택사항, 국장 discovery pool
- `UNIVERSE_MODE` 선택사항, `discovery_plus_watchlist|watchlist|manual`, 기본값 `discovery_plus_watchlist`
- `HOLDINGS_PATH` 선택사항, 기본값 `data/inputs/holdings.json`
- `KR_FLOW_PATH` 선택사항, 기본값 `data/inputs/kr_flow_snapshot.json`
- `MIN_PRICE_US` 선택사항, 기본값 `10`
- `MIN_PRICE_KR` 선택사항, 기본값 `5000`
- `INCLUDE_WATCHLIST` 선택사항, 기본값 `true`
- `WATCHLIST_PATH` 선택사항, 기본값 `data/outputs/watchlist.json`
- `WATCHLIST_MAX_WEAK_RUNS` 선택사항, 기본값 `3`
- `MAX_NEWS_AGE_HOURS` 선택사항, 기본값 `72`
- `TOP_N_CANDIDATES` 선택사항, 기본값 `5`
- `CANDIDATE_MIN_FINAL_SCORE` 선택사항, 기본값 `70`
- `OBSERVE_MIN_FINAL_SCORE` 선택사항, 기본값 `55`
- `CANDIDATE_MIN_CHART_SCORE` 선택사항, 기본값 `68`
- `CANDIDATE_MIN_NEWS_SCORE` 선택사항, 기본값 `45`

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --no-telegram
```

보유 종목은 `data/inputs/holdings.json`에 넣는다.

```json
{
  "kr": [
    { "ticker": "005930.KS" }
  ],
  "us": [
    { "ticker": "NVDA" }
  ]
}
```

샘플 입력은 [data/inputs/holdings.sample.json](/Users/young/PycharmProjects/StockAgent/data/inputs/holdings.sample.json)에 있다. 검증용으로 다른 파일을 쓰려면 `HOLDINGS_PATH`로 경로를 바꾸면 된다.

한국 시장 수급은 기본적으로 `pykrx`를 best-effort로 시도하고, 실패하면 `KR_FLOW_PATH`의 파일 기반 snapshot을 읽는다. 샘플 형식은 [data/inputs/kr_flow_snapshot.sample.json](/Users/young/PycharmProjects/StockAgent/data/inputs/kr_flow_snapshot.sample.json)에 있다.

수급 snapshot을 자동으로 만들거나 갱신하려면 `scripts/update_kr_flow_snapshot.py`를 쓸 수 있다.

```bash
python scripts/update_kr_flow_snapshot.py --print-template
python scripts/update_kr_flow_snapshot.py --source auto
```

`pykrx`가 비거나 실패하면, 아래 환경변수로 수급 값을 주입해 snapshot을 만들 수 있다.

```bash
KR_FLOW_KOSPI_FOREIGN="+420억" \
KR_FLOW_KOSPI_INSTITUTION="-180억" \
KR_FLOW_KOSPI_INDIVIDUAL="-210억" \
KR_FLOW_KOSDAQ_FOREIGN="-35억" \
KR_FLOW_KOSDAQ_INSTITUTION="+62억" \
KR_FLOW_KOSDAQ_INDIVIDUAL="-18억" \
python scripts/update_kr_flow_snapshot.py --source manual
```

설정과 의존성만 점검하려면:

```bash
python -m app.main --self-check
```

`--self-check`에는 현재 `holdings_total`, `holdings_kr`, `holdings_us`가 같이 출력되므로, GitHub Actions나 로컬에서 보유 종목 입력이 실제로 읽혔는지 바로 확인할 수 있다.
또한 `min_price_us`, `min_price_kr`가 같이 출력되므로 미국/한국 가격 기준이 분리됐는지 바로 확인할 수 있다.

보유 종목 ticker가 제대로 풀리는지 빠르게 보려면:

```bash
python -m app.main --holdings-preview
```

샘플 파일 기준으로 미리보려면:

```bash
HOLDINGS_PATH=data/inputs/holdings.sample.json python -m app.main --holdings-preview
```

실제 스캔을 일부 종목으로 제한하려면:

```bash
python -m app.main --no-telegram --limit 2
```

`--limit`를 써도 보유 종목은 항상 우선 포함된다. 즉 빠른 검증을 돌릴 때도 보유 종목 브리핑이 사라지지 않는다.

선택한 provider의 structured JSON 응답을 최소 단위로 확인하려면:

```bash
python -m app.main --llm-smoke
```

역할별 모델 smoke test를 보려면:

```bash
python -m app.main --llm-smoke --llm-role final
```

Telegram 연결만 테스트하려면:

```bash
python -m app.main --telegram-test
```

실제 Telegram 전송은 합본 1건이 아니라 `한국 시장`, `미국 시장`을 각각 별도 메시지로 보낸다. 콘솔 출력과 JSON 저장은 기존처럼 전체 실행 결과를 한 번에 유지한다.
현재 GitHub Actions 기준으로도 이 시장별 2건 전송 포맷이 실제 산출물과 일관되게 동작하는 것을 확인했다.

## GitHub Actions

`.github/workflows/stock_scan.yml`는 다음 트리거를 지원한다.

- `workflow_dispatch`
- `schedule`

이 workflow는 `actions/setup-python`의 `pip` 캐시를 사용하므로, 실행할 때마다 `pip install`은 수행하지만 패키지 다운로드는 재사용될 수 있다.
또한 `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true`를 설정해 Node 24 전환을 선제 적용했다.
현재 로그 기준으로 기존 `Node.js 20 actions are deprecated` 경고는 `Node.js 20 액션이 Node.js 24에서 강제 실행 중`이라는 형태로 바뀌었다. 즉 전환은 적용됐고, 경고를 완전히 없애려면 각 액션의 차기 릴리스를 따라가야 한다.

GitHub Secrets에 아래 값을 설정한다.

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

GitHub Variables 또는 환경변수로 아래 값을 설정할 수 있다.

- `LLM_PROVIDER`
- `LLM_MODEL_DEFAULT`
- `LLM_MODEL_CHART`
- `LLM_MODEL_NEWS`
- `LLM_MODEL_FINAL`
- `LLM_MODEL_MACRO`
- `HOLDINGS_PATH`
- `KR_FLOW_PATH`
- `KR_FLOW_KOSPI_FOREIGN`
- `KR_FLOW_KOSPI_INSTITUTION`
- `KR_FLOW_KOSPI_INDIVIDUAL`
- `KR_FLOW_KOSDAQ_FOREIGN`
- `KR_FLOW_KOSDAQ_INSTITUTION`
- `KR_FLOW_KOSDAQ_INDIVIDUAL`
- `UNIVERSE_MODE`
- `US_STOCK_UNIVERSE`
- `KR_STOCK_UNIVERSE`
- `INCLUDE_WATCHLIST`
- `WATCHLIST_MAX_WEAK_RUNS`
- `MAX_NEWS_AGE_HOURS`
- `TOP_N_CANDIDATES`
- `CANDIDATE_MIN_FINAL_SCORE`
- `OBSERVE_MIN_FINAL_SCORE`
- `CANDIDATE_MIN_CHART_SCORE`
- `CANDIDATE_MIN_NEWS_SCORE`

workflow는 실행 전에 `scripts/update_kr_flow_snapshot.py`를 호출한다. `KR_FLOW_*` Variables가 채워져 있으면 한국 수급 snapshot을 자동 생성하고, 비어 있으면 이 단계는 조용히 건너뛴다.
운영 중에는 이 값들을 GitHub Variables에 유지해도 되고, 일시 검증 후 비워도 된다. 비워 두면 한국 수급은 다시 `pykrx optional -> fallback 문구` 경로로 동작한다.
현재 저장소의 테스트용 `KR_FLOW_*` 값은 검증 후 제거해 두었다.

## 저장 결과

매 실행마다 `data/outputs/scan_YYYYMMDD_HHMMSS.json`과 `data/outputs/latest.json`을 저장한다. watchlist를 켜면 `data/outputs/watchlist.json`도 함께 갱신한다.

`watchlist.json`에는 최소한 아래 상태가 저장된다.

- `ticker`
- `name`
- `market`
- `last_action`
- `last_final_score`
- `active`
- `consecutive_weak_runs`
- `note`

필수 필드:

- `run_at`
- `candidate_count`
- `ticker`
- `name`
- `chart_features`
- `chart_analysis`
- `news_analysis`
- `final_analysis`

추가로 브리핑 구조를 위해 아래 섹션이 저장된다.

- `market_sections`
- `market_briefing`
- `holdings`
- `candidate_briefs`
- `observe_briefs`
- `rejection_summary`
- `no_candidate_reason`

## 샘플 결과 JSON

샘플 파일: [data/outputs/sample_result.json](/Users/young/PycharmProjects/StockAgent/data/outputs/sample_result.json)

## 샘플 Telegram 메시지

```text
[2026-04-12 데일리 브리핑]

🇰🇷 한국 시장
[1] 시장 상황
- 요약: 지수 방향이 혼조라 종목 선별이 더 중요하다.
- 지수 흐름: KOSPI +0.22% / KOSDAQ -0.35%
- 수급/체크: KOSPI 외국인 +420억, 기관 -180억, 개인 -210억

[2] 보유 종목 브리핑
- 삼성전자 | 005930.KS
  상태: 보유 유지
  요약: 중기 추세는 유지되지만 외국인 수급 둔화는 점검 필요

[3] 추가 매수 후보
- SK하이닉스 | 000660.KS
  상태: 매수 후보
  왜 지금 보는가: 반도체 강세와 추세 재정렬이 동시에 확인된다.
```

```text
[2026-04-12 데일리 브리핑]

🇺🇸 미국 시장
[1] 시장 상황
- 요약: 주요 지수가 전반적으로 강세이며 기술주 상대강도가 유지된다.
- 지수 흐름: S&P 500 +0.62% / Nasdaq +1.14%
- 거시 흐름: 달러인덱스 -0.31% / 미국 10년물 -0.18%

[2] 보유 종목 브리핑
- Amazon.com, Inc. | AMZN
  상태: 긍정적 관찰
  요약: 추세는 살아 있지만 단기 과열 구간 여부를 확인해야 한다.

[3] 추가 매수 후보
- NVIDIA Corporation | NVDA
  상태: 매수 후보
  왜 지금 보는가: 차트 추세와 뉴스 분위기가 모두 우호적이라 신규 후보로 볼 수 있다.
```

## 후보 없음 예시

```text
[2026-04-10 23:30 KST] 후보 없음

스크리닝과 최종 판단을 통과한 종목이 없습니다.
```

## 구현 메모

- 시세 데이터는 `yfinance`를 사용한다.
- 한국 시장 수급 데이터는 `pykrx`를 best-effort optional source로 사용한다.
- 다만 현재 `pykrx`/KRX 응답 경로는 환경과 시점에 따라 빈 응답 또는 실패가 발생할 수 있어, 실수급 데이터는 보장하지 않는다.
- 뉴스는 Google News RSS를 사용해 최신성 필터를 적용한다.
- discovery universe는 현재 `US/KR curated symbol pool`로 시작하며, 실행 중 유효한 종목은 watchlist에 자동 편입/유지될 수 있다.
- 시장 브리핑은 실제 지수/거시/섹터/뉴스 데이터를 사용하고, 이벤트는 최신 시장 뉴스 기반으로 요약한다.
- 보유 종목은 `data/inputs/holdings.json`에서 읽는다.
- watchlist는 `candidate/observe/avoid` 결과를 바탕으로 자동 갱신되며, 약한 결과가 누적되면 비활성화된다.
- 국장 지원은 ticker와 watchlist 구조까지 먼저 열어둔 상태이며, 시장 커버리지와 뉴스 품질은 이후 보강 대상이다.
- LLM 호출은 provider adapter 패턴으로 추상화했고 `OpenAI`, `Anthropic`, `Gemini`를 지원한다.
- 모델 선택은 provider 공통 구조를 사용하고, `default/chart/news/final/macro` 역할별 모델 오버라이드를 지원한다.
- OpenAI 기본 조합은 `chart/news/default = gpt-4.1-mini`, `final = gpt-4.1`이다.
- 사용자 노출 설명과 fallback 문구는 한국어를 기본으로 사용한다.
- provider structured JSON 호출 실패 시 deterministic fallback을 둔다.
- fallback이 발생하면 결과 필드 안에 fallback 사용 흔적을 남긴다.
- 후보 없음과 관찰만은 실제 `action_label` 기준으로 분리하며, 관찰 종목이 있으면 Telegram에 상위 관찰 종목 요약을 함께 보낸다.
- 민감정보는 코드나 로그에 출력하지 않는다.

## 현재 한계

- 미장/국장 discovery universe는 아직 curated symbol list 중심이며, S&P500/Nasdaq100 및 KOSPI/KOSDAQ 전체 동기화는 다음 단계다.
- 시장 이벤트는 경제 캘린더 API가 아니라 최신 이벤트성 뉴스 기반 요약이다.
- 한국 시장 수급은 `pykrx`를 우선 시도하되, 현재 KRX 응답 공백/네트워크 문제로 실제 집계가 안정적으로 보장되지는 않는다.
- 뉴스는 ticker 중심 Google News RSS라 국장 종목과 시장 이벤트에서 정밀도가 떨어질 수 있다.
