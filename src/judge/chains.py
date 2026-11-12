"""평가 판정 체인 (LCEL: prompt | llm.with_structured_output(JudgeResult))."""
from functools import lru_cache

from src.judge.prompts import JUDGE_PROMPT
from src.judge.schemas import JudgeResult
from src.shared.llm import judge_llm


@lru_cache
def _judge_chain():
    return JUDGE_PROMPT | judge_llm().with_structured_output(JudgeResult)


def judge_case(question: str, answer: str, expected: str, forbidden: str) -> dict:
    """인-아웃 케이스 1건 판정 → {"passed", "missing_traits", "found_forbidden", "reason"}"""
    return _judge_chain().invoke({"question": question, "answer": answer,
                                  "expected": expected, "forbidden": forbidden or "(없음)"}).model_dump()
