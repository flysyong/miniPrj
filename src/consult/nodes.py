"""상담 그래프 노드: FAQ 검색 → 자가 조치 안내 → 해결 여부 확인."""
import re

from langgraph.graph import END

from src.booking.prompts import ASK_INTAKE
from src.consult.products import detect_products, normalize_products, product_gate, unsupported_message
from src.consult.prompts import answer_messages
from src.mcp_server import call_tool
from src.shared.llm import main_llm, text_of
from src.shared.turn import last_user_text, say, step

# 안전 증상: 자가 조치를 안내하지 않고 사용 중지 안내 후 바로 기사 접수 (SERVICE.md 4번 정책)
SAFETY = r"연기|타는\s?냄새|탄\s?냄새|타는\s?듯|감전|누전|화재|불이\s?(났|붙)"
NOT_RESOLVED = r"안\s?돼|안\s?됨|안\s?되|여전|그대로|안\s?켜|안\s?나와|해봤는데|아니"
RESOLVED = r"해결|됐어|됩니다|돼요|켜졌|나와요|고마|감사"


def consult(state: dict) -> dict:
    """증상으로 FAQ를 검색하고, 검색 결과만 근거로 자가 조치를 안내한다."""
    text = last_user_text(state)
    products = detect_products(text)
    gate_trace = []
    if not products and not state.get("product"):
        gate = product_gate(text)
        gate_trace = gate["trace"]
        if gate["unsupported"]:
            return say(unsupported_message(gate["unsupported"]), stage="consult", product=None, trace=gate_trace)
        if gate["product"]:          # 키워드는 못 찾았지만 LLM이 지원 제품으로 판정 (예: 김치냉장고 표현 변형)
            products = [gate["product"]]
    if len(products) > 1:
        return say(f"{', '.join(products)} 여러 제품이 고장 나셨군요. 한 번에 한 제품씩 접수해 드릴게요. "
                   "먼저 상담할 제품과 증상을 알려 주세요.", stage="consult",
                   trace=[step("consult", text, f"다중 제품 {products} → 하나씩 안내")])
    product = products[0] if products else state.get("product")
    if re.search(SAFETY, text):
        return say("안전을 위해 지금 바로 제품 사용을 멈추고 전원 플러그를 뽑아 주세요. "
                   "이 증상은 자가 조치 대신 기사 점검이 필요해 방문 접수로 도와드릴게요.\n" + ASK_INTAKE,
                   stage="intake", product=product, symptom=text, status="접수 정보 입력",
                   trace=[step("safety_check", text, "안전 증상 → 자가 조치 생략, 바로 접수")])
    query = normalize_products(text)      # 티브이 → TV 등 (FAQ 표준 이름에 맞춤)
    hits = call_tool("search_faq", query=query, product=product)
    trace = gate_trace + [step("search_faq", f"{query} (제품: {product or '미지정'})",
                  ", ".join(f"{h['doc_id']}(거리 {h['distance']}, BM25 {h['bm25']}, {h['match']})" for h in hits)
                  or "맞는 문서 없음")]

    if not hits:
        if not product:
            return say("어떤 제품에서 어떤 증상이 있는지 조금 더 구체적으로 알려 주세요. "
                       "예: \"세탁기가 탈수할 때 멈춰요\"", stage="consult", trace=trace)
        return say(f"말씀하신 증상에 맞는 자가 조치 안내가 없어요. 기사 방문 접수로 도와드릴게요.\n{ASK_INTAKE}",
                   stage="intake", product=product, symptom=text, status="접수 정보 입력", trace=trace)

    top = hits[0]
    answer = text_of(main_llm().invoke(answer_messages(top["doc_id"], top["text"], text)))
    trace.append(step("generate_answer", f"faq={top['doc_id']}", answer[:80] + "…"))
    return say(answer, stage="resolve_check", product=top["product"], symptom=text, status="상담 중",
               contexts=[{"doc_id": top["doc_id"], "text": top["text"]}], trace=trace)


def resolve_check(state: dict) -> dict:
    """자가 조치 후 해결 여부를 파이썬 규칙으로 판정한다."""
    text = last_user_text(state)
    if re.search(NOT_RESOLVED, text):
        return say(f"불편을 드려 죄송합니다. 기사 방문 접수로 도와드릴게요.\n{ASK_INTAKE}",
                   stage="intake", status="접수 정보 입력", trace=[step("resolve_check", text, "미해결 → 접수 단계")])
    if re.search(RESOLVED, text):
        return say("해결되어 다행입니다. 같은 증상이 다시 생기면 언제든 말씀해 주세요. 상담을 종료합니다.",
                   stage="done", status="자가해결종료", trace=[step("resolve_check", text, "해결 → 종료")])
    return {"stage": "consult", "trace": [step("resolve_check", text, "판단 불가 → 새 문의로 상담")]}


def after_resolve(state: dict) -> str:
    return "consult" if state.get("stage") == "consult" else END
