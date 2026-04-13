# StockAgent

개인용 스윙 투자 의사결정 보조 서비스다. 자동매매가 아니라, 시장과 종목을 매일 점검해서 `지금 계속 볼 종목`, `보유 유지가 필요한 종목`, `새로 관심 가질 만한 종목`을 근거와 함께 정리해 준다.

현재는 한국 시장과 미국 시장을 각각 따로 브리핑하고, 보유 종목과 신규 후보를 분리해서 Telegram으로 전달한다.

## 이 서비스가 하는 일

- 한국 시장과 미국 시장을 따로 브리핑한다.
- 보유 종목은 `계속 보유할지`, `경계할지`, `재점검이 필요한지`를 따로 본다.
- 신규 후보는 `매수 후보`, `관찰 후보`, `후보 없음`으로 나눈다.
- 차트 해석과 뉴스 해석은 LLM이 맡고, 이동평균선/거래량/변동성 같은 계산은 Python이 맡는다.
- 결과는 Telegram 메시지와 JSON 파일로 남긴다.
- 후보가 없으면 억지로 추천하지 않고 `후보 없음`을 명시한다.

## 이 서비스가 하지 않는 일

- 자동 주문을 넣지 않는다.
- 손익 보장을 하지 않는다.
- 뉴스 기사나 차트에서 근거 없이 없는 사실을 지어내지 않도록 설계되어 있다.

## 매일 어떤 순서로 동작하나

1. 한국/미국 시장 기본 데이터와 최신 뉴스를 수집한다.
2. 보유 종목, discovery universe, watchlist를 합쳐서 스캔 대상을 만든다.
3. 가격/거래량 같은 1차 조건으로 너무 약한 종목을 먼저 걸러낸다.
4. 통과 종목의 차트 feature를 계산한다.
5. LLM이 차트를 해석한다.
6. 최신 뉴스만 모아서 LLM이 뉴스 해석을 한다.
7. 최종 점수를 계산해 `보유 상태`와 `신규 후보 상태`를 결정한다.
8. 한국 시장 메시지 1건, 미국 시장 메시지 1건을 Telegram으로 보낸다.
9. 실행 결과를 JSON으로 저장하고 watchlist를 갱신한다.

## 어떤 데이터를 보나

### 시장 데이터

- 미국/한국 주가, 거래량, 지수: `yfinance`
- 시장 뉴스와 종목 뉴스: Google News RSS
- 한국 시장 수급:
  - 1순위: `KR_FLOW_PATH` 파일
  - 2순위: `pykrx` best-effort
  - 둘 다 실패하면 fallback 문구 사용

### 종목별로 계산하는 주요 값

- `ma20`, `ma60`, `ma120`
- `above_ma20`, `above_ma60`, `above_ma120`
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

즉 이 서비스는 단순히 “뉴스 좋다” 수준으로 보지 않고, 추세/거래량/고점 거리/변동성까지 같이 본다.

## 어떤 기준으로 1차 필터링하나

현재 discovery 종목은 아래 기준을 먼저 본다.

- 가격 이력 최소 `140`일 이상
- 미국 종목 최근 종가 `10달러` 이상
- 한국 종목 최근 종가 `5,000원` 이상
- 최근 20일 평균 거래량 `1,000,000` 이상

기본값은 GitHub Variables나 환경변수로 바꿀 수 있다.

- `MIN_PRICE_US=10`
- `MIN_PRICE_KR=5000`
- `MIN_AVG_VOLUME=1000000`

중요한 점:

- 보유 종목은 `--limit`를 줘도 항상 스캔에 포함된다.
- 보유 종목은 가격/거래량 기준이 약해도 브리핑에서 완전히 빠지지 않도록 별도 처리한다.

## 최종 판단 기준은 어떻게 되나

현재 기본 threshold는 아래와 같다.

- `매수 후보(candidate)`
  - `final_score >= 70`
  - `chart_score >= 68`
  - `news_score >= 45`
- `관찰 후보(observe)`
  - `final_score >= 55`
- 그 아래는 `avoid`

보유 종목은 이 점수와 차트/뉴스 해석을 종합해서 아래 상태 중 하나로 정리한다.

- `보유 유지`
- `긍정적 관찰`
- `경계`
- `비중 축소 검토`
- `재점검 필요`

