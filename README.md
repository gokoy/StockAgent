# StockAgent

StockAgent는 개인용 단기/중기 투자 의사결정 보조 서비스다. 자동매매 서비스가 아니라, 매일 시장과 종목을 점검해서 `보유 종목을 계속 가져갈지`, `단기(1개월 이내)로 볼 후보가 있는지`, `중기(1개월~6개월)로 가져갈 후보가 있는지`, `오늘은 쉬는 게 맞는지`를 근거 중심으로 정리해 준다.

현재는 한국 시장과 미국 시장을 분리해서 브리핑하고, 각 시장마다 아래 구조로 결과를 보낸다.

1. 시장 상황
2. 보유 종목 브리핑
3. 추가 매수 후보

Telegram은 `한국 시장 1건`, `미국 시장 1건`으로 나눠서 전송하고, 실행 결과는 JSON으로도 저장한다.

## 서비스 개요

### 무엇을 하는가

- 한국 시장과 미국 시장을 각각 따로 요약한다.
- 보유 종목은 `단기 관점`과 `중기 관점`을 따로 본다.
- 신규 후보는 `단기 추천 종목`과 `중기 추천 종목`으로 나눠 보여준다.
- 차트 해석과 뉴스 해석은 LLM이 맡고, 수치 계산과 필터링은 Python이 맡는다.
- 후보가 없으면 억지로 추천하지 않고 그 이유를 같이 적는다.
- 결과는 Telegram 메시지와 JSON 파일로 남긴다.

### 무엇을 하지 않는가

- 자동으로 주문하지 않는다.
- 포트폴리오 수익을 보장하지 않는다.
- 근거 없는 추정으로 종목을 추천하지 않도록 설계되어 있다.

## 서비스가 매일 하는 일

1. 시장 데이터와 최신 뉴스를 가져온다.
2. 보유 종목, discovery universe, watchlist를 합쳐 오늘 볼 종목 목록을 만든다.
3. 너무 약한 종목은 가격/거래량 기준으로 먼저 걸러낸다.
4. 남은 종목의 차트 feature를 계산한다.
5. LLM이 차트를 해석한다.
6. 최신 뉴스만 모아서 LLM이 뉴스 해석을 한다.
7. 최종 점수와 horizon 점수를 계산해 보유 상태와 신규 후보 상태를 정한다.
8. 한국 시장 메시지 1건, 미국 시장 메시지 1건을 Telegram으로 전송한다.
9. 전체 결과를 JSON으로 저장하고 watchlist를 갱신한다.

## 데이터는 어디서 가져오나

### 시장/종목 가격 데이터

- 미국/한국 종목 가격, 거래량, 지수: `yfinance`

### 뉴스 데이터

- 시장 뉴스, 종목 뉴스: Google News RSS
- 최신성 필터를 적용해 일정 시간보다 오래된 뉴스는 제외한다.

### 한국 시장 수급 데이터

현재 한국 수급은 안정적인 무료 공식 실시간 API를 붙이지 못해서 아래 순서로 처리한다.

1. `KR_FLOW_PATH` 파일
2. `pykrx` best-effort
3. 둘 다 실패하면 fallback 문구

`KR_FLOW_PATH`는 한국 시장 수급 값을 담은 JSON 파일 경로다. 기본값은 [kr_flow_snapshot.json](/Users/young/PycharmProjects/StockAgent/data/inputs/kr_flow_snapshot.json)이다.

중요한 점:

- 이 값은 항상 자동으로 갱신되는 실시간 데이터 경로가 아니다.
- GitHub Actions에서 `KR_FLOW_*` Variables를 넣으면 workflow가 실행 전에 자동 생성할 수 있다.
- 그렇지 않으면 수동 입력 파일 또는 `pykrx` 결과를 사용한다.

## 종목을 어떤 기준으로 보나

### 1. 1차 필터

discovery 대상 종목은 먼저 아래 기준을 통과해야 한다.

