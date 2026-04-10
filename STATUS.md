# STATUS.md

## 프로젝트 상태

- 프로젝트명: StockAgent
- 현재 단계: Phase 1 기본 구현 완료, 검증 및 정리 진행중
- 마지막 업데이트: 2026-04-11

## 완료된 작업

- `AGENT.md` 작성 완료
- `PLAN.md` 작성 완료
- `.gitignore` 작성 완료
- `app/` 기준 Phase 1 디렉터리 구조 생성 완료
- `config`, `orchestrator`, `schema`, `enum` 기본 구현 완료
- Universe, market data, latest news 수집 모듈 추가 완료
- Screening Engine, Chart Feature Engine 구현 완료
- Chart Agent, News Agent, Final Decision Agent 구현 완료
- Phase 2 placeholder 모듈 생성 완료
- JSON 결과 저장 및 Telegram 포맷터/전송 모듈 추가 완료
- GitHub Actions workflow 추가 완료
- `README.md`, 샘플 결과 JSON 추가 완료
- LLM provider adapter 구조 추가 완료
- `OpenAI`, `Anthropic`, `Gemini` 전환 가능한 설정 추가 완료
- 역할별 LLM 모델 선택 구조 추가 완료
- OpenAI 역할별 기본 모델 조합 적용 완료
- `--self-check`, `--llm-smoke`, `--limit` CLI 추가 완료
- OpenAI `--llm-smoke --llm-role final` 성공 확인 완료
- structured JSON schema 정규화 로직 추가 완료
- LLM fallback 사용 시 결과 내 근거 문구로 표시되도록 개선 완료
- candidate/observe threshold 설정값 분리 완료
- 후보 없음과 관찰만 메시지 분기 로직 수정 완료
- 관찰만일 때 상위 관찰 종목 요약 출력 추가 완료
- Python 3.14 기준 문법 검증 완료
- Python 3.14 기준 self-check 실행 확인 완료
- Python 3.14 기준 1종목 제한 실제 스캔 및 JSON 저장 확인 완료
- Python 기준 버전 3.14로 통일 완료
- `pydantic`를 3.14 호환 버전으로 상향 완료
- 임시 검증용 `.venv312` 제거 완료
- Telegram 테스트 메시지 실전송 검증 완료

## 현재 저장소 상태

- `python3 -m compileall app main.py` 통과
- 프로젝트 Python 기준 버전은 3.14로 통일
- `.venv`는 Python 3.14 환경으로 사용
- `python -m app.main --self-check` 실행 확인 완료
- provider별 역할 모델 self-check 확인 완료
- OpenAI provider의 structured output smoke test 통과
- OpenAI 기본 역할 모델이 `final=gpt-4.1`로 분리된 것 확인 완료
- 제한 스캔에서 `observe_min_final_score=55` 기준으로 관찰 종목 출력 확인 완료
- `run_scan(..., max_stocks=1)` 실행 시 `관찰만` 메시지와 `latest.json` 저장 확인 완료
- GitHub Actions는 Python 3.14 기준으로 설정됨
- Anthropic/Gemini smoke test는 API key 미주입 상태라 미실행
- Telegram bot/chat 설정과 테스트 전송은 검증 완료

## 다음 작업

1. Anthropic/Gemini API key 주입 후 provider별 structured response smoke test 검증
2. 역할별 모델 조합별 smoke test 검증 확장
3. 필요 시 universe/news/source 설정 보강
4. score threshold와 후보/관찰만 기준 조정
5. provider별 오류/재시도 정책 정교화
6. OpenAI 실제 full scan에서 role별 모델 비용/품질 확인

## 메모

- 이 파일은 작업이 진행될 때마다 갱신한다.
- 완료/진행중/대기 상태를 명확히 유지한다.
- 민감정보는 기록하지 않는다.
- 작업은 가능한 한 기능/문서/인프라 단위로 나누어 커밋한다.
- 커밋이 필요한 변경을 했으면 이 파일에 반영 후 커밋 여부도 함께 관리한다.
- LLM orchestration은 현재 순수 Python으로 유지한다.
- `LangChain`, `LangGraph`는 Phase 2에서 실제 복잡도가 커질 때 재검토한다.
- provider 교체 요구는 adapter 패턴으로 수용하고, 초기 대상은 OpenAI/Anthropic/Gemini다.
- 역할별 모델 구조는 provider와 분리된 공통 설정 이름으로 유지한다.
