# StockAgent

StockAgent는 개인 투자자가 `언제 공격하고 언제 방어할지`, `어디에 돈이 몰리는지`를 구조적으로 판단하기 위한 웹 대시보드다.

자동매매나 종목 매수/매도 지시 서비스가 아니다. 시장 매크로, 섹터 상대강도, 장기 백분위, 요약 판단을 한 화면에서 보여주는 의사결정 보조 도구다.

## 화면

- `/macro`
  - 주요 매크로 지표를 종합해 공격 점수와 장세 판단을 보여준다.
  - 지수, 변동성, 금리, 신용, 달러, 원자재, 한국시장, 고베타 자산을 함께 본다.
  - 각 지표는 현재값, 최근 변화, 5년 기준 백분위, 해석, 히스토리 차트를 제공한다.
  - OpenAI API 키가 있으면 하루 1회 데이터 갱신 시 최종 정리를 LLM으로 생성한다. 키가 없으면 룰 기반 요약을 사용한다.

- `/sectors`
  - 미국/한국 섹터를 시장 벤치마크와 비교한다.
  - 20일 상대강도가 시장보다 강한 섹터를 상단에 보여준다.
  - 각 섹터는 최근 흐름과 5년 기준 상대강도 백분위를 제공한다.

- `/calendar`
  - 미국/한국 주식시장에 영향을 주는 다가오는 주요 일정을 보여준다.
  - 공식/정형 일정만 앞으로 30일 범위에서 일정이 있는 날만 표시하고, 이전/다음은 30일 단위로 이동한다.

## 데이터 구조

웹 요청 시 외부 API를 매번 호출하지 않는다. GitHub Actions가 하루에 한 번 JSON 데이터를 만들고, FastAPI 서버는 이 파일을 읽어서 화면을 렌더링한다.

- [data/web/dashboard_snapshot.json](/Users/young/PycharmProjects/StockAgent/data/web/dashboard_snapshot.json)
  - 화면 표시용 최신 스냅샷
  - 최근 차트 데이터
  - 매크로 판단 결과
  - LLM 또는 fallback 최종 정리

- [data/web/calendar](/Users/young/PycharmProjects/StockAgent/data/web/calendar)
  - 월별 주요 일정 원천 데이터
  - 파일명은 `YYYY-MM.json`
  - FOMC, BEA, Census, ISM 기반 공식 발표 일정, 시장, 중요도, 출처, 시장 영향 설명

- [data/web/floating_event_candidates.json](/Users/young/PycharmProjects/StockAgent/data/web/floating_event_candidates.json)
  - NewsData.io에서 매일 KST 07:00에 수집하는 유동 이벤트 후보
  - 화면에는 바로 노출하지 않는다.

- [data/web/floating_events](/Users/young/PycharmProjects/StockAgent/data/web/floating_events)
  - 수동 관리하는 월별 유동 이벤트
  - 파일명은 `YYYY-MM.json`
  - 현재 `/calendar` 화면에는 노출하지 않는다.

- [data/history/macro_history.json](/Users/young/PycharmProjects/StockAgent/data/history/macro_history.json)
  - 매크로 5년 장기 히스토리
  - 현재값의 장기 백분위 계산에 사용

- [data/history/sector_history.json](/Users/young/PycharmProjects/StockAgent/data/history/sector_history.json)
  - 섹터 5년 장기 상대강도 히스토리
  - 섹터별 장기 백분위 계산에 사용

## 현재 로직

1. `scripts/refresh_web_data.py`가 실행된다.
2. [app/web/dashboard_data.py](/Users/young/PycharmProjects/StockAgent/app/web/dashboard_data.py)가 yfinance와 FRED 데이터를 수집한다.
3. [app/web/market_sources.py](/Users/young/PycharmProjects/StockAgent/app/web/market_sources.py)가 가격 데이터 정규화와 한국 섹터 바스켓 정의를 담당한다.
4. NewsData.io API로 미국/한국 유동 이벤트 후보를 수집한다.
5. 매크로 5년 히스토리와 섹터 5년 히스토리를 저장한다.
6. 화면용 `dashboard_snapshot.json`을 생성한다.
7. FastAPI 서버 [app/web/server.py](/Users/young/PycharmProjects/StockAgent/app/web/server.py)가 JSON을 읽어 `/macro`, `/sectors`, `/calendar`를 렌더링한다.

## GitHub Actions

workflow:

- [.github/workflows/web_data_refresh.yml](/Users/young/PycharmProjects/StockAgent/.github/workflows/web_data_refresh.yml)

트리거:

- `workflow_dispatch`
- 매일 `22:00 UTC` 1회 실행

workflow가 하는 일:

1. Python 의존성을 설치한다.
2. `scripts/refresh_web_data.py`를 실행한다.
3. `dashboard_snapshot.json`, `macro_history.json`, `sector_history.json`, 정적 사이트 산출물을 artifact로 업로드한다.
4. 데이터나 정적 사이트가 바뀌었으면 `Refresh web dashboard data and static site` 커밋으로 repo에 반영한다.

선택 환경값:

- `OPENAI_API_KEY`: 매크로 최종 정리 LLM 생성용
- `OPENAI_MODEL_MACRO_SUMMARY`: 기본값 `gpt-4.1-mini`
- `STOCKAGENT_LIVE_FALLBACK=0`: 운영에서 스냅샷 누락을 오류로 확인
- `NEWSDATA_API_KEY`: 유동 이벤트 후보 수집 1차 소스
- `NEWSDATA_MIN_REQUEST_INTERVAL_SECONDS`: 기본값 `3`
- `NEWSDATA_MAX_QUERIES_PER_REFRESH`: 기본값 `15`
- `NEWSDATA_TIMEOUT_SECONDS`: 기본값 `30`
- `STOCKAGENT_NEWS_COLLECTION_ENABLED=0`: 유동 이벤트 후보 수집 비활성화
- `STOCKAGENT_FIXED_CALENDAR_ENABLED=0`: 고정 이벤트 자동 수집 비활성화
- `FIXED_CALENDAR_TIMEOUT_SECONDS`: 기본값 `30`

## 로컬 실행

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/refresh_web_data.py
python -m uvicorn app.web.server:app --reload --port 8000
```

브라우저:

- [http://127.0.0.1:8000/macro](http://127.0.0.1:8000/macro)
- [http://127.0.0.1:8000/sectors](http://127.0.0.1:8000/sectors)
- [http://127.0.0.1:8000/calendar](http://127.0.0.1:8000/calendar)

## 검증

```bash
python -m unittest discover -s tests
python -m compileall app scripts tests
python scripts/build_static_site.py --output docs
```

## 주요 파일

- [app/web/server.py](/Users/young/PycharmProjects/StockAgent/app/web/server.py): FastAPI 라우트
- [app/web/dashboard_data.py](/Users/young/PycharmProjects/StockAgent/app/web/dashboard_data.py): 데이터 수집, 장기 백분위, 매크로 판단
- [app/web/market_sources.py](/Users/young/PycharmProjects/StockAgent/app/web/market_sources.py): yfinance 정규화, 섹터 바스켓
- [app/web/templates](/Users/young/PycharmProjects/StockAgent/app/web/templates): HTML 템플릿
- [app/web/static](/Users/young/PycharmProjects/StockAgent/app/web/static): CSS/JS
- [scripts/refresh_web_data.py](/Users/young/PycharmProjects/StockAgent/scripts/refresh_web_data.py): 일일 데이터 갱신 스크립트
