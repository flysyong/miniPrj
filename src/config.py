"""설정 모듈 (모델 ID·경로를 모으는 유일한 곳).

값은 .env에서 읽는다. miniPjt/.env가 있으면 우선 쓰고, 없는 값은 상위 폴더(C:\\AX-SDS\\.env)에서 가져온다.
모델 ID 문자열은 이 파일에만 둔다 (Seed AC: 모델 ID 하드코딩은 .py 한 곳만 허용).
"""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent  # miniPjt/

load_dotenv(ROOT / ".env")          # 프로젝트 전용 값 (우선)
load_dotenv(ROOT.parent / ".env")   # 강의 공용 값 (AWS 키 등, 이미 있는 값은 덮어쓰지 않음)

# Seed 제약: LangSmith 등 외부 트레이싱은 쓰지 않는다
os.environ["LANGSMITH_TRACING"] = "false"


@dataclass(frozen=True)
class Settings:
    # AWS Bedrock
    aws_region: str = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    llm_model_id: str = os.getenv("LLM_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
    # 예비 모델은 메인(Sonnet)과 한도가 따로인 Haiku: Sonnet 하루 토큰 한도 초과 시에도 상담이 멈추지 않게
    llm_fallback_model_id: str = os.getenv("LLM_FALLBACK_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    judge_model_id: str = os.getenv("JUDGE_MODEL_ID", "global.anthropic.claude-haiku-4-5-20251001-v1:0")
    embed_model_id: str = os.getenv("EMBED_MODEL_ID", "amazon.titan-embed-text-v2:0")
    temperature: float = 0.0

    # 화면: 1이면 사이드바에 개발자 정보(trace·근거 FAQ·thread_id)를 보여 준다 (기본: 숨김)
    debug_ui: bool = os.getenv("DEBUG_UI", "0").strip() == "1"

    # 경로
    data_dir: Path = ROOT / "data"
    faq_dir: Path = ROOT / "data" / "faq"
    technicians_path: Path = ROOT / "data" / "technicians.json"
    tickets_path: Path = ROOT / "data" / "tickets.json"
    chroma_dir: Path = ROOT / ".chroma"
    checkpoint_db: Path = ROOT / ".checkpoints.sqlite"
    eval_dir: Path = ROOT / "evaluation"


settings = Settings()
