"""RAG 파이프라인: FAQ Markdown 청킹 → Titan v2 임베딩 → Chroma 저장·검색.

실행: python -m src.retriever            # 인덱스가 없으면 만들고 예시 검색
      python -m src.retriever --rebuild  # FAQ를 고친 뒤 인덱스 다시 만들기
참고: day2_practice/chunking_md.py, vectorstore.py
"""
import re
import threading
import sys

from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

from src.config import settings
from src.llm import BEDROCK_CONFIG

COLLECTION = "as_faq"
# 이 거리보다 멀면 "맞는 FAQ 없음"으로 본다 (값이 작을수록 가까움).
# 측정값: 정답 질문 최대 0.695 / 정답 없는 질문(타는 냄새·수리비·로봇청소기·주식) 최소 1.011 → 중간값
MAX_DISTANCE = 0.85

_SECTION = re.compile(r"\[(faq_\w+)\]\s*(.+)")
_db = None
_db_lock = threading.Lock()


def load_faq_docs() -> list[Document]:
    """FAQ 항목(## 헤더) 하나를 청크 하나로 만든다. doc_id·제품·제목은 메타데이터로 둔다."""
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "product"), ("##", "section")])
    docs = []
    for path in sorted(settings.faq_dir.glob("*.md")):
        for chunk in splitter.split_text(path.read_text(encoding="utf-8")):
            m = _SECTION.match(chunk.metadata.get("section", ""))
            if not m:
                continue  # 제품 제목만 있는 부분은 건너뜀
            doc_id, title = m.groups()
            product = chunk.metadata["product"]
            docs.append(Document(
                page_content=f"[{product}] {title}\n{chunk.page_content}",
                metadata={"doc_id": doc_id, "product": product, "title": title, "source": path.name},
            ))
    return docs


def get_db(rebuild: bool = False) -> Chroma:
    """Chroma 벡터스토어를 연다. 비어 있거나 rebuild=True면 FAQ로 다시 채운다."""
    global _db
    with _db_lock:
        return _open_db(rebuild)


def _open_db(rebuild: bool) -> Chroma:
    global _db
    if _db is not None and not rebuild:
        return _db
    embeddings = BedrockEmbeddings(model_id=settings.embed_model_id, region_name=settings.aws_region,
                                   config=BEDROCK_CONFIG)
    db = Chroma(collection_name=COLLECTION, embedding_function=embeddings,
                persist_directory=str(settings.chroma_dir))
    if rebuild:
        db.reset_collection()
    if db._collection.count() == 0:
        docs = load_faq_docs()
        db.add_documents(docs, ids=[d.metadata["doc_id"] for d in docs])
    _db = db
    return db


def search(query: str, k: int = 3, product: str | None = None) -> list[dict]:
    """증상으로 FAQ를 찾는다. product가 있으면 그 제품군 문서만 본다.

    반환: [{"doc_id", "text", "product", "title", "distance"}] (가까운 순, MAX_DISTANCE 이내만)
    """
    flt = {"product": product} if product else None
    hits = get_db().similarity_search_with_score(query, k=k, filter=flt)
    return [
        {"doc_id": d.metadata["doc_id"], "text": d.page_content, "product": d.metadata["product"],
         "title": d.metadata["title"], "distance": round(score, 3)}
        for d, score in hits if score <= MAX_DISTANCE
    ]


if __name__ == "__main__":
    get_db(rebuild="--rebuild" in sys.argv)
    print(f"인덱스: {get_db()._collection.count()}건")
    for q in ["TV 전원이 안 켜져요", "세탁기가 탈수할 때 덜컹거리며 멈춰요", "에어컨에서 찬바람이 안 나와요"]:
        print(f"\n질문: {q}")
        for h in search(q):
            print(f"  {h['doc_id']} (거리 {h['distance']}) {h['title']}")
