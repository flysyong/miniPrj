"""REST API (표준 규약).

POST /query
  Body:     {"question": "사용자 질의", "thread_id": "선택: 이어서 대화할 때"}
  Response: {"answer": str, "contexts": [{"doc_id", "text"}], "trace": [{"step", "input", "output"}]}
  - 응답 본문은 표준 규약 3개 필드만 담는다. 대화를 이어갈 thread_id는 응답 헤더 X-Thread-Id로 돌려준다.
  - thread_id 없이 보내면 새 대화로 처리한다.

실행 (miniPjt 폴더에서): uvicorn src.api:app --port 8000   → 테스트 페이지 http://localhost:8000/docs
"""
import uuid

from fastapi import FastAPI, Response
from pydantic import BaseModel, Field

from src.agent import run_turn

app = FastAPI(title="전자제품 AS 접수 Agent API", version="1.0")


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="사용자 질의")
    thread_id: str | None = Field(None, description="이어서 대화할 때 이전 응답 헤더 X-Thread-Id 값")


class Context(BaseModel):
    doc_id: str
    text: str


class TraceStep(BaseModel):
    step: str
    input: str
    output: str


class QueryResponse(BaseModel):
    answer: str = Field(description="근거 기반 응답")
    contexts: list[Context] = Field(description="검색된 FAQ 문서")
    trace: list[TraceStep] = Field(description="이번 요청에서 실행된 그래프 노드·도구 호출 순서")


@app.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, response: Response) -> QueryResponse:
    thread_id = req.thread_id or str(uuid.uuid4())
    r = run_turn(thread_id, req.question)
    response.headers["X-Thread-Id"] = thread_id
    return QueryResponse(answer=r["answer"], contexts=r["contexts"], trace=r["trace"])


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
