"""메인 에이전트 그래프 (LangGraph): 각 도메인의 노드를 하나의 흐름으로 연결한다.

흐름: begin → guard(차단 시 안내 후 종료, 대화는 계속) → (단계별 분기, workflow/dialog.py)
  consult       : FAQ 검색(MCP search_faq) → 자가 조치 안내 → stage=resolve_check     [consult/nodes.py]
  resolve_check : 해결 → 종료 / 미해결 → 접수 정보 요청                                [consult/nodes.py]
  lookup        : 전화번호로 진행 중 접수 조회                                          [booking/nodes.py]
  intake        : 접수 정보 추출(LCEL+IntakeSlots)·형식 검증 → 다 모이면 중복 확인으로    [booking/nodes.py]
  check_duplicate → assign → propose → hitl(interrupt: 고객 승인)                     [booking/nodes.py]
     hitl 승인 → 예약확정 저장 / 거절 → 가장 빠른 날짜 재제안(최대 3회) → 초과 시 '대기' 저장
  cancel        : 어느 단계에서든 취소 의사 → 저장 없이 종료                            [workflow/dialog.py]

한 번의 사용자 입력 = 그래프 1회 실행(1턴). 단계는 state["stage"]에, 대화는 SQLite 체크포인터에 thread_id별로 저장.
방문 일정 승인은 interrupt()로 그래프를 멈추고, 다음 입력이 오면 Command(resume=입력)로 이어간다.
화면(app.py)·CLI(cli.py)·API(api.py)는 run_turn()만 호출한다.
"""
import sqlite3
import threading

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.booking.nodes import (after_assign, after_duplicate, after_hitl, after_intake, assign, check_duplicate,
                               hitl, intake, lookup, propose)
from src.config import settings
from src.consult.nodes import after_resolve, consult, resolve_check
from src.guard.masking import find_phone, mask_pii
from src.guard.nodes import guard
from src.shared.llm import text_of
from src.workflow.dialog import after_guard, begin, cancel
from src.workflow.state import RESET_FIELDS, State


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("begin", begin), ("guard", guard), ("consult", consult), ("resolve_check", resolve_check), ("lookup", lookup),
                     ("intake", intake), ("check_duplicate", check_duplicate), ("assign", assign),
                     ("propose", propose), ("hitl", hitl), ("cancel", cancel)]:
        g.add_node(name, fn)
    g.add_edge(START, "begin")
    g.add_edge("begin", "guard")
    g.add_conditional_edges("guard", after_guard, ["consult", "resolve_check", "lookup", "intake", "cancel", END])
    g.add_edge("cancel", END)
    g.add_conditional_edges("resolve_check", after_resolve, ["consult", END])
    g.add_conditional_edges("intake", after_intake, ["check_duplicate", END])
    g.add_conditional_edges("check_duplicate", after_duplicate, ["assign", END])
    g.add_conditional_edges("assign", after_assign, ["propose", END])
    g.add_edge("propose", "hitl")
    g.add_conditional_edges("hitl", after_hitl, ["propose", "hitl", END])
    g.add_edge("consult", END)
    g.add_edge("lookup", END)
    return g.compile(checkpointer=checkpointer)


_graph = None
_graph_lock = threading.Lock()


def get_graph():
    """SQLite 체크포인터를 붙인 그래프 (프로세스당 1개)."""
    global _graph
    with _graph_lock:
        if _graph is None:
            conn = sqlite3.connect(settings.checkpoint_db, check_same_thread=False)
            _graph = build_graph(SqliteSaver(conn))
    return _graph


def run_turn(thread_id: str, text: str) -> dict:
    """사용자 입력 1건을 처리하고 API 규약 형태로 돌려준다.

    반환: {"answer", "question"(마스킹본), "contexts": [{doc_id, text}], "trace": [{step, input, output}], "status", "stage"}
    """
    graph = get_graph()
    cfg = {"configurable": {"thread_id": thread_id}}
    phone, masked = find_phone(text), mask_pii(text)   # 전화번호 원문은 따로, 대화·로그·LLM에는 마스킹본
    snap = graph.get_state(cfg)
    if snap.interrupts:
        # 방문 일정 승인 대기 중 → 고객 답변으로 재개 (이번 턴 기록만 잘라서 반환)
        before = len(snap.values.get("trace", []))
        out = graph.invoke(Command(resume=masked), cfg)
        trace = out.get("trace", [])[before:]
        contexts = []
    else:
        if snap.values.get("stage") == "done":
            # 이전 상담이 끝난 대화에 새 입력이 오면 새 상담으로 시작
            graph.update_state(cfg, RESET_FIELDS)
        out = graph.invoke({"messages": [HumanMessage(masked)], "turn_phone": phone}, cfg)
        trace, contexts = out.get("trace", []), out.get("contexts", [])
    return {
        "answer": text_of(out["messages"][-1]),
        "question": masked,                       # 화면 표시용 (마스킹된 입력)
        "contexts": contexts,
        "trace": trace,
        "status": out.get("status", ""),
        "stage": out.get("stage", ""),
    }
