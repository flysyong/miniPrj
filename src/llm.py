"""Bedrock LLM 생성 도우미.

- temperature=0 고정 (Seed 제약)
- 메인 모델 호출이 실패하면 예비 모델로 자동 전환 (CLAUDE.md: 중단 없이 쓸 수 있게)
"""
from functools import lru_cache

from botocore.config import Config
from langchain_aws import ChatBedrockConverse

from src.config import settings

# 호출 한도(ThrottlingException)에 걸리면 자동으로 속도를 줄이며 최대 10번까지 재시도
BEDROCK_CONFIG = Config(retries={"max_attempts": 10, "mode": "adaptive"}, read_timeout=120)


def _make(model_id: str) -> ChatBedrockConverse:
    return ChatBedrockConverse(model=model_id, region_name=settings.aws_region, temperature=settings.temperature,
                               config=BEDROCK_CONFIG)


@lru_cache
def main_llm():
    """상담 답변용 (Sonnet 4.5, 실패 시 예비 모델)."""
    return _make(settings.llm_model_id).with_fallbacks([_make(settings.llm_fallback_model_id)])


@lru_cache
def judge_llm() -> ChatBedrockConverse:
    """가드 판정·정보 추출·평가 판정용 (Haiku 4.5). 구조화 출력에 쓰므로 fallback 래핑 없이 반환."""
    return _make(settings.judge_model_id)


def text_of(message) -> str:
    """ChatBedrockConverse의 content가 블록 리스트일 때 텍스트만 모은다."""
    content = message.content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content
