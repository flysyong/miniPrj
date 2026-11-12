# 작업 규칙
- 무엇을 만드는지는 SERVICE.md가, 세부 규칙과 완료 검증은 as_callcenter.seed.yaml이 기준이다. 애매하면 추측하지 말고 물어본다.
- 스택: Python, LangGraph, Bedrock (메인 us.anthropic.claude-sonnet-4-5-20250929-v1:0, 판정·가드 global.anthropic.claude-haiku-4-5-20251001-v1:0) -> 필요 시 모델은 조정해서 사용하거나 복수의 모델을 상황에 맞춰 변경하여 중단없이 쓸 수 있게 한다.
- 괜찮은 레퍼런스 코드를 깃허브에서 찾아서 레퍼런스로 삼거나 (있을 경우) 현재 ref 폴더 내 코드를 참조한다. 절대 사용자의 허락없이 신규 프레임워크 또는 라이브러리를 들이지 않는다.
- 한 번에 TASKS.md의 작업 하나만 한다.
- 계산, 규칙 판정은 LLM이 아니라 파이썬 코드로 하는 원칙으로 진행한다. 필요시 LLM 판정부분을 덧붙여 추가한다.
- API 키는 .env에서 읽는다.

# 소스 폴더 구조 (src/, 도메인별)
기술 역할(utils, models)이 아니라 상담 업무 단위(도메인)로 나눈다. 모든 소스는 `src/` 안에 둔다
(예외: Seed가 고정한 `evaluation/run_eval.py`, `evaluation/rag_metrics.py`).

| 폴더 | 역할 |
|---|---|
| `src/consult/` | FAQ 상담: 제품 판정(지원 5종·별칭·미지원), RAG 검색, 자가 조치 답변, 해결 여부 확인 |
| `src/booking/` | AS 접수·배정: 접수 정보 추출·검증, 진행 조회, 중복 확인, 기사 배정, 일정 제안·승인(HITL), 더미 데이터 |
| `src/guard/` | 입력 가드레일(인젝션·무관 질문·욕설)과 개인정보 마스킹 |
| `src/judge/` | 평가 판정(LLM-as-Judge), evaluation/run_eval.py가 사용 |
| `src/workflow/` | 대화 흐름: 그래프 상태, 라우팅·취소, 노드 연결(build_graph), run_turn |
| `src/shared/` | 여러 도메인이 같이 쓰는 것만: LLM 클라이언트(`llm.py`), 노드 도우미(`turn.py`: step·say·last_user_text) |
| `src/assets/` | 화면용 정적 파일(배경 SVG) |

## 도메인 폴더 안 파일 배치 규칙 (필요한 파일만 만든다)
- `schemas.py` — Pydantic 입출력 스키마 (LLM 구조화 출력 모델)
- `prompts.py` — 프롬프트 템플릿, 고객에게 보내는 고정 안내 문구
- `chains.py` — LCEL 체인 (`prompt | llm.with_structured_output(스키마)`)
- `rules.py` — 파이썬 규칙 (정규식·형식 검증·판정). 계산·규칙 판정은 여기에 둔다
- `tools.py` — MCP로 노출하는 도구 함수 (`src/tools.py`에 모아 `src/mcp_server.py`가 노출)
- `nodes.py` — 그래프 노드 함수 (도메인의 실행 로직). 그래프 연결은 `workflow/graph.py`에서만 한다
- 도메인 고유 모듈은 이름을 그대로 쓴다 (`consult/retriever.py`, `consult/products.py`, `guard/masking.py`, `booking/sample_data.py`, `booking/service_area.py`)

## src/ 바로 아래 파일 (진입점, 경로를 바꾸지 않는다)
- Seed·제출 규약이 경로를 고정했다: `config.py`(모델 ID를 가진 유일한 모듈), `agent.py`, `tools.py`, `retriever.py`,
  `mcp_server.py`, `api.py`, `app.py`, `cli.py`, `scenarios.py`, `make_data.py`
- `agent.py`·`tools.py`·`retriever.py`·`make_data.py`는 도메인 코드를 다시 내보내기만 한다. 로직을 여기에 쓰지 않는다

## 의존 방향
- 도메인끼리는 필요한 것만 직접 import한다 (예: booking → consult.products, guard.masking)
- `shared/`는 다른 도메인을 import하지 않는다. `workflow/state.py`·`dialog.py`는 다른 도메인의 nodes를 import하지 않는다 (순환 방지)
- 도메인 노드는 MCP 도구를 `src.mcp_server.call_tool`로 호출한다. MCP 도구는 Seed가 정한 6종만 두고,
  그 밖의 읽기 전용 규칙(예: `booking/service_area.py`)은 노드가 직접 import한다
