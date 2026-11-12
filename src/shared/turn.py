"""공통: 그래프 노드가 1턴을 처리할 때 쓰는 작은 도우미 (모든 도메인 노드가 같이 쓴다)."""
from langchain_core.messages import AIMessage, HumanMessage


def last_user_text(state: dict) -> str:
    """대화 기록에서 가장 최근 고객 입력."""
    return next(m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage))


def step(name: str, input_, output) -> dict:
    """trace 한 줄 {step, input, output}."""
    return {"step": name, "input": str(input_), "output": str(output)}


def say(text: str, **updates) -> dict:
    """상담원 답변 1건 + 상태 변경을 노드 반환값으로 만든다."""
    return {"messages": [AIMessage(text)], **updates}
