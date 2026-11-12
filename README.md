# 미니 PJT: 전자제품 AS 접수 Agent

## 무엇을 푸나
고장 난 전자제품의 AS를 신청하려는 소비자가 콜센터를 기다리지 않고 채팅으로 자가 조치를 안내받거나, 기사 배정과 방문 날짜 확정까지 한 번에 끝낸다.

## 활용한 패턴 (Day 1~7)
- Day 1: LCEL chain + Pydantic 구조화 출력 — `prompt | llm.with_structured_output(...)`로 접수 정보 추출(IntakeSlots), 제품 판정(ProductCheck), 가드 판정(GuardResult), 평가 판정(JudgeResult)을 dict로 반환 (각 도메인의 `schemas.py`·`prompts.py`·`chains.py`)
- Day 2: RAG — FAQ Markdown을 `##` 헤더 단위로 청킹, Titan v2 임베딩(Chroma) + BM25(kiwipiepy 형태소) 하이브리드 검색, 두 순위를 RRF로 결합, 제품군 메타데이터 필터 (`src/consult/retriever.py`)
- Day 3: LangGraph 조건 분기 — 대화 단계(stage)에 따라 상담 / 해결 확인 / 접수 / 조회로 라우팅, SQLite 체크포인터로 대화 기억 (`src/workflow/`)
- Day 4: MCP 서버 연동 — FastMCP로 도메인 도구 6종 노출, 그래프는 MCP 클라이언트로 호출 (`src/mcp_server.py`)
- Day 5: 가드레일 — 정규식 1차 + LLM 2차로 인젝션·무관 질문·욕설 차단, 차단 후에도 대화 계속 (`src/guard/`)
- Day 5: HITL — 방문 일정 확정 전 `interrupt()`로 그래프를 멈추고 고객 승인을 받음, 거절 시 최대 3회 재제안
- Day 5: 마스킹 — 주민번호·카드번호·전화번호를 대화 기록·로그·LLM 전달 전에 가림 (그래프 진입 전 전처리)
- Day 7: 평가 — 인-아웃 세트 LLM-as-Judge + RAGAS 4지표 + 배정 정확도 + 가드 차단율 (`evaluation/run_eval.py`)

## 아키텍처
> 상세 다이어그램: [`.archify/architecture-as-agent-20261112-150440/as-agent.html`](.archify/architecture-as-agent-20261112-150440/as-agent.html)
> — 노드마다 소스 코드 줄로 연결된 인터랙티브 다이어그램 (내려받아 브라우저로 열기)

