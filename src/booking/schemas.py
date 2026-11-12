"""접수 입출력 스키마 (LLM 구조화 출력)."""
from pydantic import BaseModel, Field


class IntakeSlots(BaseModel):
    """고객 메시지에 적힌 AS 접수 정보. 메시지에 없는 항목은 null."""
    name: str | None = Field(None, description="고객 이름 (예: 홍길동)")
    phone: str | None = Field(None, description="휴대폰 번호. 고객이 쓴 그대로 복사 (형식을 고치지 말 것)")
    region: str | None = Field(None, description="'시/도 구/군' 형태 지역 (예: 서울 강남구, 부산 해운대구)")
    product: str | None = Field(None, description="제품군: TV, 냉장고, 세탁기, 에어컨, 전자레인지 중 하나")
    symptom: str | None = Field(None, description="고장 증상 요약")
    preferred_date: str | None = Field(None, description="희망 방문일. 고객이 쓴 그대로 복사 (예: 2026-11-20, 11월 말쯤)")
