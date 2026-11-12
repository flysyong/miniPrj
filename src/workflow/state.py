"""그래프 상태 스키마 (모든 노드가 읽고 쓰는 대화 상태)."""
from typing import Annotated, Literal, TypedDict

from langgraph.graph.message import add_messages

Stage = Literal["consult", "resolve_check", "intake", "hitl", "done"]


def _turn_list(old: list, new: list | None) -> list:
    """턴마다 비우는 리스트용 리듀서: None이 오면 비우고, 리스트가 오면 이어 붙인다."""
    return [] if new is None else (old or []) + new


class State(TypedDict, total=False):
    messages: Annotated[list, add_messages]   # 전체 대화
    stage: Stage                              # 다음 입력을 어느 단계로 보낼지
    product: str | None                       # 상담 중인 제품군
    symptom: str | None                       # 처음 말한 증상
    slots: dict                               # 접수 정보 {name, phone, region, product, preferred_date}
    proposal: dict | None                     # 제안 중인 방문 일정 {technician_id, name, visit_date, ...}
    attempts: int                             # 재제안 횟수 (최대 3)
    ticket_id: str | None
    hitl_result: str | None                   # 승인 단계 결과 (라우팅용)
    status: str                               # 화면 표시용 상태
    turn_phone: str | None                    # 이번 입력의 전화번호 원문 (대화 기록에는 마스킹본만 저장)
    contexts: Annotated[list, _turn_list]     # 이번 턴에 검색된 FAQ [{doc_id, text}]
    trace: Annotated[list, _turn_list]        # 이번 턴 실행 기록 [{step, input, output}]


# 상담을 처음 상태로 되돌릴 때 비우는 값 (취소·미지원 제품·새 상담 시작에 공통 사용)
RESET_FIELDS = {"stage": "consult", "product": None, "slots": {}, "proposal": None, "attempts": 0,
                "ticket_id": None, "symptom": None, "hitl_result": None, "status": ""}
