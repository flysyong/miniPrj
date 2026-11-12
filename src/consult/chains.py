"""상담 LLM 체인 (LCEL: prompt | llm.with_structured_output(ProductCheck))."""
from functools import lru_cache

from src.consult.prompts import PRODUCT_PROMPT
from src.consult.schemas import ProductCheck
from src.shared.llm import judge_llm


@lru_cache
def _product_chain():
    return PRODUCT_PROMPT | judge_llm().with_structured_output(ProductCheck)


def check_product(text: str) -> dict:
    """고객 메시지 → {"product_name", "category"} (category: 지원 5종 / 기타 / 없음)"""
    return _product_chain().invoke({"text": text}).model_dump()
