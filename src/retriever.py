"""진입점: RAG 파이프라인 (제출 규약 경로 src/retriever.py). 실제 구현은 src/consult/retriever.py.

실행: python -m src.retriever            # 인덱스가 없으면 만들고 예시 검색
      python -m src.retriever --rebuild  # FAQ를 고친 뒤 인덱스 다시 만들기
"""
from src.consult.retriever import get_db, main, search  # noqa: F401

if __name__ == "__main__":
    main()
