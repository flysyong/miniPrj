# TASKS

기준: SERVICE.md, as_callcenter.seed.yaml (v1.2.1). 한 번에 작업 하나만 진행하고, 완료 조건을 확인한 뒤 체크한다.
진행 방식: T4에서 화면을 먼저 띄우고, 이후 작업마다 그래프에 기능을 더해 화면에서 바로 확인한다.

## 기반
- [x] **T1. 설정·환경**
  - `src/config.py` (모델 ID·경로를 .env에서 읽는 유일한 모듈), `.env.example`, `src/__init__.py`
  - 완료: `python -c "from src.config import settings; print(settings)"` 실행됨, 모델 ID 문자열이 다른 .py에 없음

- [x] **T2. 더미 데이터 생성**
  - `data/faq/*.md` 증상-조치 FAQ 30~50건 (TV·냉장고·세탁기·에어컨·전자레인지, 문서마다 doc_id)
  - `data/technicians.json` 기사 명단·지역·제품군·근무일·날짜별 예약 수
  - `data/tickets.json` 접수 이력
  - test_queries.csv 재현 조건 포함: 010-5555-0001 진행 중 냉장고 접수 / 010-8888-9999 방문완료 냉장고 접수 / 010-4444-5555 진행 중 접수 / 부산 해운대구 세탁기 2026-11-15 가능 기사 없음
  - 완료: JSON 로드 성공, FAQ 파일 30건 이상

- [x] **T3. RAG 파이프라인** (`src/retriever.py`)
  - Markdown 청킹 → Titan v2 임베딩 → Chroma 저장·검색, 결과에 doc_id·text 포함
  - 참고: day2_practice/chunking_md.py, vectorstore.py
  - 완료: "TV 전원이 안 켜져요" 검색 시 TV 전원 FAQ가 상위에 나옴

## 화면 먼저 (여기부터 화면 테스트 가능)
- [x] **T4. 그래프 v1 (FAQ 상담) + 화면** (`src/agent.py`, `src/app.py`, `src/cli.py`)
  - 그래프: FAQ 검색 → 자가 조치 안내 → 해결 여부 질문 → 해결되면 종료 (SQLite 체크포인터, temperature=0, FAQ 본문은 구분자로 감싸 데이터로 전달)
  - Streamlit 채팅 화면과 CLI는 그래프만 호출하고 배정·라우팅 로직은 두지 않음
  - 참고: day3_practice/conditional.py
  - 완료: `streamlit run src/app.py`에서 "TV 전원이 안 켜져요" 입력 시 자가 조치 안내가 나옴 (시나리오 ① 화면 확인)

## 기능 추가 (매 단계 화면에서 확인)
- [x] **T5. 접수·배정·HITL** (`src/tools.py`, `src/mcp_server.py`, `src/agent.py` 확장)
  - 도구: search_faq, find_open_ticket, assign_technician, find_earliest_date, save_ticket, update_ticket_status
  - 배정은 파이썬 규칙: 지역+제품군+근무일 → 예약 최소 → 기사 ID 순
  - 접수 정보 추출(LCEL + IntakeSlots), 전화번호·날짜 형식 검증은 파이썬 코드
  - 그래프 확장: 미해결 → 중복 확인 → 배정 → HITL 승인(interrupt) → 확정 / 재제안(최대 3회) / 대기
  - 화면: 승인·거절 버튼(또는 입력)으로 interrupt 재개
  - 참고: day7_practice/mcp_server.py
  - 완료: 화면에서 시나리오 ②정상 예약 ③3회 거절 후 대기 ④중복 접수 차단 확인

- [x] **T6. 가드레일·마스킹** (`src/guards.py`, `src/agent.py` 앞단에 연결)
  - 정규식 + LLM 판정(LCEL + GuardResult), 주민번호·카드번호 마스킹, 전화번호 010-****-1234 표시
  - 참고: day5_practice/guards_input.py, masking_middleware.py
  - 완료: 화면에서 시나리오 ⑤가드 차단 후 대화 계속 확인, 화면·로그 전화번호 마스킹 확인

## 인터페이스·자동 검증
- [x] **T7. API** (`src/api.py`, `run.sh`)
  - POST /query {question, thread_id(선택)} → {answer, contexts, trace}
  - 완료: Seed AC2 verify_command가 API_OK 출력, `http://localhost:8000/docs`에서 호출 확인

- [x] **T8. 시나리오 자동 검증** (`src/scenarios.py`)
  - 화면에서 확인한 5개 시나리오를 화면 없이 자동 실행
  - 완료: `python -m src.scenarios` 5개 통과, 실패 시 종료 코드 0이 아님

## 평가
- [x] **T9. 보조 평가셋** (`data/eval_rag.json` 20, `data/eval_assign.json` 15, `data/eval_guard.json` 30)
  - 완료: 건수 확인, 배정 정답은 T2 데이터와 일치

- [x] **T10. 평가 스크립트** (`evaluation/run_eval.py`)
  - 인-아웃 20건 판정(LCEL + JudgeResult, trace로 도구 확인), RAGAS 4지표, 배정 정확도, 가드 차단율·오차단률
  - 90% 목표 PASS/FAIL 출력, 건별 CSV를 evaluation/results/에 저장
  - 완료: Seed AC4 verify_command가 CSV_OK 출력

- [x] **T11. 1차 평가·문서화**
  - run_eval.py 실행 → `evaluation/round1_report.md` (점수, 실패 케이스 분석), README 실행 방법·RAGAS·1차 통과율·핵심 코드 위치 채우기
  - 완료: Seed AC7 verify_command가 DOCS_OK 출력

## 선택 / 이후
- [ ] **T12. (선택) BM25+kiwipiepy 하이브리드 검색** — 시간 남을 때 T3에 추가
- [ ] **T13. 2차 개선·평가** — 실패 케이스 개선 후 `round2_report.md`, README 2차 통과율·개선폭·회고 작성
