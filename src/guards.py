"""입력 가드레일 + 개인정보 마스킹.

- 차단 대상: 프롬프트 인젝션, AS 무관 질문, 욕설·폭언 → 안내 문구를 보내고 대화는 계속
- 개인정보(주민번호·카드번호)는 차단하지 않고 로그·LLM 전달 전에 마스킹
- 전화번호는 고객 식별용 원문을 따로 꺼내 두고, 대화 기록·로그·LLM에는 010-****-1234로 마스킹
검사 순서: 1차 정규식(파이썬) → 2차 LLM 판정(LCEL + GuardResult)
참고: day5_practice/guards_input.py, masking_middleware.py
"""
import re

from src.chains import llm_guard

PHONE_RE = re.compile(r"(?<![\d*])01\d[-\s.]?\d{2,4}[-\s.]?\d{2,4}(?![\d*])")
RRN_RE = re.compile(r"\d{6}\s?-\s?[1-4]\d{6}")            # 주민등록번호
CARD_RE = re.compile(r"\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}")  # 카드번호
MASK_PHONE_RE = re.compile(r"(?<!\d)(01\d)[-\s.]?\d{3,4}[-\s.]?(\d{4})(?!\d)")  # 하이픈·공백·점 구분 모두

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

GUARD_MESSAGES = {
    "injection": "요청하신 내용은 처리할 수 없어요. 전자제품 고장 증상을 말씀해 주시면 AS 상담을 이어서 도와드릴게요.",
    "offtopic": "저는 전자제품 AS 접수만 도와드릴 수 있어요. 고장 난 제품과 증상을 알려 주시면 바로 도와드릴게요.",
    "abuse": "불편을 드려 죄송합니다. 원활한 상담을 위해 표현을 조금만 순화해 주시면 바로 도와드리겠습니다.",
}


# ---------------------------------------------------------------- 마스킹
def find_phone(text: str) -> str | None:
    """입력에서 전화번호 원문을 꺼낸다 (고객 식별·형식 검증용, 화면·로그에는 쓰지 않음).
    주민번호·카드번호 일부를 전화번호로 오인하지 않도록 그 둘을 먼저 가린 뒤 찾는다."""
    m = PHONE_RE.search(CARD_RE.sub("#", RRN_RE.sub("#", text)))
    return m.group() if m else None


def mask_pii(text: str) -> str:
    """주민번호·카드번호는 전부, 전화번호는 가운데 자리를 가린다 (010-****-1234)."""
    text = RRN_RE.sub("******-*******", text)
    text = CARD_RE.sub("****-****-****-****", text)
    return MASK_PHONE_RE.sub(r"\1-****-\2", text)


# ---------------------------------------------------------------- 차단 판정
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