신규 후보는 아래처럼 정리한다.

- `매수 후보`
- `관찰 후보`
- `후보 없음`

## 입력 파일은 무엇을 쓰나

### 1. 보유 종목 입력

파일: [data/inputs/holdings.json](/Users/young/PycharmProjects/StockAgent/data/inputs/holdings.json)

예시:

```json
{
  "kr": [
    { "ticker": "005490.KS" },
    { "ticker": "097950.KS" },
    { "ticker": "402340.KS" }
  ],
  "us": [
    { "ticker": "TSLA" },
    { "ticker": "META" }
  ]
}
```

샘플 파일: [data/inputs/holdings.sample.json](/Users/young/PycharmProjects/StockAgent/data/inputs/holdings.sample.json)

### 2. 한국 시장 수급 입력

파일: [data/inputs/kr_flow_snapshot.sample.json](/Users/young/PycharmProjects/StockAgent/data/inputs/kr_flow_snapshot.sample.json)

예시:

```json
{
  "as_of": "2026-04-13",
  "source": "manual",
  "markets": {
    "KOSPI": {
      "foreign": "+420억",
      "institution": "-180억",
      "individual": "-210억"
    },
    "KOSDAQ": {
      "foreign": "-35억",
      "institution": "+62억",
      "individual": "-18억"
    }
  }
}
```

이 파일은 실시간 원천 데이터가 아니라, 브리핑에 넣을 한국 수급 값을 주입하는 운영용 입력이다.

## 출력은 어떻게 나오나

Telegram은 `한국 시장 1건`, `미국 시장 1건`으로 따로 간다.

구조는 항상 같다.

1. 시장 상황
2. 보유 종목 브리핑
3. 추가 매수 후보

### Telegram 예시

```text
[2026-04-14 데일리 브리핑]

🇰🇷 한국 시장
[1] 시장 상황
- 요약: 지수는 버티지만 종목별 차별화가 강하다.
- 지수 흐름: KOSPI +0.42% / KOSDAQ -0.18%
- 수급/체크: KOSPI 외국인 +420억, 기관 -180억, 개인 -210억

[2] 보유 종목 브리핑
- POSCO Holdings | 005490.KS
  상태: 경계
  요약: 중기 추세는 아직 남아 있지만 단기 반등 신뢰도는 약하다.

- CJ CheilJedang | 097950.KS
  상태: 보유 유지
  요약: 박스권 안이지만 추세 훼손은 아직 아니다.

[3] 추가 매수 후보
- 오늘은 신규 매수 후보 없음
  근거: 조건을 강하게 통과한 종목이 부족하고, 시장 주도력이 제한적이다.
```

```text
[2026-04-14 데일리 브리핑]

🇺🇸 미국 시장
[1] 시장 상황
- 요약: 기술주 상대강도는 유지되지만 추격 매수는 선별적으로 봐야 한다.
- 지수 흐름: S&P 500 +0.31% / Nasdaq +0.84% / Dow -0.12%

[2] 보유 종목 브리핑
- Tesla, Inc. | TSLA
  상태: 재점검 필요
  요약: 추세 신뢰도가 약하고 뉴스 변동성이 크다.

- Meta Platforms, Inc. | META
  상태: 긍정적 관찰
  요약: 추세는 양호하지만 단기 과열 여부를 같이 봐야 한다.

[3] 추가 매수 후보
- AMD | 매수 후보
  왜 지금 보는가: 차트 추세와 뉴스 분위기가 동시에 우호적이다.
```

### JSON 저장 예시

매 실행마다 아래 파일이 갱신된다.

- [data/outputs/latest.json](/Users/young/PycharmProjects/StockAgent/data/outputs/latest.json)
- `data/outputs/scan_YYYYMMDD_HHMMSS.json`
- [data/outputs/watchlist.json](/Users/young/PycharmProjects/StockAgent/data/outputs/watchlist.json)

`latest.json`에는 최소 아래가 들어간다.

- `run_at`
- `candidate_count`
- `ticker`
- `name`
- `chart_features`
- `chart_analysis`
- `news_analysis`
- `final_analysis`

브리핑용으로는 아래 섹션도 저장된다.

- `market_sections`
- `market_briefing`
- `holdings`
- `candidate_briefs`
- `observe_briefs`
- `rejection_summary`
- `no_candidate_reason`

