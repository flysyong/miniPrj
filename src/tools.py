"""도메인 도구 (파이썬 규칙). MCP 서버(mcp_server.py)가 이 함수들을 도구로 노출한다.

계산·규칙 판정은 LLM이 아니라 이 파일의 파이썬 코드로 한다 (CLAUDE.md).
배정 규칙: 지역 일치 + 제품군 일치 + 그날 근무 → 그날 예약이 가장 적은 기사 → 동률이면 기사 ID 순
"""
import json
from datetime import date, timedelta

from src import retriever
from src.config import settings

DOW = "월화수목금토일"
HORIZON_DAYS = 14          # 가장 빠른 날짜를 찾는 범위
OPEN_STATUSES = {"예약확정", "대기"}   # 방문 완료 전(진행 중)으로 보는 상태


# ---------------------------------------------------------------- 저장소 (JSON 파일)
def _load(path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path, rows: list[dict]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def mask_phone(phone: str | None) -> str:
    """010-1234-5678 → 010-****-5678"""
    if not phone or len(phone) < 4:
        return phone or ""
    return phone[:4] + "****-" + phone[-4:] if phone.count("-") == 2 else "***" + phone[-4:]


# ---------------------------------------------------------------- 도구 6종
def search_faq(query: str, product: str | None = None) -> list[dict]:
    """증상으로 FAQ 자가 조치 문서를 찾는다."""
    return retriever.search(query, k=2, product=product)


def find_open_ticket(phone: str, product: str | None = None) -> list[dict]:
    """고객 전화번호(와 제품)로 방문 완료 전인 접수를 찾는다."""
    return [t for t in _load(settings.tickets_path)
            if t["phone"] == phone and t["status"] in OPEN_STATUSES and (product is None or t["product"] == product)]


def _candidates(region: str, product: str, day: str) -> list[dict]:
    weekday = DOW[date.fromisoformat(day).weekday()]
    techs = [t for t in _load(settings.technicians_path)
             if t["region"] == region and product in t["products"] and weekday in t["workdays"]]
    return sorted(techs, key=lambda t: (t["bookings"].get(day, 0), t["technician_id"]))


def assign_technician(region: str, product: str, visit_date: str) -> dict | None:
    """배정 규칙으로 그날 방문할 기사 1명을 고른다. 없으면 None."""
    c = _candidates(region, product, visit_date)
    if not c:
        return None
    t = c[0]
    return {"technician_id": t["technician_id"], "name": t["name"], "visit_date": visit_date,
            "bookings": t["bookings"].get(visit_date, 0), "candidates": [x["technician_id"] for x in c]}


def find_earliest_date(region: str, product: str, after_date: str) -> dict | None:
    """after_date 다음 날부터 HORIZON_DAYS 안에서 배정 가능한 가장 빠른 날짜와 기사를 찾는다."""
    start = date.fromisoformat(after_date)
    for i in range(1, HORIZON_DAYS + 1):
        day = (start + timedelta(days=i)).isoformat()
        hit = assign_technician(region, product, day)
        if hit:
            return hit
    return None


def save_ticket(ticket: dict) -> dict:
    """새 접수를 저장한다. 예약확정이면 기사의 그날 예약 수를 1 올린다. 저장된 접수를 반환."""
    tickets = _load(settings.tickets_path)
    today = date.today().strftime("%Y%m%d")
    seq = sum(1 for t in tickets if t["ticket_id"].startswith(f"AS-{today}-")) + 1
    row = {"ticket_id": f"AS-{today}-{seq:03d}", "customer_name": None, "phone": None, "region": None,
           "product": None, "symptom": None, "technician_id": None, "visit_date": None,
           "status": "대기", "proposal_attempts": 0, "created_at": date.today().isoformat()}
    row.update({k: v for k, v in ticket.items() if k in row and k != "ticket_id"})
    tickets.append(row)
    _save(settings.tickets_path, tickets)
    if row["status"] == "예약확정" and row["technician_id"]:
        techs = _load(settings.technicians_path)
        for t in techs:
            if t["technician_id"] == row["technician_id"]:
                t["bookings"][row["visit_date"]] = t["bookings"].get(row["visit_date"], 0) + 1
        _save(settings.technicians_path, techs)
    return row


def update_ticket_status(ticket_id: str, status: str) -> dict | None:
    """접수 상태를 바꾼다 (예: 대기 → 예약확정, 예약확정 → 방문완료)."""
    tickets = _load(settings.tickets_path)
    for t in tickets:
        if t["ticket_id"] == ticket_id:
            t["status"] = status
            _save(settings.tickets_path, tickets)
            return t
    return None


def technician_name(technician_id: str) -> str:
    return next((t["name"] for t in _load(settings.technicians_path) if t["technician_id"] == technician_id), "")
