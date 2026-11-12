"""개인정보 마스킹 (파이썬 규칙).

- 주민번호·카드번호는 차단하지 않고 로그·LLM 전달 전에 전부 가린다
- 전화번호는 고객 식별용 원문을 따로 꺼내 두고, 대화 기록·로그·LLM에는 010-****-1234로 가린다
"""
import re

PHONE_RE = re.compile(r"(?<![\d*])01\d[-\s.]?\d{2,4}[-\s.]?\d{2,4}(?![\d*])")
RRN_RE = re.compile(r"\d{6}\s?-\s?[1-4]\d{6}")            # 주민등록번호
CARD_RE = re.compile(r"\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{4}")  # 카드번호
MASK_PHONE_RE = re.compile(r"(?<!\d)(01\d)[-\s.]?\d{3,4}[-\s.]?(\d{4})(?!\d)")  # 하이픈·공백·점 구분 모두


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


def mask_phone(phone: str | None) -> str:
    """010-1234-5678 → 010-****-5678 (저장된 전화번호를 답변에 보여 줄 때)"""
    if not phone or len(phone) < 4:
        return phone or ""
    return phone[:4] + "****-" + phone[-4:] if phone.count("-") == 2 else "***" + phone[-4:]