샘플 파일: [data/outputs/sample_result.json](/Users/young/PycharmProjects/StockAgent/data/outputs/sample_result.json)

## 어떻게 실행하나

### 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --no-telegram
```

### 자주 쓰는 명령

설정 점검:

```bash
python -m app.main --self-check
```

보유 종목 미리보기:

```bash
python -m app.main --holdings-preview
```

일부 종목만 빠르게 검증:

```bash
python -m app.main --no-telegram --limit 5
```

LLM 연동 최소 점검:

```bash
python -m app.main --llm-smoke
python -m app.main --llm-smoke --llm-role final
```

Telegram 연결만 테스트:

```bash
python -m app.main --telegram-test
```

## GitHub Actions에서는 어떻게 쓰나

workflow 파일: [.github/workflows/stock_scan.yml](/Users/young/PycharmProjects/StockAgent/.github/workflows/stock_scan.yml)

지원 트리거:

- `workflow_dispatch`
- `schedule`

### 필수 Secrets

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

### 자주 쓰는 Variables

- `LLM_PROVIDER`
- `LLM_MODEL_DEFAULT`
- `LLM_MODEL_CHART`
- `LLM_MODEL_NEWS`
- `LLM_MODEL_FINAL`
- `HOLDINGS_PATH`
- `KR_FLOW_PATH`
- `MIN_PRICE_US`
- `MIN_PRICE_KR`
- `MIN_AVG_VOLUME`
- `MAX_NEWS_AGE_HOURS`
- `TOP_N_CANDIDATES`
- `CANDIDATE_MIN_FINAL_SCORE`
- `OBSERVE_MIN_FINAL_SCORE`
- `CANDIDATE_MIN_CHART_SCORE`
- `CANDIDATE_MIN_NEWS_SCORE`

### 한국 수급 값을 Variables로 넣고 싶다면

- `KR_FLOW_KOSPI_FOREIGN`
- `KR_FLOW_KOSPI_INSTITUTION`
- `KR_FLOW_KOSPI_INDIVIDUAL`
- `KR_FLOW_KOSDAQ_FOREIGN`
- `KR_FLOW_KOSDAQ_INSTITUTION`
- `KR_FLOW_KOSDAQ_INDIVIDUAL`

workflow는 실행 전에 `scripts/update_kr_flow_snapshot.py`를 호출한다. 위 값이 있으면 한국 시장 수급 snapshot을 만들고, 없으면 조용히 건너뛴다.

## 현재 데이터 범위와 한계

- 미국/한국 discovery universe는 아직 완전 시장 전체가 아니라 curated pool 중심이다.
- 한국 시장 수급은 안정적인 무료 공식 실시간 API를 아직 확보하지 못했다.
- 그래서 한국 수급은 `KR_FLOW_PATH` 또는 `pykrx optional` 구조로 운영한다.
- 시장 이벤트는 경제 캘린더 API가 아니라 최신 시장 뉴스 기반 요약이다.
- 뉴스는 Google News RSS 기반이라 source 품질과 정밀도는 계속 보강 대상이다.
- 자동매매용 서비스가 아니라 의사결정 보조 도구다.

## 운영에 꼭 알아야 하는 파일

- [app/config.py](/Users/young/PycharmProjects/StockAgent/app/config.py)
  - 기본 threshold, 경로, 모델 설정
- [data/inputs/holdings.json](/Users/young/PycharmProjects/StockAgent/data/inputs/holdings.json)
  - 내 보유 종목 입력
- [.github/workflows/stock_scan.yml](/Users/young/PycharmProjects/StockAgent/.github/workflows/stock_scan.yml)
  - GitHub Actions 실행 방식
- [app/orchestrator.py](/Users/young/PycharmProjects/StockAgent/app/orchestrator.py)
  - 실제 스캔 흐름
- [app/reporting/formatter.py](/Users/young/PycharmProjects/StockAgent/app/reporting/formatter.py)
  - Telegram/콘솔 출력 형식

## 릴리스 상태

현재 기준 릴리스 베이스라인은 `v0.1.0`이다.
릴리스 메모: [docs/release-v0.1.0.md](/Users/young/PycharmProjects/StockAgent/docs/release-v0.1.0.md)
