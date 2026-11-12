"""가드레일 LLM 판정 체인 (LCEL: prompt | llm.with_structured_output(GuardResult))."""
from functools import lru_cache

from src.guard.prompts import GUARD_PROMPT
from src.guard.schemas import GuardResult
from src.shared.llm import judge_llm


@lru_cache
def _guard_chain():
    return GUARD_PROMPT | judge_llm().with_structured_output(GuardResult)


def llm_guard(text: str, stage: str) -> dict:
    """가드레일 LLM 판정 → {"blocked", "category", "reason"}"""
    return _guard_chain().invoke({"text": text, "stage": stage}).model_dump()
