"""가드레일 그래프 노드: 매 턴 입력을 먼저 검사한다."""
from src.guard.prompts import GUARD_MESSAGES
from src.guard.rules import check_input
from src.shared.turn import last_user_text, say, step


def guard(state: dict) -> dict:
    """입력 가드레일: 인젝션·무관 질문·욕설은 안내 문구로 답하고 이번 턴을 끝낸다 (단계는 그대로 유지)."""
    text = last_user_text(state)
    r = check_input(text, state.get("stage"))
    trace = [step("guard", text, f"차단 · {r['category']} ({r['by']}) · {r['reason']}" if r["blocked"] else "통과")]
    if r["blocked"]:
        return say(GUARD_MESSAGES[r["category"]], trace=trace, hitl_result="blocked")
    return {"trace": trace, "hitl_result": None}
