"""Streamlit 채팅 화면.

실행 (miniPjt 폴더에서): streamlit run src/app.py
화면은 그래프(run_turn)만 호출하고, 배정·라우팅 로직은 두지 않는다.
"""
import base64
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # src 패키지 import용

import streamlit as st  # noqa: E402

from src.agent import run_turn  # noqa: E402

st.set_page_config(page_title="AS 접수 상담", page_icon="🔧")
GREETING = """안녕하세요, 전자제품 AS 접수 상담입니다. 고장 난 제품과 증상을 말씀해 주세요.

**이렇게 말씀해 주시면 더 빠르게 도와드려요**

🔧 **증상 상담** — *제품 + 언제 · 어떤 증상인지*
> 세탁기가 탈수할 때 덜컹거리며 멈춰요

🗓️ **바로 방문 접수** — *제품·증상 + 성함 · 휴대폰 번호 · 지역 · 희망 방문일*
> 냉장고 냉동실이 안 얼어요. 조치해 봤는데 안 돼요. 홍길동 010-1234-5678 서울 강남구 2026-11-20 방문 희망

*지원 제품: TV · 냉장고 · 세탁기 · 에어컨 · 전자레인지*"""


def apply_background() -> None:
    """블랙 톤 위에 회로기판 무늬 배경을 은은하게 깐다 (색 테마는 .streamlit/config.toml).

    배경 그림은 직접 그린 SVG(src/assets/bg_circuit.svg)라 외부 이미지·저작권·인터넷 연결이 필요 없다.
    """
    svg = (Path(__file__).parent / "assets" / "bg_circuit.svg").read_text(encoding="utf-8")
    data = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode()
    st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{
  background-color: #0D0F12;
  background-image:
    radial-gradient(ellipse at 50% 0%, rgba(242,163,58,0.10), transparent 55%),
    radial-gradient(ellipse at center, transparent 30%, rgba(13,15,18,0.85) 100%),
    url("{data}");
  background-size: auto, auto, 320px 320px;
  background-attachment: fixed;
}}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stBottomBlockContainer"], [data-testid="stBottom"] > div {{ background: transparent; }}
/* 대화 말풍선은 배경 무늬 위에서도 읽히도록 반투명 패널로 */
[data-testid="stChatMessage"] {{
  background: rgba(23,26,31,0.88);
  border: 1px solid #262B33;
  border-radius: 12px;
  padding: 0.75rem 1rem;
}}
[data-testid="stSidebar"] {{ background: rgba(18,20,24,0.96); border-right: 1px solid #262B33; }}
h1 {{ letter-spacing: -0.01em; }}
</style>""", unsafe_allow_html=True)


apply_background()


def new_session() -> None:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.history = [{"role": "assistant", "content": GREETING}]
    st.session_state.last = None


if "thread_id" not in st.session_state:
    new_session()

# ---------------- 사이드바: 에이전트 내부 상태
with st.sidebar:
    st.subheader("상담 상태")
    last = st.session_state.last
    st.write(f"**상태:** {last['status'] if last else '대기 중'}")
    if st.button("새 상담 시작"):
        new_session()
        st.rerun()
    if last:
        st.subheader("이번 턴 trace")
        for t in last["trace"]:
            with st.expander(t["step"]):
                st.caption(f"input: {t['input']}")
                st.caption(f"output: {t['output']}")
        if last["contexts"]:
            st.subheader("근거 FAQ")
            for c in last["contexts"]:
                st.caption(c["doc_id"])
    st.caption(f"thread_id: {st.session_state.thread_id[:8]}")

# ---------------- 채팅
st.title("전자제품 AS 접수 상담")
for m in st.session_state.history:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

def send(text: str) -> None:
    """입력 1건을 그래프에 보내고 대화 기록에 남긴다."""
    with st.spinner("확인 중…"):
        result = run_turn(st.session_state.thread_id, text)
    # 화면에는 마스킹된 입력(010-****-1234 등)을 표시한다
    st.session_state.history.append({"role": "user", "content": result["question"]})
    st.session_state.history.append({"role": "assistant", "content": result["answer"]})
    st.session_state.last = result
    if result["status"] == "상담 종료":
        # 고객이 취소·상담 거부 → 마무리 인사를 남기고 새 상담(새 thread)으로 전환
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.history.append({"role": "assistant", "content": "— 새 상담 —\n\n" + GREETING})
        st.session_state.last = None
    st.rerun()


# 방문 일정 승인 대기(HITL) 중이면 버튼으로도 답할 수 있게 한다 (버튼도 같은 문장을 그래프에 보냄)
last = st.session_state.last
clicked = None
if last and last["stage"] == "hitl":
    col1, col2 = st.columns(2)
    if col1.button("이 일정으로 확정", type="primary", use_container_width=True):
        clicked = "확정"
    if col2.button("다른 날짜로 해주세요", use_container_width=True):
        clicked = "다른 날짜로 해주세요"
elif last and last["stage"] == "resolve_check":
    col1, col2 = st.columns(2)
    if col1.button("해결됐어요", use_container_width=True):
        clicked = "해결됐어요"
    if col2.button("그래도 안 돼요", use_container_width=True):
        clicked = "그래도 안 돼요"

prompt = st.chat_input("증상이나 접수 정보를 입력하세요")
if clicked or prompt:
    send(clicked or prompt)
