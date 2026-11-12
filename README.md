# 미니 PJT: 전자제품 AS 접수 Agent

## 무엇을 푸나
고장 난 전자제품의 AS를 신청하려는 소비자가 콜센터를 기다리지 않고 채팅으로 자가 조치를 안내받거나, 기사 배정과 방문 날짜 확정까지 한 번에 끝낸다.

## 활용한 패턴 (Day 1~7)
- Day 1: LCEL chain + Pydantic 구조화 출력 — `prompt | llm.with_structured_output(...)`로 접수 정보 추출(IntakeSlots), 가드 판정(GuardResult), 평가 판정(JudgeResult)을 dict로 반환 (`src/chains.py`)
- Day 2: RAG — FAQ Markdown을 `##` 헤더 단위로 청킹, Titan v2 임베딩, Chroma 저장, 제품군 메타데이터 필터 검색 (`src/retriever.py`)
- Day 3: LangGraph 조건 분기 — 대화 단계(stage)에 따라 상담 / 해결 확인 / 접수 / 조회로 라우팅, SQLite 체크포인터로 대화 기억 (`src/agent.py`)
- Day 4: MCP 서버 연동 — FastMCP로 도메인 도구 6종 노출, 그래프는 MCP 클라이언트로 호출 (`src/mcp_server.py`)
- Day 5: 가드레일 — 정규식 1차 + LLM 2차로 인젝션·무관 질문·욕설 차단, 차단 후에도 대화 계속 (`src/guards.py`)
- Day 5: HITL — 방문 일정 확정 전 `interrupt()`로 그래프를 멈추고 고객 승인을 받음, 거절 시 최대 3회 재제안
- Day 5: 마스킹 — 주민번호·카드번호·전화번호를 대화 기록·로그·LLM 전달 전에 가림 (그래프 진입 전 전처리)
- Day 7: 평가 — 인-아웃 세트 LLM-as-Judge + RAGAS 4지표 + 배정 정확도 + 가드 차단율 (`evaluation/run_eval.py`)

## 아키텍처
```
Streamlit 화면 · CLI · POST /query ──▶ run_turn()  (전화번호 원문 분리 + PII 마스킹)
                                          │
                                          ▼
                     begin ─▶ guard (정규식 → LLM)  ──(차단)──▶ 안내 문구, 대화 계속
                                          │
              ┌──────────────┬────────────┼──────────────────┐
              ▼              ▼            ▼                  ▼
          consult      resolve_check    lookup             intake
     FAQ 검색(MCP)·답변   해결/미해결    진행 접수 조회     정보 추출(LLM)·형식 검증(파이썬)
              │              │                               │
              └──(미해결)────┴──────────────▶ check_duplicate (MCP) ──(중복)──▶ 기존 접수 안내
                                                             │
                                                             ▼
                                         assign (MCP: 규칙 배정 / 가장 빠른 날짜)
                                                             │
                                                             ▼
                                       propose ─▶ hitl: interrupt() 고객 승인 대기
                                                    │승인          │거절(최대 3회)
                                                    ▼              ▼
                                           save_ticket 예약확정   재제안 → 초과 시 '대기' 저장
```
- LLM이 하는 일: 자가 조치 답변 생성(FAQ 근거만), 접수 정보 추출, 가드 2차 판정
- 파이썬이 하는 일: 라우팅, 해결·승인 판정, 형식 검증, 중복 확인, 기사 배정 규칙, 저장
- 데이터: `data/faq/*.md`(FAQ 35건), `data/technicians.json`(기사 10명), `data/tickets.json`(접수 이력) — 모두 가상 데이터

## 실행 방법
```bash
# 0) 준비 (miniPjt 폴더, Python 3.14)
pip install -r requirements.txt
cp .env.example .env            # AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION 입력
python -m src.make_data         # 기사·접수 데이터 초기화 (테스트 후 되돌릴 때도 사용)
python -m src.retriever         # FAQ 벡터 인덱스 생성 (최초 1회, FAQ 수정 시 --rebuild)

# 1) 화면
streamlit run src/app.py        # 웹 채팅 http://localhost:8501
python -m src.cli               # 터미널 채팅

# 2) API (표준 규약 POST /query)
sh run.sh                       # = uvicorn src.api:app --port 8000, 테스트 페이지 http://localhost:8000/docs
curl -X POST localhost:8000/query -H "Content-Type: application/json" -d '{"question": "TV 전원이 안 켜져요"}'
#   이어서 대화: 응답 헤더 X-Thread-Id 값을 Body의 "thread_id"로 함께 보냄

# 3) 검증·평가
python -m src.scenarios         # 데모 시나리오 5개 자동 검증 (실패 시 종료 코드 1)
python evaluation/run_eval.py   # 4개 항목 평가 → evaluation/results/*.csv, summary.json
python evaluation/run_eval.py --only assign,guard   # 일부만
```

