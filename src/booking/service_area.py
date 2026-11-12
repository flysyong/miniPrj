"""서비스 지역 규칙 (파이썬): 지역 이름 정규화 + 담당 기사가 있는 지역인지 판정.

기사 명단(data/technicians.json)의 지역 표기("서울 강남구")를 표준으로 삼는다.
- 정규화 예: "서울특별시 강남구" / "서울 강남" / "강남구" / "강남" → "서울 강남구", "부산 해운대" → "부산 해운대구"
- 시/도 없이 여러 도시에 있는 구 이름(중구·서구 등)만 말하면 추측하지 않고 다시 묻는다.
MCP 도구 6종(Seed 고정)과 별개로, 그래프 노드가 직접 부르는 읽기 전용 규칙이다.
"""
import json
import re

from src.config import settings

# 시/도 정식 이름 → 기사 명단에서 쓰는 짧은 이름
CITY_ALIASES = {
    r"서울(특별시|시)?": "서울", r"부산(광역시|시)?": "부산", r"인천(광역시|시)?": "인천", r"대전(광역시|시)?": "대전",
    r"대구(광역시|시)?": "대구", r"광주(광역시|시)?": "광주", r"울산(광역시|시)?": "울산", r"세종(특별자치시|시)?": "세종",
    r"경기(도)?": "경기", r"강원(특별자치도|도)?": "강원", r"충북|충청북도": "충북", r"충남|충청남도": "충남",
    r"전북(특별자치도)?|전라북도": "전북", r"전남|전라남도": "전남", r"경북|경상북도": "경북", r"경남|경상남도": "경남",
    r"제주(특별자치도|도)?": "제주",
}
# 여러 도시에 같은 이름이 있는 구 → 시/도 없이 오면 추측하지 않는다
AMBIGUOUS_DISTRICTS = {"중구", "동구", "서구", "남구", "북구", "중", "동", "서", "남", "북"}


def _technicians() -> list[dict]:
    return json.loads(settings.technicians_path.read_text(encoding="utf-8"))


def known_regions() -> list[str]:
    """기사가 담당하는 지역 목록 (방문 서비스 지역)."""
    return sorted({t["region"] for t in _technicians()})


def _short_city(token: str) -> str | None:
    for pattern, short in CITY_ALIASES.items():
        if re.fullmatch(pattern, token):
            return short
    return None


def normalize_region(text: str | None) -> dict:
    """고객이 쓴 지역 → {"region": 표준 표기 또는 정리한 원문, "ambiguous": bool}

    알려진 서비스 지역과 맞으면 그 표기로 바꾸고, 못 맞추면 시/도 이름만 줄여서 돌려준다.
    """
    if not text:
        return {"region": None, "ambiguous": False}
    tokens = re.sub(r"[,·/]", " ", text).split()
    city = next((c for c in map(_short_city, tokens) if c), None)
    rest = [t for t in tokens if not _short_city(t)]
    matches = []
    for region in known_regions():
        r_city, r_district = region.split(maxsplit=1)
        stem = re.sub(r"(구|군|시)$", "", r_district)
        if (city in (None, r_city)) and any(t in (r_district, stem) for t in rest):
            matches.append(region)
    if len(matches) == 1 and (city or not any(t in AMBIGUOUS_DISTRICTS for t in rest)):
        return {"region": matches[0], "ambiguous": False}
    if not city and any(t in AMBIGUOUS_DISTRICTS for t in rest):
        return {"region": None, "ambiguous": True}
    return {"region": " ".join(([city] if city else []) + rest), "ambiguous": False}


def coverage(region: str, product: str) -> str:
    """방문 가능 여부 → "ok" / "no_region"(그 지역 담당 기사 없음) / "no_product"(그 지역에 해당 제품 담당 기사 없음)"""
    in_region = [t for t in _technicians() if t["region"] == region]
    if not in_region:
        return "no_region"
    return "ok" if any(product in t["products"] for t in in_region) else "no_product"
