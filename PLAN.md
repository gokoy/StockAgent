# PLAN.md

## 목표 요약

Phase 1에서는 GitHub Actions에서 정기 실행되는 개인용 스윙 투자 보조 도구의 최소 실행 가능한 구조를 완성한다. 핵심은 Python 정량 계산, LLM 기반 차트/뉴스 해석, 순차 orchestrator, JSON 저장, Telegram 전송, 후보 없음 처리다. 이후 Phase 1.5에서는 고정 관심 종목 스캔에서 `discovery universe + dynamic watchlist` 구조로 확장한다.

## 비목표

- 자동매매
- broker 연동
- 실시간 체결/주문
- agent 간 자율 협업
- 과도한 예측형 설명

## 아키텍처 개요

```text
GitHub Actions
  -> app/main.py
  -> orchestrator.py
     -> data/universe.py
     -> screening/screener.py
     -> chart/features.py
     -> agents/chart_agent.py
     -> data/news_data.py
     -> agents/news_agent.py
     -> agents/final_agent.py
     -> reporting/storage.py
     -> reporting/formatter.py
     -> reporting/telegram.py
     -> data/watchlist.py
```

## 운영 방향 업데이트

- 사용자가 직접 종목을 전부 고르지 않아도 되도록 서비스가 시장 universe에서 종목을 발굴한다.
- universe는 `discovery pool`과 `watchlist`로 분리한다.
- discovery pool은 미장/국장 후보군에서 신규 종목을 찾는다.
- watchlist는 과거에 유효했던 종목을 계속 추적하고, 반복적으로 약해지면 제거한다.
- 초기 구현은 `US/KR curated symbols + watchlist merge` 구조로 시작하고, 이후 외부 지수/시장 소스로 확장한다.

## Phase 1 구현 범위

### 1. 실행/설정 계층

- `app/main.py`: 엔트리포인트
- `app/config.py`: 환경변수 로딩 및 검증
- `.github/workflows/stock_scan.yml`: `workflow_dispatch` + `schedule`

완료 기준:

- 로컬 실행 가능
- GitHub Actions에서 환경변수 기반 실행 가능
- Telegram 테스트 메시지 전송 가능

### 2. 데이터 수집 계층

- `app/data/universe.py`: Universe 수집
- `app/data/market_data.py`: OHLCV 로딩
- `app/data/news_data.py`: 최신 뉴스 fetch
- `app/data/watchlist.py`: watchlist 저장/갱신
- `app/data/sector_data.py`: Phase 2 placeholder

완료 기준:

- Universe를 리스트 형태로 반환
- 미장/국장 discovery pool과 watchlist를 병합할 수 있음
- 종목별 가격/거래량 데이터 확보
- 뉴스는 최신성 필터 적용

### 3. 스크리닝/피처 계산

- `app/screening/filters.py`
- `app/screening/screener.py`
- `app/chart/indicators.py`
- `app/chart/patterns.py`
- `app/chart/features.py`

필수 feature:

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

완료 기준:

- 모든 후보 종목에 동일 feature 세트 생성
- feature 누락 시 구조화된 오류 처리

### 4. Agent 계층

- `app/agents/llm_client.py`
- `app/agents/chart_agent.py`
- `app/agents/news_agent.py`
- `app/agents/final_agent.py`
- `app/agents/macro_agent.py` placeholder

완료 기준:

- structured JSON 응답 강제
- chart/news/final agent 순차 호출
- agent 간 직접 통신 금지

### 5. 모델/스키마 계층

- `app/models/enums.py`
- `app/models/schemas.py`

완료 기준:

- 입력/출력 schema를 코드로 검증
- Telegram과 저장 포맷이 동일 schema를 사용

### 6. 리포팅/저장 계층

- `app/reporting/storage.py`
- `app/reporting/formatter.py`
- `app/reporting/telegram.py`

완료 기준:

- 실행 결과 JSON 저장
- Telegram 리포트 포맷 고정
- 후보 없음 메시지 지원

### 7. 평가/확장 placeholder

- `app/evaluation/tracker.py`
- `app/evaluation/performance.py`
- `app/evaluation/backtest_stub.py`
- `app/portfolio/sizing_stub.py`

완료 기준:

- import 가능한 placeholder 제공
- Phase 2 구현 진입점 명확화

## 권장 디렉터리 생성 순서

1. 루트 디렉터리와 `app/` 하위 구조 생성
2. `models/`와 `config.py` 먼저 작성
3. `data/`, `screening/`, `chart/` 구현
4. `agents/` 구현
5. `reporting/` 구현
6. `main.py`, `orchestrator.py` 연결
7. workflow, README, 샘플 결과 추가

## Orchestrator 상세 플로우

1. 설정 로드
2. 실행 시각 `run_at` 생성
3. Discovery universe 수집
4. Watchlist 로드 및 병합
5. 시장 데이터 조회
6. Screening 수행
7. 후보별 chart feature 계산
8. Chart Agent 호출
9. 최신 뉴스 조회
10. News Agent 호출
11. Final Agent 호출
12. watchlist add/keep/remove 상태 갱신
13. 최종 후보 정렬 및 3~5개 선택
14. JSON 저장
15. Telegram 메시지 생성 및 전송

## 출력 스키마 고정 방침

모든 종목은 아래 상위 구조를 따른다.

