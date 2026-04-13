# Release v0.1.0

## 범위

- OpenAI 기반 스윙 투자 보조 도구 Phase 1.5 완료 기준
- GitHub Actions 정기 실행
- Telegram 시장별 2건 전송
- 한국/미국 시장 브리핑
- 보유 종목 브리핑
- 신규 후보/관찰 후보 분리
- JSON 저장 및 watchlist 갱신

## 포함 기능

- Python 정량 스크리닝
- LLM 차트/뉴스/최종 판단
- structured JSON 응답 강제
- `discovery universe + watchlist`
- `holdings.json` 기반 보유 종목 반영
- `KR_FLOW_PATH + pykrx optional` 기반 한국 수급 fallback
- 역할별 모델 설정
- GitHub Actions `workflow_dispatch + schedule`

## 운영 기준

- 기본 provider: `openai`
- Python: `3.14`
- Telegram: 한국 시장 / 미국 시장 분리 전송
- 한국 수급: `KR_FLOW_* -> snapshot -> pykrx optional -> fallback`

## 제외 범위

- Anthropic/Gemini 실연동 검증
- 자동매매
- 브로커 연동
- 실시간 주문/체결
- Phase 2 매크로/섹터/성과추적 본구현