- 가격 이력 최소 `140`일 이상
- 미국 종목 최근 종가 `10달러` 이상
- 한국 종목 최근 종가 `5,000원` 이상
- 최근 20일 평균 거래량 `1,000,000` 이상

기본 운영값:

- `MIN_PRICE_US=10`
- `MIN_PRICE_KR=5000`
- `MIN_AVG_VOLUME=1000000`

예외:

- 보유 종목은 `--limit`를 줘도 항상 스캔에 포함된다.
- 보유 종목은 가격/거래량이 약해도 브리핑에서 완전히 빠지지 않게 별도 처리한다.

### 2. 차트에서 계산하는 주요 값

아래 값은 최종 판단의 재료로 쓰인다.

- `ma20`, `ma60`, `ma120`
  - 20일, 60일, 120일 이동평균선 값이다.
  - 단기/중기/장기 추세를 볼 때 쓴다.
- `above_ma20`, `above_ma60`, `above_ma120`
  - 현재 가격이 각 이동평균선 위에 있는지 여부다.
  - 여러 이동평균선 위에 있으면 추세가 강한 편으로 본다.
- `distance_from_20d_high_pct`
  - 최근 20일 고점 대비 현재 가격이 얼마나 떨어져 있는지 비율이다.
  - 0에 가까우면 최근 고점 근처에 있다는 뜻이다.
- `distance_from_60d_high_pct`
  - 최근 60일 고점 대비 현재 가격 거리다.
  - 중기 기준으로 얼마나 강한지 볼 때 쓴다.
- `volume_ratio_20d`
  - 오늘 거래량이 최근 20일 평균 거래량 대비 몇 배인지 나타낸다.
  - 1보다 크면 평균보다 거래가 많이 붙은 것이다.
- `atr_pct`
  - ATR을 현재 가격 대비 퍼센트로 바꾼 값이다.
  - 하루 변동 폭이 큰 종목인지 작은 종목인지 볼 때 쓴다.
- `volatility_contracting`
  - 최근 변동성이 줄어드는 중인지 여부다.
  - 눌림 후 정리되는 구간인지 판단할 때 쓴다.
- `breakout_setup`
  - 고점 근처에서 돌파 시도가 가능한 구조인지 보는 플래그다.
- `pullback_setup`
  - 강한 추세 이후 눌림목 구조인지 보는 플래그다.
- `range_bound`
  - 방향성 없이 박스권에 가까운 상태인지 여부다.
- `overextended_pct`
  - 이동평균 대비 얼마나 과하게 멀어진 상태인지 보여준다.
  - 높을수록 추격 매수 부담이 크다.
- `recent_sharp_runup`
  - 최근 짧은 기간에 급등했는지 여부다.
  - 급등 직후에는 변동성 확대 가능성을 본다.
- `support_level_hint`
  - 어떤 가격대가 지지선처럼 보이는지 간단히 설명하는 힌트다.

즉 이 서비스는 단순 뉴스 요약기가 아니라, 추세/고점 거리/거래량/변동성/과열 여부를 같이 본다.

### 3. 최종 판단 기준

현재 기본 threshold는 아래와 같다.

- `매수 후보(candidate)`
  - `final_score >= 70`
  - `chart_score >= 68`
  - `news_score >= 45`
- `관찰 후보(observe)`
  - `final_score >= 55`
- 그 아래는 `avoid`

보유 종목은 이 점수와 해석을 종합해서 아래 상태 중 하나로 정리한다.

- `보유 유지`
- `긍정적 관찰`
- `경계`
- `비중 축소 검토`
- `재점검 필요`

신규 후보는 아래처럼 정리한다.

- `매수 후보`
- `관찰 후보`
- `후보 없음`

추가로 출력용으로는 horizon 관점도 같이 계산한다.

- `단기`: 1개월 이내
  - MA20, 20일 고점 거리, 거래량 증가, 돌파 구조, 최근 모멘텀을 더 강하게 본다.
