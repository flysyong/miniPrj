"""상담 도구 (MCP로 노출: src/tools.py → src/mcp_server.py)."""
from src.consult import retriever


def search_faq(query: str, product: str | None = None) -> list[dict]:
    """증상으로 FAQ 자가 조치 문서를 찾는다."""
    return retriever.search(query, k=2, product=product)
