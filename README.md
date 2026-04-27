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

## 데이터 구조

웹 요청 시 외부 API를 매번 호출하지 않는다. GitHub Actions가 하루에 한 번 JSON 데이터를 만들고, FastAPI 서버는 이 파일을 읽어서 화면을 렌더링한다.

- [data/web/dashboard_snapshot.json](/Users/young/PycharmProjects/StockAgent/data/web/dashboard_snapshot.json)
  - 화면 표시용 최신 스냅샷
  - 최근 차트 데이터
  - 매크로 판단 결과
  - LLM 또는 fallback 최종 정리

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
4. 매크로 5년 히스토리와 섹터 5년 히스토리를 저장한다.
5. 화면용 `dashboard_snapshot.json`을 생성한다.
6. FastAPI 서버 [app/web/server.py](/Users/young/PycharmProjects/StockAgent/app/web/server.py)가 JSON을 읽어 `/macro`, `/sectors`를 렌더링한다.

## GitHub Actions

workflow:

- [.github/workflows/web_data_refresh.yml](/Users/young/PycharmProjects/StockAgent/.github/workflows/web_data_refresh.yml)

트리거:

- `workflow_dispatch`
- 매일 `22:00 UTC` 1회 실행

workflow가 하는 일:

1. Python 의존성을 설치한다.
2. `scripts/refresh_web_data.py`를 실행한다.
3. `dashboard_snapshot.json`, `macro_history.json`, `sector_history.json`을 artifact로 업로드한다.
4. 데이터가 바뀌었으면 `Refresh web dashboard data` 커밋으로 repo에 반영한다.

선택 환경값:

- `OPENAI_API_KEY`: 매크로 최종 정리 LLM 생성용
- `OPENAI_MODEL_MACRO_SUMMARY`: 기본값 `gpt-4.1-mini`
- `STOCKAGENT_LIVE_FALLBACK=0`: 운영에서 스냅샷 누락을 오류로 확인

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/refresh_web_data.py
python -m uvicorn app.web.server:app --reload --port 8000
```

브라우저:

- [http://127.0.0.1:8000/macro](http://127.0.0.1:8000/macro)
- [http://127.0.0.1:8000/sectors](http://127.0.0.1:8000/sectors)

## 주요 파일

- [app/web/server.py](/Users/young/PycharmProjects/StockAgent/app/web/server.py): FastAPI 라우트
- [app/web/dashboard_data.py](/Users/young/PycharmProjects/StockAgent/app/web/dashboard_data.py): 데이터 수집, 장기 백분위, 매크로 판단
- [app/web/market_sources.py](/Users/young/PycharmProjects/StockAgent/app/web/market_sources.py): yfinance 정규화, 섹터 바스켓
- [app/web/templates](/Users/young/PycharmProjects/StockAgent/app/web/templates): HTML 템플릿
- [app/web/static](/Users/young/PycharmProjects/StockAgent/app/web/static): CSS/JS
- [scripts/refresh_web_data.py](/Users/young/PycharmProjects/StockAgent/scripts/refresh_web_data.py): 일일 데이터 갱신 스크립트