- `중기`: 1개월~6개월
  - MA60, MA120, 60일 고점 거리, 중기 추세 유지 여부를 더 강하게 본다.

보유 종목은 `단기 관점`과 `중기 관점`을 동시에 보여준다. 신규 후보도 `단기 추천 종목` 최대 5개, `중기 추천 종목` 최대 5개로 따로 보여준다.

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

Telegram은 `한국 시장 1건`, `미국 시장 1건`으로 따로 간다. 한 메시지가 Telegram 길이 제한을 넘으면 자동으로 여러 개로 나눠서 보낸다.

구조는 항상 같다.

1. 시장 메모
2. 보유 종목
3. 단기 추천 종목
4. 중기 추천 종목

### Telegram 예시

```text
[2026-04-14 데일리 브리핑]

🇰🇷 한국 시장
🧭 시장 메모
• 요약: 지수는 버티지만 종목별 차별화가 강하다.
• 특이 흐름
  - KOSPI +1.40% 급등
  - KOSDAQ +1.64% 급등
• 주요 이벤트
  - 이번 주 한국은행 일정 관련 기사

📦 보유 종목
• POSCO Holdings | 005490.KS
  ⏱ 단기: 경계
  🗓 중기: 긍정적 관찰
  - 근거
    • MA20, MA60 위 유지
    • 변동성 축소

⚡ 단기 추천 종목
• 오늘은 단기 추천 종목 없음

🏗️ 중기 추천 종목
• 오늘은 중기 추천 종목 없음
```

```text
[2026-04-14 데일리 브리핑]

🇺🇸 미국 시장
🧭 시장 메모
• 요약: 기술주 상대강도는 유지되지만 추격 매수는 선별적으로 봐야 한다.
• 특이 흐름
  - WTI +6.41% 상승
• 주요 이벤트
  - CPI 발표 관련 기사
  - FOMC 관련 기사

📦 보유 종목
• Tesla, Inc. | TSLA
  ⏱ 단기: 재점검 필요
  🗓 중기: 재점검 필요

• Meta Platforms, Inc. | META
  ⏱ 단기: 긍정적 관찰
  🗓 중기: 보유 유지

⚡ 단기 추천 종목
• AMD | 관찰 후보

🏗️ 중기 추천 종목
• NVDA | 매수 후보
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

## 운영자가 매일 확인할 것

### 로컬에서 쓸 때

1. [data/inputs/holdings.json](/Users/young/PycharmProjects/StockAgent/data/inputs/holdings.json)에 보유 종목이 맞게 들어 있는지 확인
2. 필요하면 한국 수급 입력 파일이나 관련 값 갱신
3. `python -m app.main --self-check`로 설정 확인
4. `python -m app.main --holdings-preview`로 보유 종목 이름이 정상 해석되는지 확인
5. `python -m app.main --no-telegram` 또는 일반 실행으로 결과 확인
6. [data/outputs/latest.json](/Users/young/PycharmProjects/StockAgent/data/outputs/latest.json)과 Telegram 메시지가 기대한 형식인지 확인

### GitHub Actions로 운영할 때

1. GitHub Secrets에 `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`가 들어 있는지 확인
2. GitHub Variables에 threshold, holdings 경로, 한국 수급 관련 값이 맞는지 확인
3. `workflow_dispatch`로 한 번 수동 실행
4. Actions artifact의 `latest.json`, `watchlist.json` 확인
5. Telegram에서 한국 시장 1건, 미국 시장 1건이 정상 전송됐는지 확인

### 결과를 볼 때 특히 볼 것

- 보유 종목 상태가 내 체감과 크게 어긋나지 않는지
- 신규 후보가 없을 때 그 이유가 납득 가능한지
- 후보 종목의 `왜 지금 보는가`, `리스크`, `무효화 기준`이 충분히 실용적인지
- 뉴스가 너무 오래됐거나 잡음 source에 치우치지 않았는지
- 한국 수급이 fallback 문구인지 실제 입력값인지

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
