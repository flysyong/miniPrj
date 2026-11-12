"""기사·접수 더미 데이터 생성 (교육용 가상 데이터).

실행: python -m src.make_data
- data/technicians.json, data/tickets.json을 만든다.
- 다시 실행하면 접수 이력이 초기 상태로 돌아간다 (시나리오·평가 전에 초기화용으로 사용).
- FAQ 문서(data/faq/*.md)는 직접 작성한 파일이라 여기서 만들지 않는다.

test_queries.csv 재현 조건 (값을 바꾸면 평가 결과가 달라지니 주의):
- 010-5555-0001: 진행 중(예약확정) 냉장고 접수 → 중복 접수 차단 (#12)
- 010-8888-9999: 방문완료 냉장고 접수 → 재접수 허용 (#17)
- 010-4444-5555: 진행 중 세탁기 접수 → 진행 상황 조회 (#7)
- 부산 해운대구 세탁기 2026-11-15(일): 근무 기사 없음 → 가장 빠른 날짜 재제안 (#6)
- 서울 강남구 냉장고 2026-11-20: 후보 T01(예약 2), T02(예약 1) → T02 배정 (#5)
"""
import json

from src.config import settings

WEEKDAYS = ["월", "화", "수", "목", "금"]
WEEKDAYS_SAT = ["월", "화", "수", "목", "금", "토"]

TECHNICIANS = [
    {"technician_id": "T01", "name": "김민준", "region": "서울 강남구", "products": ["TV", "냉장고"],
     "workdays": WEEKDAYS, "bookings": {"2026-11-20": 2}},
    {"technician_id": "T02", "name": "이서준", "region": "서울 강남구", "products": ["냉장고", "세탁기"],
     "workdays": WEEKDAYS, "bookings": {"2026-11-20": 1}},
    {"technician_id": "T03", "name": "박도윤", "region": "서울 마포구", "products": ["TV", "냉장고", "세탁기"],
     "workdays": WEEKDAYS_SAT, "bookings": {"2026-11-14": 1}},
    {"technician_id": "T04", "name": "최예준", "region": "부산 해운대구", "products": ["세탁기", "에어컨"],
     "workdays": WEEKDAYS, "bookings": {"2026-11-16": 1}},
    {"technician_id": "T05", "name": "정하준", "region": "부산 해운대구", "products": ["세탁기"],
     "workdays": ["월", "수", "금"], "bookings": {}},
    {"technician_id": "T06", "name": "강지호", "region": "서울 송파구", "products": ["냉장고", "세탁기", "에어컨"],
     "workdays": WEEKDAYS_SAT, "bookings": {"2026-11-13": 1}},
    {"technician_id": "T07", "name": "윤시우", "region": "인천 남동구", "products": ["TV", "냉장고", "세탁기"],
     "workdays": WEEKDAYS, "bookings": {}},
    {"technician_id": "T08", "name": "장은우", "region": "대전 서구", "products": ["TV", "냉장고", "세탁기", "에어컨", "전자레인지"],
     "workdays": WEEKDAYS, "bookings": {}},
    {"technician_id": "T09", "name": "임서진", "region": "서울 강남구", "products": ["에어컨", "전자레인지", "TV"],
     "workdays": ["화", "목", "토"], "bookings": {"2026-11-20": 0}},
    {"technician_id": "T10", "name": "한지민", "region": "서울 마포구", "products": ["에어컨", "전자레인지"],
     "workdays": WEEKDAYS, "bookings": {}},
]

TICKETS = [
    {"ticket_id": "AS-20261105-002", "customer_name": "이영희", "phone": "010-5555-0001", "region": "서울 마포구",
     "product": "냉장고", "symptom": "냉장실 온도가 올라감", "technician_id": "T03", "visit_date": "2026-11-14",
     "status": "예약확정", "proposal_attempts": 0, "created_at": "2026-11-05"},
    {"ticket_id": "AS-20261020-011", "customer_name": "정수민", "phone": "010-8888-9999", "region": "서울 송파구",
     "product": "냉장고", "symptom": "냉동실 성에 과다", "technician_id": "T06", "visit_date": "2026-10-22",
     "status": "방문완료", "proposal_attempts": 0, "created_at": "2026-10-20"},
    {"ticket_id": "AS-20261109-004", "customer_name": "윤서연", "phone": "010-4444-5555", "region": "서울 송파구",
     "product": "세탁기", "symptom": "탈수 시 소음", "technician_id": "T06", "visit_date": "2026-11-13",
     "status": "예약확정", "proposal_attempts": 1, "created_at": "2026-11-09"},
]


def write_json(path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_data() -> None:
    """기사 명단·예약과 접수 이력을 초기 상태로 되돌린다."""
    write_json(settings.technicians_path, TECHNICIANS)
    write_json(settings.tickets_path, TICKETS)


def main() -> None:
    """실행: python -m src.make_data"""
    reset_data()
    print(f"technicians: {len(TECHNICIANS)}건 -> {settings.technicians_path}")
    print(f"tickets: {len(TICKETS)}건 -> {settings.tickets_path}")


if __name__ == "__main__":
    main()
