"""진입점: 기사·접수 더미 데이터 초기화. 실제 구현은 src/booking/sample_data.py.

실행: python -m src.make_data
"""
from src.booking.sample_data import main, reset_data  # noqa: F401

if __name__ == "__main__":
    main()
