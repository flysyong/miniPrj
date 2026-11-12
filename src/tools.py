"""진입점: MCP로 노출하는 도메인 도구 모음 (제출 규약 경로 src/tools.py).

도구 6종의 실제 구현은 도메인 폴더에 있다.
- search_faq: src/consult/tools.py
- find_open_ticket, assign_technician, find_earliest_date, save_ticket, update_ticket_status: src/booking/tools.py
"""
from src.booking.tools import (assign_technician, find_earliest_date, find_open_ticket,  # noqa: F401
                               save_ticket, update_ticket_status)
from src.consult.tools import search_faq  # noqa: F401
