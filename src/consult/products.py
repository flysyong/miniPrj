"""제품 판정: 지원 5종인지, 별칭 정규화. 1차 파이썬 규칙 → 2차 LLM(chains.check_product)."""
import re

from src.consult.chains import check_product
from src.shared.turn import step

# 제품 이름 (확실한 신호)
PRODUCT_NAMES = {
    "TV": r"TV|티비|티브이|텔레비전|텔레비|테레비",
    "냉장고": r"냉장고",
    "세탁기": r"세탁기|통돌이",
    "에어컨": r"에어컨|에어콘|에아컨",
    "전자레인지": r"전자\s?레인지|전자\s?렌지|(?<![가-힣])레인지|(?<![가-힣])렌지",   # '오렌지'는 제외
}
# 증상·부품 단어 (제품 이름이 없을 때만 참고). '탈수'·'배수'는 탈수기·식기세척기에도 쓰이므로
# 미지원 제품 이름이 함께 있으면 쓰지 않는다 (예: "탈수기 전원" → 세탁기 아님)
PRODUCT_HINTS = {
    "냉장고": r"냉동실|냉장실|제빙",
    "세탁기": r"탈수|배수|세탁|빨래",
    "에어컨": r"실외기|찬바람",
}
PRODUCTS = PRODUCT_NAMES          # 지원 제품 5종 (이름 목록으로 쓰는 곳: `cat in PRODUCTS`)
# 제품 별칭 → 표준 이름 (검색 전에 바꿈). FAQ 문서는 표준 이름으로 쓰여 있어서,
# 별칭(티브이 등)은 임베딩·BM25 모두 같은 제품으로 연결하지 못한다 (예: "티브이 전원" 거리 1.078 → "TV 전원" 0.496)
PRODUCT_ALIASES = [
    (r"(?<![A-Za-z])tv(?![A-Za-z])|티브이|티비|텔레비전|텔레비|테레비", "TV"),
    (r"에어콘|에아컨", "에어컨"),
    (r"전자\s?렌지|전자\s(?=레인지)|(?<![가-힣])렌지", "전자레인지"),
    (r"통돌이(\s?세탁기)?", "세탁기"),
]
# 지원 제품 5종(PRODUCTS) 밖의 가전 — 접수하지 않고 판매처 문의로 안내 (SERVICE.md 4번 정책)
UNSUPPORTED = r"탈수기|로봇\s?청소기|청소기|노트북|컴퓨터|휴대폰|핸드폰|스마트폰|태블릿|건조기|식기세척기|정수기|공기청정기|제습기|선풍기|모니터|프린터"
SUPPORTED_TEXT = "TV, 냉장고, 세탁기, 에어컨, 전자레인지"


def normalize_products(text: str) -> str:
    """검색용 문장에서 제품 별칭을 표준 이름으로 바꾼다 (고객에게 보이는 문장은 그대로)."""
    for pattern, name in PRODUCT_ALIASES:
        text = re.sub(pattern, name, text, flags=re.I)
    return text.replace("전자레인지레인지", "전자레인지")


def detect_products(text: str) -> list[str]:
    """문장에 나온 지원 제품 목록 (키워드 규칙).

    1) 지원 제품 이름이 있으면 그것 2) 미지원 제품 이름이 있으면 없음(→ product_gate가 미지원 안내)
    3) 둘 다 없으면 증상 단어로 추정 ("탈수할 때 멈춰요" → 세탁기)
    """
    names = [p for p, pat in PRODUCT_NAMES.items() if re.search(pat, text, re.I)]
    if names:
        return names
    if re.search(UNSUPPORTED, text):
        return []
    return [p for p, pat in PRODUCT_HINTS.items() if re.search(pat, text, re.I)]


def unsupported_message(name: str) -> str:
    """지원 5종이 아닌 제품 안내 (SERVICE.md 4번 정책)."""
    return (f"요청하신 제품({name})은 지원 제품이 아니어서 해당 제품에 대한 상담과 수리는 지원하지 않습니다. "
            f"판매처에 문의하세요.\n(지원 제품: {SUPPORTED_TEXT})")


def product_gate(text: str) -> dict:
    """지원 5종 키워드가 없을 때 제품을 판정한다. 1차 파이썬(미지원 키워드) → 2차 LLM(ProductCheck).

    반환: {"unsupported": 제품명|None, "product": 지원 제품|None, "trace": [...]}
    """
    m = re.search(UNSUPPORTED, text)
    if m:
        return {"unsupported": m.group(), "product": None,
                "trace": [step("product_check", text, f"미지원 제품({m.group()}) · 규칙")]}
    r = check_product(text)
    cat, name = r["category"], r["product_name"]
    out = f"{cat} ({name or '-'}) · LLM"
    if cat in PRODUCTS:
        return {"unsupported": None, "product": cat, "trace": [step("product_check", text, f"지원 제품 {out}")]}
    if cat == "기타" and name:
        return {"unsupported": name, "product": None, "trace": [step("product_check", text, f"미지원 제품 {out}")]}
    return {"unsupported": None, "product": None, "trace": [step("product_check", text, "제품 언급 없음 · LLM")]}
