# StockAgent

개인용 스윙 투자 의사결정 보조 도구다. 자동매매가 아니라 Python 기반 정량 스크리닝과 LLM 기반 차트/뉴스 해석을 결합해 근거 중심 후보를 정리한다.

## 핵심 원칙

- 정량 계산은 Python에서 수행
- 차트 해석과 뉴스 해석은 LLM agent가 수행
- agent 간 자유 대화 없이 `orchestrator`가 순차 호출
- 모든 종목 동일 포맷 유지
- 후보 없음/관찰만 허용
- 최신 뉴스만 사용
- 매 실행 결과 JSON 저장

## 디렉터리 구조

```text
repo/
  app/
    main.py
    config.py
    orchestrator.py
    models/schemas.py
    models/enums.py
    data/universe.py
    data/market_data.py
    data/news_data.py
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
  data/logs/
  data/performance/
  requirements.txt
  README.md
  .github/workflows/stock_scan.yml
```

## 환경변수

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `OPENAI_MODEL` 선택사항, 기본값 `gpt-4.1-mini`
- `STOCK_UNIVERSE` 선택사항, 예: `AAPL,MSFT,NVDA`
- `MAX_NEWS_AGE_HOURS` 선택사항, 기본값 `72`
- `TOP_N_CANDIDATES` 선택사항, 기본값 `5`

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main --no-telegram
```

Telegram 연결만 테스트하려면:

```bash
python -m app.main --telegram-test
```

## GitHub Actions

`.github/workflows/stock_scan.yml`는 다음 트리거를 지원한다.

- `workflow_dispatch`
- `schedule`

GitHub Secrets에 아래 값을 설정한다.

- `OPENAI_API_KEY`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## 저장 결과

매 실행마다 `data/outputs/scan_YYYYMMDD_HHMMSS.json`과 `data/outputs/latest.json`을 저장한다.

필수 필드:

- `run_at`
- `candidate_count`
- `ticker`
- `name`
- `chart_features`
- `chart_analysis`
- `news_analysis`
- `final_analysis`

## 샘플 결과 JSON

샘플 파일: [data/outputs/sample_result.json](/Users/young/PycharmProjects/StockAgent/data/outputs/sample_result.json)

## 샘플 Telegram 메시지

```text
[2026-04-10 23:30 KST] Swing Scan

NVDA | NVIDIA
- 종합 점수: 78 | 상태: candidate
- 차트 근거: Price is holding above MA20 and MA60. / Price is within reach of the 20-day high with supportive volume. / Recent volatility has tightened versus the prior month.
- 뉴스 요약: NVIDIA headlines show continued AI demand focus / Recent coverage mentions growth-type positive catalysts.
- 주요 리스크: Recent price run-up raises chase risk. / Check whether fresh news changes the near-term thesis.
- 무효화 기준: Setup weakens if price loses the nearby support zone. Hint: 20d low 842.15, MA20 875.42, MA60 812.90.
```

## 후보 없음 예시

```text
[2026-04-10 23:30 KST] 후보 없음

스크리닝과 최종 판단을 통과한 종목이 없습니다.
```

## 구현 메모

- 시세 데이터는 `yfinance`를 사용한다.
- 뉴스는 Google News RSS를 사용해 최신성 필터를 적용한다.
- OpenAI structured JSON 응답을 우선 사용하고, 실패 시 deterministic fallback을 둔다.
- 민감정보는 코드나 로그에 출력하지 않는다.
