#!/bin/sh
# API 서버 실행 (POST /query)
uvicorn src.api:app --host 0.0.0.0 --port 8000
