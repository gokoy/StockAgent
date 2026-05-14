# 시장 발표 달력

`/calendar`의 월간 달력에는 날짜가 공식/정형적으로 확인되는 고정 발표만 넣는다. 뉴스성 이벤트는 달력에 섞지 않고 유동 이벤트 탭에서 관리한다.

자동 수집 대상:

- Federal Reserve FOMC calendar
- BEA release schedule: GDP, Personal Income and Outlays, U.S. International Trade

BLS는 공식 사이트가 자동 요청을 차단할 수 있어 현재 자동 수집 대상에서 제외한다. CPI, 고용, PPI, JOLTS 등은 추후 허용 가능한 공식 캘린더 피드가 확보되면 추가한다.

## 데이터 파일

- 경로: `data/web/calendar/YYYY-MM.json`
- 형식:

```json
{
  "month": "2026-05",
  "events": [
    {
      "date": "2026-05-13",
      "time_kst": "21:30",
      "market": "US",
      "category": "물가",
      "title": "미국 CPI",
      "importance": "high",
      "source_name": "BLS",
      "source_url": "https://www.bls.gov/schedule/news_release/cpi.htm",
      "why_it_matters": "물가 둔화 여부는 금리 기대와 성장주 밸류에이션에 직접 영향을 준다."
    }
  ]
}
```

`data/web/market_calendar.json`은 이전 단일 파일 구조와의 호환을 위해 남겨둔다. 새 데이터는 월별 파일에 넣는다.

자동 수집 이벤트는 `source_type: "auto_fixed"`가 붙는다. 사람이 추가한 이벤트는 이 필드를 생략하면 다음 자동 갱신 때 보존된다.

## 필드

- `date`: `YYYY-MM-DD`
- `time_kst`: 한국시간. 미확정이면 `TBD` 또는 빈 문자열
- `market`: `US`, `KR`, `GLOBAL`
- `category`: `정책`, `물가`, `고용`, `성장`, `소비`, `금리/수급`, `실적`, `원자재`
- `importance`: `high`, `medium`, `low`
- `source_name`, `source_url`: 공식 출처 또는 거래소/회사 IR 링크
- `why_it_matters`: 시장 영향 한 줄 설명

## 미국 고정 발표

`high`

- FOMC 기준금리 결정, 점도표, 의장 기자회견
- CPI/Core CPI
- PCE/Core PCE
- 비농업고용, 실업률, 시간당 임금
- GDP 속보/수정/확정치
- ISM 제조업/서비스업 PMI
- 소매판매
- 주요 빅테크/반도체/금융 실적

`medium`

- PPI
- JOLTS 구인건수
- 주간 실업수당 청구
- 내구재 주문
- 산업생산
- 미시간대 소비심리와 기대인플레이션
- 무역수지
- EIA 원유재고
- 10년/30년 국채 입찰

## 한국 고정 발표

`high`

- 한국은행 금통위 기준금리 결정과 총재 기자간담회
- 한국 CPI
- 월간 수출입 동향
- GDP 속보/잠정치
- 삼성전자, SK하이닉스, 현대차 등 지수 영향 큰 실적
- 선물/옵션 동시만기
- MSCI/FTSE 정기 리밸런싱 적용일

`medium`

- 산업활동동향
- 고용동향
- 생산자물가
- 소비자동향조사
- 기업경기실사지수
- 국제수지
- 외환보유액
- 금융통화위원 의사록
- 단일 옵션만기일

## 주요 출처

- Federal Reserve FOMC calendar
- BLS release calendar
- BEA release calendar
- Census Bureau release schedule
- ISM report calendar
- EIA weekly petroleum status report
- U.S. Treasury auction calendar
- 한국은행 보도자료/통화정책 일정
- 통계청 보도자료 일정
- 산업통상자원부 수출입 동향
- 한국거래소 파생상품/시장 일정
- 회사 IR 일정
