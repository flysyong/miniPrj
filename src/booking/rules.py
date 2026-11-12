"""접수 규칙 (파이썬): 형식 검증, 승인/거절 판정, 날짜 표시."""
import re
from datetime import date

DOW = "월화수목금토일"
MAX_REPROPOSALS = 3                       # 거절 시 재제안 최대 횟수 → 초과하면 '대기' 저장
PHONE_OK = r"010-\d{4}-\d{4}"
LOOKUP = r"진행|상황|조회|어떻게 됐|언제 와"     # 전화번호와 함께 오면 진행 상황 조회
# "네/예"는 문장 맨 앞에 단독으로 올 때만 승인으로 본다 ("애매하네요"를 승인으로 오판하지 않도록)
APPROVE = r"확정|승인|좋아요|좋습니다|괜찮아요|그렇게 해|^\s*(네|예)(\s|,|\.|!|$)"
REJECT = r"다른|거절|안\s?돼|안\s?될|어려|힘들|싫|변경|안 괜찮|못"
SLOT_LABELS = {"name": "성함", "phone": "휴대폰 번호", "region": "지역(예: 서울 강남구)",
               "product": "제품", "preferred_date": "희망 방문일(YYYY-MM-DD)"}


def fmt_date(d: str) -> str:
    """2026-11-20 → 2026-11-20(금)"""
    return f"{d}({DOW[date.fromisoformat(d).weekday()]})"


def valid_date(d: str) -> bool:
    """YYYY-MM-DD 형식이고 오늘 이후인지."""
    try:
        return date.fromisoformat(d) >= date.today() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) is not None
    except ValueError:
        return False
