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
- [x] **T12. (선택) BM25+kiwipiepy 하이브리드 검색** — 시간 남을 때 T3에 추가
- [x] **T13. 2차 개선·평가** — 실패 케이스 개선 후 `round2_report.md`, README 2차 통과율·개선폭·회고 작성
- [x] **T15. 상담 취소·종료** (사용자 요청 추가)
  - 고객이 접수 취소·상담 거부 의사("취소할게요", "그만할래요", "필요 없어요" 등)를 보이면 어느 단계에서든 처리를 멈추고 마무리 인사
  - 저장하지 않고(일정 승인 대기 중이어도 '대기' 저장 안 함) 대화 상태를 초기화, 화면은 새 상담으로 전환
  - 완료: 상담·접수 입력·일정 승인 대기 중 각각 취소 시 저장 없이 종료되고, 다음 입력은 새 상담으로 시작
- [x] **T16. 지원하지 않는 제품 판정·안내** (사용자 요청 추가)
  - 지원 5종(TV·냉장고·세탁기·에어컨·전자레인지)이 아닌 제품이면 "해당 제품에 대한 상담과 수리는 지원하지 않습니다. 판매처에 문의하세요." 안내
  - 판정: 1차 파이썬(지원 5종 키워드 / 미지원 키워드) → 2차 LLM(LCEL + ProductCheck)로 목록 밖 제품(형광등 등)까지 판단
  - 첫 상담과 접수 정보 입력 단계 모두 적용, SERVICE.md 4번 정책에 추가
  - 완료: 형광등·보일러·로봇청소기는 미지원 안내, 지원 5종과 제품 언급 없는 문장은 기존대로 진행
- [x] **T17. 제품 별칭 정규화** (사용자 요청 추가)
  - "티브이에 전원이 안 들어와요"가 FAQ를 못 찾고 기사 접수로 빠지는 문제: 별칭(티브이)이 검색에서 TV와 연결되지 않음
  - 검색 전에 제품 별칭을 표준 이름으로 바꿈(파이썬): 티브이·티비·텔레비전·테레비·tv → TV, 에어콘 → 에어컨, 전자렌지·렌지 → 전자레인지, 통돌이 → 세탁기
  - 제품 키워드 인식 목록에도 별칭 추가
  - 완료: 별칭으로 쓴 질문이 표준 이름으로 쓴 질문과 같은 FAQ로 안내됨, 시나리오 회귀 없음
- [x] **T18. 도메인별 폴더 구조 리팩토링** (사용자 요청 추가)
  - `src/` 아래 consult·booking·guard·judge·workflow·shared로 분리, 도메인마다 schemas·prompts·chains·rules·tools·nodes
  - Seed가 고정한 경로(`src/agent.py`, `tools.py`, `retriever.py` 등)는 진입점으로 유지, 규칙은 `CLAUDE.md`
  - 완료: 시나리오 6/6, API_OK, 배정 평가 15/15, Streamlit 화면 로드 확인
- [x] **T19. 서비스 지역 판정·지역 정규화·종료 안내** (사용자 요청 추가, `src/booking/service_area.py`)
  - 지역 담당 기사 없음 / 지역에 해당 제품 담당 기사 없음 → 저장 없이 다음 행동 안내 후 종료 (status 서비스지역외)
  - 담당 기사는 있으나 14일 안에 일정 없음 → '대기' 저장 + 다음 행동 안내 + 마무리 인사
  - 지역 정규화(파이썬): 서울특별시 강남구·서울 강남·강남 → 서울 강남구, 시/도 없는 서구·중구 등은 다시 질문
  - 완료: 수원 영통(지역 없음)·인천 남동구 에어컨(제품 없음) 저장 0건 종료, 강남 → T02 배정, 서구 → 재질문, 시나리오 6/6
- [x] **T20. 증상 단어로 제품 오인 수정** (사용자 요청 추가, `src/consult/products.py`)
  - "탈수기 전원"이 '탈수' 키워드 때문에 세탁기로 접수되던 문제 (식기세척기 배수·건조기 탈수도 동일)
  - 제품 이름과 증상 단어를 분리: 지원 제품 이름 → 미지원 제품 이름(탈수기 추가) → 증상 단어 순으로 판정
  - 완료: 탈수기·식기세척기·건조기는 미지원 안내, "탈수할 때 덜컹거려요"는 세탁기 유지, 시나리오 6/6
- [ ] **T14. 화면 최종 개선** (T13 이후, `src/app.py`)
  - 사이드바의 개발자용 정보(이번 턴 trace, 근거 FAQ, thread_id)는 기본 화면에서 숨기고 `.env`의 `DEBUG_UI=1`일 때만 표시
  - 고객 화면에는 상담 상태와 "새 상담 시작" 버튼만 남김, 그 밖의 레이아웃 정리
  - 완료: 기본 실행 시 개발자 정보가 보이지 않고, DEBUG_UI=1이면 보임
  - (먼저 적용) 블랙 톤 테마 `.streamlit/config.toml` + 회로기판 무늬 배경 `src/assets/bg_circuit.svg` — 사용자 요청
