"""접수 정보 추출 체인 (LCEL: prompt | llm.with_structured_output(IntakeSlots))."""
from functools import lru_cache

from src.booking.prompts import INTAKE_PROMPT
from src.booking.schemas import IntakeSlots
from src.shared.llm import judge_llm


@lru_cache
def _intake_chain():
    return INTAKE_PROMPT | judge_llm().with_structured_output(IntakeSlots)


def extract_intake(text: str) -> dict:
    """고객 메시지 → 접수 정보 dict (없는 항목은 키 자체를 빼고 반환)."""
    slots: IntakeSlots = _intake_chain().invoke({"text": text})
    return {k: v.strip() for k, v in slots.model_dump().items()
            if v and v.strip().lower() not in ("null", "none", "없음")}
