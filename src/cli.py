"""CLI 데모 (Streamlit 없이 같은 그래프로 시연).

실행: python -m src.cli      (종료: q, 새 상담: new)
"""
import uuid

from src.agent import run_turn


def main() -> None:
    thread_id = str(uuid.uuid4())
    print("전자제품 AS 접수 상담입니다. 고장 난 제품과 증상을 말씀해 주세요. (q: 종료, new: 새 상담)")
    while True:
        text = input("\n고객> ").strip()
        if text in ("q", "quit", "exit"):
            break
        if text == "new":
            thread_id = str(uuid.uuid4())
            print("[새 상담을 시작합니다]")
            continue
        if not text:
            continue
        r = run_turn(thread_id, text)
        print(f"\n상담> {r['answer']}")
        print(f"   [상태: {r['status']} | 단계: {' → '.join(t['step'] for t in r['trace'])}]")


if __name__ == "__main__":
    main()
