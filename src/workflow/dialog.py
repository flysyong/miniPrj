"""대화 제어: 입력을 어느 도메인 노드로 보낼지(라우팅)와 상담 취소."""
import re

from langgraph.graph import END

from src.booking.rules import LOOKUP
from src.consult.products import detect_products
from src.shared.turn import last_user_text, say, step
from src.workflow.state import RESET_FIELDS

# 접수 취소·상담 거부 의사 (어느 단계에서든 처리 중단 → 마무리 인사 → 초기 상태)
CANCEL = (r"취소|그만\s?(할|하|둘|두)|그만할|안\s?할\s?(래|게)|접수\s?안\s?(할|해)|필요\s?없|상담\s?(종료|끝)"
          r"|종료\s?(할|해)|끝낼|나중에\s?(할|다시)|됐어요,?\s?(그냥|안)|그냥\s?(됐|안\s?할)")
FAREWELL = "요청하신 대로 상담을 종료할게요. 진행 중이던 내용은 저장하지 않았습니다. 이용해 주셔서 감사합니다. 도움이 필요하시면 언제든 다시 말씀해 주세요."


def begin(state: dict) -> dict:
    """턴 시작: 이번 턴 기록을 비운다."""
    return {"trace": None, "contexts": None}


def route(state: dict) -> str:
    """이번 입력을 처리할 노드를 고른다 (파이썬 규칙)."""
    text, stage = last_user_text(state), state.get("stage")
    if stage == "intake":
        return "intake"
    if state.get("turn_phone"):
        return "lookup" if re.search(LOOKUP, text) and not detect_products(text) else "intake"
    if stage == "resolve_check":
        return "resolve_check"
    return "consult"


def after_guard(state: dict) -> str:
    """가드 통과 후: 취소 의사면 cancel, 아니면 단계별 노드로."""
    if state.get("hitl_result") == "blocked":
        return END
    return "cancel" if re.search(CANCEL, last_user_text(state)) else route(state)


def cancel(state: dict) -> dict:
    """고객이 취소·상담 거부 의사를 보이면 저장 없이 마무리 인사를 하고 상담 상태를 처음으로 되돌린다."""
    return say(FAREWELL, **{**RESET_FIELDS, "stage": "done", "status": "상담 종료"},
               trace=[step("cancel", last_user_text(state), "취소 의사 → 저장 없이 종료, 상태 초기화")])
