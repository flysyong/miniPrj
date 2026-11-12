"""가드레일 입출력 스키마 (LLM 구조화 출력)."""
from pydantic import BaseModel, Field


class GuardResult(BaseModel):
    """입력 가드레일 판정 결과."""
    blocked: bool = Field(description="차단해야 하면 true")
    category: str = Field(description="injection(프롬프트 인젝션·시스템 정보 탈취), offtopic(전자제품 AS와 무관한 요청), "
                                      "abuse(욕설·폭언), none(정상) 중 하나")
    reason: str = Field(description="판정 근거 한 문장")
