"""접수 그래프 노드: 조회 → 접수 정보 → 중복 확인 → 배정 → 제안 → 승인(HITL interrupt) → 확정/재제안/대기."""
import re

from langchain_core.messages import HumanMessage
from langgraph.graph import END
from langgraph.types import interrupt

from src.booking.chains import extract_intake
from src.booking.prompts import ASK_REGION_CITY, out_of_area_message, waiting_message
from src.booking.rules import APPROVE, MAX_REPROPOSALS, PHONE_OK, REJECT, SLOT_LABELS, fmt_date, valid_date
from src.booking.service_area import coverage, known_regions, normalize_region
from src.consult.products import PRODUCTS, detect_products, product_gate, unsupported_message
from src.guard.masking import mask_phone
from src.guard.prompts import GUARD_MESSAGES
from src.guard.rules import check_input
from src.mcp_server import call_tool
from src.shared.turn import last_user_text, say, step
from src.workflow.dialog import CANCEL, FAREWELL
from src.workflow.state import RESET_FIELDS


def lookup(state: dict) -> dict:
    """전화번호로 진행 중인 접수를 조회한다."""
    phone = state["turn_phone"]
    rows = call_tool("find_open_ticket", phone=phone)
    trace = [step("find_open_ticket", mask_phone(phone), [r["ticket_id"] for r in rows] or "없음")]
    if not rows:
        return say(f"{mask_phone(phone)} 번호로 진행 중인 접수가 없습니다.", trace=trace)
    lines = [f"- 접수번호 {r['ticket_id']} · {r['product']} · {r['status']}"
             + (f" · 방문 예정 {fmt_date(r['visit_date'])}" if r.get("visit_date") else "") for r in rows]
    return say(f"{mask_phone(phone)} 고객님의 진행 중인 접수입니다.\n" + "\n".join(lines), trace=trace)


def intake(state: dict) -> dict:
    """접수 정보를 추출(LLM)하고 형식을 검증(파이썬)한다. 빠진 항목이 있으면 다시 묻는다."""
    text = last_user_text(state)
    found = extract_intake(text)          # LLM에는 마스킹된 문장만 전달됨
    found.pop("phone", None)
    if state.get("turn_phone"):
        found["phone"] = state["turn_phone"]
    slots = {**state.get("slots", {}), **found}
    if slots.get("product") not in PRODUCTS:
        slots.pop("product", None)
    product = slots.get("product") or state.get("product") or next(iter(detect_products(text)), None)
    gate_trace = []
    if not product:
        gate = product_gate(text)
        gate_trace = gate["trace"]
        if gate["unsupported"]:
            # stage="consult"는 '접수 정보 완료' 신호와 겹치므로 done으로 끝낸다 (다음 입력은 새 상담으로 시작)
            return say(unsupported_message(gate["unsupported"]), **{**RESET_FIELDS, "stage": "done"}, trace=gate_trace)
        product = gate["product"]
    if product:
        slots["product"] = product
    region_trace, ambiguous_region = [], False
    if "region" in found:                 # 지역 이름 정규화 (강남 → 서울 강남구)
        nr = normalize_region(found["region"])
        ambiguous_region = nr["ambiguous"]
        if nr["region"]:
            slots["region"] = nr["region"]
        else:
            slots.pop("region", None)
        region_trace = [step("normalize_region", found["region"], "시/도 필요 (같은 구 이름 여러 곳)" if ambiguous_region
                             else nr["region"])]
    view = {k: (mask_phone(v) if k == "phone" else v) for k, v in slots.items()}
    trace = gate_trace + [step("extract_intake", "IntakeSlots", view)] + region_trace
    upd = {"slots": slots, "product": product, "stage": "intake", "status": "접수 정보 입력",
           "symptom": state.get("symptom") or slots.get("symptom") or text}

    if slots.get("region") and product:
        # 담당 기사가 아예 없는 지역이면 날짜와 상관없이 방문할 수 없으므로 저장하지 않고 안내 후 종료
        cov = coverage(slots["region"], product)
        trace.append(step("service_area", f"{slots['region']} / {product}",
                          {"ok": "담당 기사 있음", "no_region": "지역 담당 기사 없음",
                           "no_product": "지역에 해당 제품 담당 기사 없음"}[cov]))
        if cov != "ok":
            return say(out_of_area_message(slots["region"], product, cov, known_regions()),
                       **{**RESET_FIELDS, "stage": "done", "status": "서비스지역외"}, trace=trace)

    if "phone" in found and not re.fullmatch(PHONE_OK, found["phone"]):
        slots.pop("phone")
        trace.append(step("validate", "phone", "형식 오류"))
        return say("휴대폰 번호 형식이 올바르지 않아요. 010-XXXX-XXXX 형식으로 다시 입력해 주세요.", **upd, trace=trace)
    if "preferred_date" in found and not valid_date(found["preferred_date"]):
        slots.pop("preferred_date")
        trace.append(step("validate", "preferred_date", "형식 오류 또는 지난 날짜"))
        return say("희망 방문일을 오늘 이후 날짜로, YYYY-MM-DD 형식으로 알려 주세요. 예: 2026-11-20", **upd, trace=trace)
    if ambiguous_region:
        return say(ASK_REGION_CITY, **upd, trace=trace)
    missing = [label for k, label in SLOT_LABELS.items() if not slots.get(k)]
    if missing:
        return say(f"접수를 위해 {', '.join(missing)}을(를) 알려 주세요.", **upd, trace=trace)
    return {**upd, "stage": "consult", "trace": trace}   # 다 모임 → 중복 확인으로


