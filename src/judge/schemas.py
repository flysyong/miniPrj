"""평가 판정 출력 스키마 (LLM 구조화 출력)."""
from pydantic import BaseModel, Field


class JudgeResult(BaseModel):
    """인-아웃 케이스 판정 결과."""
    passed: bool = Field(description="expected_traits를 모두 충족하고 forbidden이 하나도 없으면 true")
    missing_traits: list[str] = Field(default_factory=list, description="충족하지 못한 expected_traits 항목")
    found_forbidden: list[str] = Field(default_factory=list, description="답변에 나타난 forbidden 항목")
    reason: str = Field(description="판정 근거 한 문장")
