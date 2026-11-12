#!/bin/sh
# API 서버 실행 (POST /query, 테스트 페이지: http://localhost:8000/docs)
cd "$(dirname "$0")"
uvicorn src.api:app --host 0.0.0.0 --port 8000