def after_intake(state: dict) -> str:
    return "check_duplicate" if state.get("stage") == "consult" else END


def check_duplicate(state: dict) -> dict:
    """같은 고객·같은 제품으로 방문 완료 전인 접수가 있으면 새 접수를 막는다."""
    s = state["slots"]
    rows = call_tool("find_open_ticket", phone=s["phone"], product=s["product"])
    trace = [step("find_open_ticket", f"{mask_phone(s['phone'])} / {s['product']}",
                  [r["ticket_id"] for r in rows] or "진행 중 접수 없음")]
    if not rows:
        return {"trace": trace}
    r = rows[0]
    visit = f"\n방문 예정 {fmt_date(r['visit_date'])}" if r.get("visit_date") else ""
    return say(f"같은 제품으로 진행 중인 접수가 이미 있어요.\n접수번호 {r['ticket_id']} · 상태 {r['status']}{visit}\n"
               "새 접수는 만들지 않았습니다. 일정 변경이 필요하면 말씀해 주세요.",
               stage="done", status="중복차단", ticket_id=r["ticket_id"], trace=trace)


def after_duplicate(state: dict) -> str:
    return END if state.get("stage") == "done" else "assign"


def assign(state: dict) -> dict:
    """희망일에 규칙으로 기사를 배정한다. 없으면 가장 빠른 가능 날짜를 찾는다."""
    s = state["slots"]
    hit = call_tool("assign_technician", region=s["region"], product=s["product"], visit_date=s["preferred_date"])
    trace = [step("assign_technician", f"{s['region']} / {s['product']} / {s['preferred_date']}",
                  f"{hit['candidates']} → {hit['technician_id']}" if hit else "가능 기사 없음")]
    if hit:
        return {"proposal": hit, "attempts": 0, "trace": trace}
    hit = call_tool("find_earliest_date", region=s["region"], product=s["product"], after_date=s["preferred_date"])
    trace.append(step("find_earliest_date", f"after {s['preferred_date']}",
                      f"{hit['visit_date']} · {hit['technician_id']}" if hit else "14일 내 없음"))
    if not hit:
        # 지역 담당 기사는 있지만(intake에서 확인) 일정이 꽉 찬 경우 → 대기
        return {**save_waiting(state, f"{s['region']} {s['product']} 담당 기사는 있지만, 희망하신 날짜부터 "
                                      "14일 안에 방문 가능한 일정이 없어요."), "trace": trace}
    return {"proposal": {**hit, "note": f"희망하신 {fmt_date(s['preferred_date'])}에는 방문 가능한 기사가 없어요. "
                                        "가장 빠른 날짜로 제안드립니다."},
            "attempts": 0, "trace": trace}


def after_assign(state: dict) -> str:
    return END if state.get("stage") == "done" else "propose"


def propose(state: dict) -> dict:
    """방문 일정(기사·날짜)을 제안하고 승인을 요청한다."""
    p, n = state["proposal"], state.get("attempts", 0)
    if n:
        head = f"다음으로 가능한 날짜입니다. (재제안 {n}/{MAX_REPROPOSALS})"
    else:  # 첫 제안: 새 접수라는 것을 고객에게 알린다 (중복 확인을 통과한 경우만 여기에 옴)
        product = state.get("slots", {}).get("product", "")
        head = f"{product} AS를 새로 접수해 방문 일정을 잡아 드릴게요." + (f"\n{p['note']}" if p.get("note") else "")
    msg = (f"{head}\n" if head else "") + (
        f"아래 일정으로 방문을 확정할까요?\n- 기사: {p['name']} ({p['technician_id']})\n- 방문일: {fmt_date(p['visit_date'])}\n"
        "확정하시려면 '확정', 다른 날짜를 원하시면 '다른 날짜'라고 말씀해 주세요.")
    return say(msg, stage="hitl", status="승인 대기", proposal={**p, "note": None})