```
Streamlit 화면 · CLI · POST /query ──▶ run_turn()  (전화번호 원문 분리 + PII 마스킹)
                                          │
                                          ▼
                     begin ─▶ guard (정규식 → LLM)  ──(차단)──▶ 안내 문구, 대화 계속
                                          │
                                          ├──(취소 의사, 어느 단계든)──▶ cancel: 저장 없이 마무리 인사, 상태 초기화
              ┌──────────────┬────────────┼──────────────────┐
              ▼              ▼            ▼                  ▼
          consult      resolve_check    lookup             intake
     제품 판정(규칙→LLM)   해결/미해결    진행 접수 조회     정보 추출(LLM)·형식 검증·지역 정규화(파이썬)
      ├ 미지원 제품 → 판매처 문의 안내                      ├ 담당 기사 없는 지역 → 저장 없이 안내 후 종료
      ├ 안전 증상 → 사용 중지 안내 → 바로 intake             │
      └ FAQ 검색(MCP)·답변                                   │
              │              │                               │
              └──(미해결)────┴──────────────▶ check_duplicate (MCP) ──(중복)──▶ 기존 접수 안내
                                                             │
                                                             ▼
                                         assign (MCP: 규칙 배정 / 가장 빠른 날짜, 14일 내 없으면 '대기')
                                                             │
                                                             ▼
                                       propose ─▶ hitl: interrupt() 고객 승인 대기
                                                    │승인          │거절(최대 3회)
                                                    ▼              ▼
                                           save_ticket 예약확정   재제안 → 초과 시 '대기' 저장
```
- LLM이 하는 일: 자가 조치 답변 생성(FAQ 근거만), 접수 정보 추출, 제품 판정 2차, 가드 2차 판정
- 파이썬이 하는 일: 라우팅·취소, 해결·승인 판정, 형식 검증, 지역 정규화·서비스 지역 판정, 중복 확인, 기사 배정 규칙, 저장
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
python -m src.scenarios         # 데모 시나리오 6개 자동 검증 (실패 시 종료 코드 1)
python evaluation/run_eval.py   # 4개 항목 평가 → evaluation/results/*.csv, summary.json
python evaluation/run_eval.py --only assign,guard   # 일부만
```

## RAGAS 평가 결과
2차 최종 (2026-11-12, `data/eval_rag.json` 20건, 괄호는 1차)
- context_recall: 0.95 (0.65)
- context_precision: 0.95 (0.65)
- faithfulness: 0.95 (0.65)
- answer_relevancy: 0.43 (0.33)

> `ragas` 0.4.3이 Python 3.14에서 설치·실행되지 않아(의존 패키지 scikit-network 빌드 실패, langchain_community 호환 오류)
> `evaluation/rag_metrics.py`에서 RAGAS와 같은 정의로 직접 계산했다 (판정 Haiku 4.5, 임베딩 Titan v2).
> 1차는 바꿔 말한 질문 7건이 검색 단계에서 버려져 0.65였고, BM25 하이브리드 검색으로 6건을 회복해 0.95가 되었다.
> 검색 성공 건은 recall·precision·faithfulness 모두 1.0 (분석: `evaluation/round1_report.md`, `round2_report.md`).

## 인-아웃 세트 통과율 (자체 평가)
- 1차 (Day 9 종료): 17 / 20 통과 (85%, 목표 90% 미달) — 실패: #8 미해결 시 접수 안내 누락, #9 지원 외 제품 안내 없음, #17 재접수 안내 문구 부족
- 2차 (Day 10 개선 후): 18 / 20 통과 (90%, **목표 달성**) — 남은 실패 #9·#11은 답변 판정은 통과, 정책 변경으로 기대 도구(search_faq)를 호출하지 않아 실패
- 개선폭: +1 건 (주요 개선 사항: BM25 하이브리드 검색, 미해결 시 접수 안내 문구, 새 접수 안내 문구, 지원 외 제품 분기 → #8·#17 회복 / 안전 증상 정책으로 #11은 검색을 건너뛰어 실패로 바뀜)
- 참고 (2차 이후, 평가 기준 정리): #9·#11의 기대값을 바뀐 정책(미지원 제품 → 판매처 문의, 안전 증상 → 검색 없이 바로 접수)에 맞게 고친 뒤 재평가 20 / 20 (100%).
  코드 개선이 아니라 **평가 기준을 갱신한 결과**이며, 위 1차·2차 수치는 당시 기준 그대로 둔다 (변경 내용: TASKS.md T21)

그 밖의 지표 (1차 → 2차): 기사 배정 정확도 15/15 → 15/15 · 가드레일 차단율 20/20 → 20/20 · 오차단률 0/10 → 0/10 · 시나리오 5/5 → 5/5
(최종 제출본 기준: 배정 15/15 · 시나리오 6/6 — 상담 취소 시나리오 추가)

## 트라이앤에러 회고
- 시도했지만 실패한 접근 · 왜 실패했는가
  - `ragas` 라이브러리 사용 → Python 3.14에서 의존 패키지 빌드 실패와 langchain_community 호환 오류로 동작하지 않음. 같은 정의로 직접 구현
  - 검색 "맞는 FAQ 없음" 기준을 FAQ 문구에 가까운 질문으로만 정함(거리 0.85) → 고객이 바꿔 말한 질문 7건을 버림. 기준을 올리면 답이 없어야 할 질문까지 통과해 단순 조정으로는 해결 불가
  - 승인 판정에 "네"를 그대로 사용 → "애매하네요"를 승인으로 오인해 예약 확정. 문장 맨 앞 단독일 때만 승인으로 수정
  - 병렬 평가에서 MCP 도구를 여러 스레드가 동시에 호출 → 교착으로 12분 정지. 호출을 잠금으로 직렬화
  - 하이브리드 검색으로 "세탁기 타는 냄새·연기"까지 "세탁 후 냄새" FAQ에 연결됨 → 검색 점수로는 구분 불가. 안전 증상은 검색 대신 정책(사용 중지 안내 후 바로 접수)으로 처리
- 최종 채택한 접근 · 왜 그것으로 갔는가
  - 기사 배정·해결/승인 판정·형식 검증은 LLM이 아닌 파이썬 규칙 → 결과가 매번 같고 정답 대조로 검증 가능 (배정 100%)
  - 방문 일정 확정은 `interrupt()` 기반 HITL → 고객 승인 없이 예약이 저장되지 않음을 시나리오로 확인
  - 가드레일은 정규식 1차 + LLM 2차 → 명백한 공격은 빠르게, 변형 공격은 LLM으로 (차단 100%, 오차단 0%)
  - 검색은 벡터 + BM25 하이브리드, "두 검색이 같은 문서를 1위로 고르면 거리 기준 완화" → 바꿔 말한 질문은 살리고 답이 없어야 할 질문은 계속 거름 (RAGAS 0.65 → 0.95)
- 남은 한계 · 향후 개선 방향
  - 검색 기준값을 평가셋 측정값으로 정해 처음 보는 질문에서는 성능이 낮을 수 있음 → 별도 검증용 질문 세트로 일반화 확인 필요
  - 안전 증상 판정은 아직 정규식뿐이라 목록에 없는 표현("스파크", "지지직 타는 소리")을 놓칠 수 있음 → LLM 2차 확인 추가 필요
    (지원 외 제품 판정은 규칙 1차 + LLM 2차로 보완 완료)
  - 평가셋 #9·#11의 기대값이 초기 설계(항상 FAQ 검색) 기준이라 바뀐 정책과 어긋났음 → 기준 정리 완료(20/20). 다만 정책을 바꿀 때마다 평가셋을 함께 고치는 절차가 필요
  - 평가셋 20건이 작아 1건이 5%p → 케이스 확대 필요

## 핵심 코드 위치
- `src/agent.py:5` — 메인 에이전트 그래프 (진입점, 구현: `src/workflow/graph.py:35` `build_graph`, `src/workflow/graph.py:70` `run_turn`)
- `src/tools.py` — 도메인 도구 (MCP 도구 6종 모음, 구현: `src/consult/tools.py` `search_faq`, `src/booking/tools.py:39` `assign_technician` 외)
- `src/retriever.py` — RAG 파이프라인 (진입점, 구현: `src/consult/retriever.py`)

그 밖의 위치 — 소스는 도메인별 폴더로 나뉘어 있다 (폴더 규칙은 `CLAUDE.md`):
- `src/consult/` — FAQ 상담: 제품 판정(`products.py`), RAG 검색, 자가 조치 답변
- `src/booking/` — 접수·배정: 중복 확인, 저장, 서비스 지역(`service_area.py`), HITL 승인(`nodes.py:157` `hitl`)
- `src/guard/` — 가드레일(`rules.py`)·마스킹(`masking.py`), `src/judge/` — 평가 판정 체인
- `src/shared/` — 공통 LLM 클라이언트(`llm.py`), `src/mcp_server.py` — MCP 서버(도구 6종은 `src/tools.py`에 모음)
- `src/api.py` — POST /query, `src/app.py` — Streamlit 화면
- `evaluation/run_eval.py` — 평가, `evaluation/rag_metrics.py` — RAGAS 지표 계산
