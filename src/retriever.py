"""RAG 파이프라인: FAQ Markdown 청킹 → Titan v2 임베딩(Chroma) + BM25(kiwipiepy) 하이브리드 검색.

실행: python -m src.retriever            # 인덱스가 없으면 만들고 예시 검색
      python -m src.retriever --rebuild  # FAQ를 고친 뒤 인덱스 다시 만들기
참고: day2_practice/chunking_md.py, vectorstore.py, hybrid.py

하이브리드 이유 (1차 평가): 고객이 FAQ 문구를 바꿔 말하면 벡터 거리만으로는 "맞는 FAQ 없음"과 구분되지 않았다.
키워드(리모컨, 냉장실, 5C 등)가 맞는지 BM25로 함께 보고, 두 검색이 같은 문서를 1위로 고르면 거리 기준을 완화한다.
"""
import re
import threading
import sys

from langchain_aws import BedrockEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter
from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi

from src.config import settings
from src.llm import BEDROCK_CONFIG

COLLECTION = "as_faq"
# ---- "맞는 FAQ 있음" 판정 기준 (거리는 작을수록 가까움, BM25는 클수록 키워드가 많이 겹침)
MAX_DISTANCE = 0.85        # 벡터만으로 확실한 거리 (1차 측정: FAQ 문구에 가까운 질문 최대 0.695)
AGREE_DISTANCE = 1.15      # 벡터·BM25가 같은 문서를 1위로 고르면 이 거리까지 인정 (바꿔 말한 질문 1.015~1.116)
AGREE_MIN_BM25 = 3.0
BM25_STRONG = 6.0          # 키워드가 강하게 겹치는 BM25 1위 문서는 이 거리까지 인정
BM25_STRONG_DISTANCE = 1.45
# 측정값: 답이 없어야 하는 질문은 두 검색이 다른 문서를 고르거나(BM25 1.6~3.5), 같아도 거리 1.19 이상.
# 예외 "타는 냄새·연기"는 검색이 아니라 안전 정책으로 처리 (agent.py SAFETY)
RRF_K = 60                 # 순위 결합(Reciprocal Rank Fusion) 상수
KEEP_TAGS = {"NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "SL", "SN", "XR"}  # 명사·어간·숫자·외래어

_SECTION = re.compile(r"\[(faq_\w+)\]\s*(.+)")
_db = None
_db_lock = threading.Lock()
_bm25 = None               # (BM25Okapi, 문서 목록)
_kiwi = Kiwi()


def tokenize(text: str) -> list[str]:
    """한국어 형태소 단위 토큰 (day2 hybrid.py와 같은 방식)."""
    return [t.form for t in _kiwi.tokenize(text) if t.tag in KEEP_TAGS]


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


def _get_bm25():
    global _bm25
    with _db_lock:
        if _bm25 is None:
            docs = load_faq_docs()
            _bm25 = (BM25Okapi([tokenize(d.page_content) for d in docs]), docs)
    return _bm25


def search(query: str, k: int = 3, product: str | None = None) -> list[dict]:
    """증상으로 FAQ를 찾는다 (벡터 + BM25 하이브리드). product가 있으면 그 제품군 문서만 본다.

    반환: [{"doc_id", "text", "product", "title", "distance", "bm25", "match"}]
          "맞는 FAQ"로 인정된 문서만, 두 검색 순위를 결합(RRF)한 순서로 최대 k개
    """
    bm25, docs = _get_bm25()
    cand = [d for d in docs if product is None or d.metadata["product"] == product]
    if not cand:
        return []
    # 1) 벡터: 후보 전체의 거리 (FAQ가 35건뿐이라 전부 받아도 가볍다)
    flt = {"product": product} if product else None
    dist = {d.metadata["doc_id"]: s for d, s in get_db().similarity_search_with_score(query, k=len(cand), filter=flt)}
    # 2) BM25: 키워드 점수
    all_scores = bm25.get_scores(tokenize(query))
    score = {d.metadata["doc_id"]: float(all_scores[docs.index(d)]) for d in cand}
    ids = [d.metadata["doc_id"] for d in cand if d.metadata["doc_id"] in dist]
    v_rank = {i: r for r, i in enumerate(sorted(ids, key=lambda i: dist[i]), start=1)}
    b_rank = {i: r for r, i in enumerate(sorted(ids, key=lambda i: -score[i]), start=1)}

    def match(i: str) -> str | None:
        if dist[i] <= MAX_DISTANCE:
            return "vector"
        if v_rank[i] == 1 and b_rank[i] == 1 and dist[i] <= AGREE_DISTANCE and score[i] >= AGREE_MIN_BM25:
            return "agree"
        if b_rank[i] == 1 and score[i] >= BM25_STRONG and dist[i] <= BM25_STRONG_DISTANCE:
            return "keyword"
        return None

    rrf = {i: 1 / (RRF_K + v_rank[i]) + 1 / (RRF_K + b_rank[i]) for i in ids}
    by_id = {d.metadata["doc_id"]: d for d in cand}
    out = []
    for i in sorted(ids, key=lambda i: -rrf[i]):
        how = match(i)
        if how:
            d = by_id[i]
            out.append({"doc_id": i, "text": d.page_content, "product": d.metadata["product"],
                        "title": d.metadata["title"], "distance": round(dist[i], 3),
                        "bm25": round(score[i], 2), "match": how})
    return out[:k]


if __name__ == "__main__":
    get_db(rebuild="--rebuild" in sys.argv)
    print(f"인덱스: {get_db()._collection.count()}건")
    for q in ["TV 전원이 안 켜져요", "세탁기가 탈수할 때 덜컹거리며 멈춰요", "에어컨에서 찬바람이 안 나와요"]:
        print(f"\n질문: {q}")
        for h in search(q):
            print(f"  {h['doc_id']} (거리 {h['distance']}, BM25 {h['bm25']}, {h['match']}) {h['title']}")