def hitl(state: dict) -> dict:
    """고객 승인 대기 (interrupt). 다음 입력으로 재개되면 승인/거절을 판정한다."""
    p = state["proposal"]
    answer = interrupt({"proposal": p, "question": "방문 일정 승인"})
    g = check_input(answer, "hitl")
    if re.search(CANCEL, answer) and not g["blocked"]:
        # 일정 승인 대기 중 취소: 예약도 '대기'도 저장하지 않고 종료
        result = say(FAREWELL, **{**RESET_FIELDS, "stage": "done", "status": "상담 종료", "hitl_result": "cancelled"},
                     trace=[step("cancel", answer, "승인 대기 중 취소 → 저장 없이 종료, 상태 초기화")])
    elif g["blocked"]:
        result = say(GUARD_MESSAGES[g["category"]], hitl_result="unclear",
                     trace=[step("guard", answer, f"차단 · {g['category']} ({g['by']})")])
    else:
        result = _hitl_decide(state, p, answer)
    result["messages"] = [HumanMessage(answer)] + result.get("messages", [])
    return result


def _hitl_decide(state: dict, p: dict, answer: str) -> dict:
    """승인 → 예약확정 저장 / 거절 → 재제안 또는 대기 저장 / 판단 불가 → 다시 질문."""
    if re.search(APPROVE, answer) and not re.search(REJECT, answer):
        s = state["slots"]
        row = call_tool("save_ticket", ticket={
            "customer_name": s["name"], "phone": s["phone"], "region": s["region"], "product": s["product"],
            "symptom": state.get("symptom"), "technician_id": p["technician_id"], "visit_date": p["visit_date"],
            "status": "예약확정", "proposal_attempts": state.get("attempts", 0)})
        return say(f"방문 일정이 확정되었습니다.\n접수번호 {row['ticket_id']}\n{fmt_date(p['visit_date'])} · {p['name']} 기사\n"
                   f"방문 전날 {mask_phone(s['phone'])}로 안내 문자를 드립니다.",
                   stage="done", status="예약확정", ticket_id=row["ticket_id"], hitl_result="approved",
                   trace=[step("hitl_resume", answer, "승인"), step("save_ticket", "예약확정", row["ticket_id"])])
    if re.search(REJECT, answer):
        n = state.get("attempts", 0)
        trace = [step("hitl_resume", answer, f"거절 (재제안 {n}/{MAX_REPROPOSALS} 사용)")]
        if n >= MAX_REPROPOSALS:
            return {**save_waiting(state, f"재제안 {MAX_REPROPOSALS}회 안에 원하시는 날짜를 찾지 못했어요."),
                    "trace": trace + [step("save_ticket", "대기", "저장")]}
        s = state["slots"]
        hit = call_tool("find_earliest_date", region=s["region"], product=s["product"], after_date=p["visit_date"])
        trace.append(step("find_earliest_date", f"after {p['visit_date']}",
                          f"{hit['visit_date']} · {hit['technician_id']}" if hit else "없음"))
        if not hit:
            return {**save_waiting(state, "더 이상 가능한 날짜가 없어요."), "trace": trace}
        return {"proposal": hit, "attempts": n + 1, "stage": "hitl", "hitl_result": "reproposed", "trace": trace}
    return say("'확정' 또는 '다른 날짜'로 말씀해 주세요.", hitl_result="unclear", trace=[step("hitl_resume", answer, "판단 불가 → 다시 질문")])


def after_hitl(state: dict) -> str:
    """승인·대기 저장 → 종료 / 재제안 → propose / 판단 불가 → hitl에서 다시 대기."""
    return {"reproposed": "propose", "unclear": "hitl"}.get(state.get("hitl_result"), END)


def save_waiting(state: dict, why: str) -> dict:
    """가능한 일정이 없으면 '대기'로 저장하고 추후 연락을 안내한다."""
    s = state["slots"]
    row = call_tool("save_ticket", ticket={
        "customer_name": s["name"], "phone": s["phone"], "region": s["region"], "product": s["product"],
        "symptom": state.get("symptom"), "status": "대기", "proposal_attempts": state.get("attempts", 0)})
    return say(waiting_message(why, row["ticket_id"], mask_phone(s["phone"])),
               stage="done", status="대기", ticket_id=row["ticket_id"], proposal=None, hitl_result="waiting")