## RAGAS 평가 결과
1차 (2026-11-12, `data/eval_rag.json` 20건)
- context_recall: 0.65
- context_precision: 0.65
- faithfulness: 0.65
- answer_relevancy: 0.33

> `ragas` 0.4.3이 Python 3.14에서 설치·실행되지 않아(의존 패키지 scikit-network 빌드 실패, langchain_community 호환 오류)
> `evaluation/rag_metrics.py`에서 RAGAS와 같은 정의로 직접 계산했다 (판정 Haiku 4.5, 임베딩 Titan v2).
> 20건 중 13건은 recall·precision·faithfulness 1.0이고, 7건은 검색 단계에서 문서를 받지 못해 0점이다 (분석: `evaluation/round1_report.md`).

## 인-아웃 세트 통과율 (자체 평가)
- 1차 (Day 9 종료): 17 / 20 통과 (85%, 목표 90% 미달) — 실패: #8 미해결 시 접수 안내 누락, #9 지원 외 제품 안내 없음, #17 재접수 안내 문구 부족
- 2차 (Day 10 개선 후): XX / XX 통과
- 개선폭: +XX 건 (주요 개선 사항: ...)

그 밖의 1차 지표: 기사 배정 정확도 15/15 (100%) · 가드레일 차단율 20/20 (100%) · 오차단률 0/10 (0%) · 시나리오 5/5

## 트라이앤에러 회고
- 시도했지만 실패한 접근 · 왜 실패했는가
  - `ragas` 라이브러리 사용 → Python 3.14에서 의존 패키지 빌드 실패와 langchain_community 호환 오류로 동작하지 않음. 같은 정의로 직접 구현
  - 검색 "맞는 FAQ 없음" 기준을 FAQ 문구에 가까운 질문으로만 정함(거리 0.85) → 고객이 바꿔 말한 질문 7건을 버림. 기준을 올리면 답이 없어야 할 질문까지 통과해 단순 조정으로는 해결 불가
  - 승인 판정에 "네"를 그대로 사용 → "애매하네요"를 승인으로 오인해 예약 확정. 문장 맨 앞 단독일 때만 승인으로 수정
  - 병렬 평가에서 MCP 도구를 여러 스레드가 동시에 호출 → 교착으로 12분 정지. 호출을 잠금으로 직렬화
- 최종 채택한 접근 · 왜 그것으로 갔는가
  - 기사 배정·해결/승인 판정·형식 검증은 LLM이 아닌 파이썬 규칙 → 결과가 매번 같고 정답 대조로 검증 가능 (배정 100%)
  - 방문 일정 확정은 `interrupt()` 기반 HITL → 고객 승인 없이 예약이 저장되지 않음을 시나리오로 확인
  - 가드레일은 정규식 1차 + LLM 2차 → 명백한 공격은 빠르게, 변형 공격은 LLM으로 (차단 100%, 오차단 0%)
- 남은 한계 · 향후 개선 방향
  - (2차 개선 후 작성) 1차 계획: BM25 하이브리드 검색, 제품 동의어 보강, 지원 외 제품 분기, 안내 문구 보완

## 핵심 코드 위치
- `src/agent.py:346` — 메인 에이전트 그래프 (`build_graph`), `src/agent.py:380` — 진입점 `run_turn`
- `src/tools.py` — 도메인 도구 (배정 규칙 `assign_technician`, 중복 확인, 저장), `src/mcp_server.py` — MCP 서버
- `src/retriever.py` — RAG 파이프라인
- `src/guards.py` — 가드레일·마스킹, `src/chains.py` — LCEL 구조화 출력 체인
- `src/api.py` — POST /query, `src/app.py` — Streamlit 화면
- `evaluation/run_eval.py` — 평가, `evaluation/rag_metrics.py` — RAGAS 지표 계산
