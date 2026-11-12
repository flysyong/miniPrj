"""입력 가드레일 판정.

- 차단 대상: 프롬프트 인젝션, AS 무관 질문, 욕설·폭언 → 안내 문구를 보내고 대화는 계속
검사 순서: 1차 정규식(파이썬) → 2차 LLM 판정(chains.llm_guard)
참고: day5_practice/guards_input.py, masking_middleware.py
"""
import re

from src.guard.chains import llm_guard
from src.guard.prompts import GUARD_MESSAGES

INJECTION_PATTERNS = [
    r"ignore (the |all )?(previous|above|prior) (instructions?|prompts?)",
    r"(위의?|이전|기존|지금까지)\s?(의\s)?(모든\s)?(지시|명령|규칙|프롬프트)[은는를]?\s?.{0,8}(무시|잊|버려)",
    r"(시스템\s?프롬프트|system\s?prompt|숨겨진\s?(지시|프롬프트)).{0,10}(공개|출력|알려|보여)",
    r"</?(system|admin|root)>",
    r"system\s*:",
    r"개발자\s?모드|관리자\s?모드|탈옥|jailbreak",
    r"너는 이제|역할을 바꿔|규칙 ?(이|가) ?없는",
]
ABUSE_PATTERNS = [r"씨발|시발|ㅅㅂ|개새|병신|ㅂㅅ|좆|닥쳐|미친놈|미친년|꺼져", r"\bXX\b|XX\s?같"]
OFFTOPIC_PATTERNS = [r"주식|코인|비트코인|로또|맛집|연애|날씨|운세|정치"]


def rule_check(text: str) -> tuple[str, str] | None:
    """1차 정규식 검사. 걸리면 (유형, 패턴)을 돌려준다."""
    for category, patterns in [("injection", INJECTION_PATTERNS), ("abuse", ABUSE_PATTERNS),
                               ("offtopic", OFFTOPIC_PATTERNS)]:
        for p in patterns:
            if re.search(p, text, re.IGNORECASE):
                return category, p
    return None


def check_input(text: str, stage: str | None = None) -> dict:
    """입력 1건을 검사한다. text는 마스킹된 문장을 넣는다.

    반환: {"blocked": bool, "category": "injection|offtopic|abuse|none", "reason": str, "by": "rule|llm|none"}
    """
    hit = rule_check(text)
    if hit:
        return {"blocked": True, "category": hit[0], "reason": f"규칙: {hit[1]}", "by": "rule"}
    try:
        r = llm_guard(text, stage or "consult")
        if r["blocked"] and r["category"] in GUARD_MESSAGES:
            return {**r, "by": "llm"}
    except Exception as e:  # LLM 판정 실패 시 규칙 결과만 쓰고 통과 (day5 정책과 동일)
        return {"blocked": False, "category": "none", "reason": f"LLM 판정 실패: {e}", "by": "none"}
    return {"blocked": False, "category": "none", "reason": "통과", "by": "llm"}