```json
{
  "ticker": "",
  "name": "",
  "chart_features": {},
  "chart_analysis": {},
  "news_analysis": {},
  "final_analysis": {}
}
```

전체 실행 결과는 아래를 포함한다.

```json
{
  "run_at": "",
  "candidate_count": 0,
  "candidates": [],
  "non_candidates": []
}
```

## 후보 선정 규칙 초안

- 1차: Discovery universe와 watchlist 병합
- 2차: 유동성/가격/거래량 기준 필터링
- 2차: 차트 setup 존재 여부 확인
- 3차: 최신 뉴스 해석 반영
- 4차: final score 기반 정렬
- 5차: 상위 3~5개만 Telegram에 노출

예외:

- 기준 충족 종목이 없으면 `후보 없음`
- 일부 신호만 있으면 `관찰만`

watchlist 운영 예외:

- `candidate` 또는 `observe`는 watchlist 유지 또는 신규 편입 대상이다.
- `avoid`가 반복되면 watchlist에서 제거한다.
- 신규 discovery 편입 기준과 기존 watchlist 유지 기준은 분리 가능해야 한다.

## GitHub Actions 요구사항

- 트리거: `workflow_dispatch`, `schedule`
- Secrets:
  - `OPENAI_API_KEY`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- 로그에 secret 값 출력 금지
- 실행 후 JSON artifact 또는 저장 파일 유지 고려

## 작업 운영 원칙

- 의미 있는 변경은 작업 단위로 나누어 커밋한다.
- 문서 변경도 독립적인 작업이면 별도 커밋으로 남긴다.
- 진행 상태가 바뀌면 `STATUS.md`를 먼저 갱신하고 커밋 범위에 포함한다.
- 커밋 메시지는 변경 의도가 드러나게 짧고 명확하게 작성한다.

## LLM 아키텍처 원칙

- Phase 1과 초기 Phase 2에서는 `LangChain`, `LangGraph`를 도입하지 않는다.
- 현재 워크플로는 순차 orchestrator와 고정 JSON schema가 핵심이므로 순수 Python 구조를 유지한다.
- LLM 제공자 전환은 공통 interface와 provider adapter 패턴으로 구현한다.
- 우선 대상 제공자는 `OpenAI`, `Anthropic`, `Google Gemini`다.
- Phase 2에서 분기, 상태관리, 재시도, 다단계 의존성이 실제로 복잡해지면 그 시점에 `LangGraph` 도입 여부를 재평가한다.

## README 포함 항목

- 프로젝트 목적
- 디렉터리 구조
- 환경변수 설정 방법
- 로컬 실행 방법
- GitHub Actions 설정 방법
- 샘플 JSON 결과
- 샘플 Telegram 메시지
- 후보 없음 예시

## 샘플 산출물 계획

- `data/outputs/sample_result.json`
- `README.md` 내 sample Telegram message

## 리스크와 대응

- 뉴스 최신성 판단 실패
  - 대응: fetch 시각 및 게시 시각 기준 필터 명시
- LLM 응답 형식 이탈
  - 대응: schema validation + retry + fallback
- 데이터 소스 장애
  - 대응: 부분 실패 허용, uncertainty 기록
- 후보 과다/과소
  - 대응: score threshold와 상위 N 제한 분리
- universe 품질 부족
  - 대응: 초기에는 curated US/KR 풀로 시작하고 이후 index/market source로 교체

## Phase 1.5 추가 목표

- `UNIVERSE_MODE=discovery_plus_watchlist|watchlist|manual` 지원
- `US_STOCK_UNIVERSE`, `KR_STOCK_UNIVERSE` 분리
- `WATCHLIST_PATH`와 `watchlist.json` 저장 지원
- watchlist entry에 `added_at`, `last_seen_at`, `last_action`, `consecutive_weak_runs`, `active` 저장
- `WATCHLIST_MAX_WEAK_RUNS` 기준 제거 정책 지원
- 실제 뉴스/시장 데이터 소스는 단계적으로 개선하되, 현재는 `yfinance + Google News RSS`를 유지

## 새 우선순위

1. universe/source와 dynamic watchlist 구조 반영
2. 실행 결과와 watchlist 상태 저장 품질 점검
3. OpenAI 실제 제한 스캔 품질 검증
4. threshold 조정
5. GitHub Actions 실제 1회 검증

## Phase 2 Placeholder 범위

### Macro Agent

예정 출력:

- `market_regime`
- `macro_score`
- `market_summary`
- `risk_flags`
- `recommended_posture`

### Sector Strength

예정 필드:

- `sector_name`
- `sector_relative_strength`
- `sector_trend_label`

### Performance Tracking

예정 필드:

- 추천일
- 추천 종가
- 5/10/20일 후 수익률
- 최대 상승폭
- 최대 낙폭

### 기타

- 조건별 성과 비교 기본 구조
- 포트폴리오 비중 제안 placeholder

## Definition Of Done

- 필수 디렉터리 구조가 생성되어 있다.
- Phase 1 모듈이 import 가능하고 실행 가능하다.
- workflow 수동/스케줄 트리거가 정의되어 있다.
- Telegram 테스트 메시지가 전송된다.
- JSON 결과가 저장된다.
- 후보 없음 시나리오가 정상 출력된다.
- README와 샘플 결과가 포함된다.
