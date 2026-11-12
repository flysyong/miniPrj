"""상담 입출력 스키마 (LLM 구조화 출력)."""
from pydantic import BaseModel, Field


class ProductCheck(BaseModel):
    """고객 메시지에서 AS를 요청하는 제품 판정 결과."""
    product_name: str | None = Field(None, description="고객이 말한 제품 이름 그대로 (예: 형광등, 김치냉장고). 없으면 null")
    category: str = Field(description="TV, 냉장고, 세탁기, 에어컨, 전자레인지 중 해당하는 것. "
                                      "이 5종이 아닌 제품이면 '기타', 제품 언급이 전혀 없으면 '없음'")
