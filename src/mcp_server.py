"""AS 접수 MCP 서버 (FastMCP). tools.py의 도메인 함수를 MCP 도구로 노출한다.

노출 도구: search_faq, find_open_ticket, assign_technician, find_earliest_date, save_ticket, update_ticket_status

- 단독 실행(stdio, 외부 MCP 클라이언트용): python -m src.mcp_server
- 에이전트 그래프는 call_tool()로 같은 서버를 프로세스 안(in-memory)에서 MCP 프로토콜로 호출한다.
참고: day7_practice/mcp_server.py
"""
import asyncio
import threading

from fastmcp import Client, FastMCP

from src import tools

mcp = FastMCP("as-callcenter")


@mcp.tool()
def search_faq(query: str, product: str | None = None) -> list[dict]:
    """고객이 말한 증상으로 자가 조치 FAQ 문서를 검색한다.

    Args:
        query: 고객이 말한 증상 문장
        product: 제품군 (TV, 냉장고, 세탁기, 에어컨, 전자레인지). 모르면 비움
    """
    return tools.search_faq(query, product)


@mcp.tool()
def find_open_ticket(phone: str, product: str | None = None) -> list[dict]:
    """고객 전화번호(010-XXXX-XXXX)로 방문 완료 전인 진행 중 접수를 조회한다. 중복 접수 확인과 진행 상황 조회에 쓴다.

    Args:
        phone: 고객 휴대폰 번호
        product: 제품군. 주면 그 제품의 접수만 본다
    """
    return tools.find_open_ticket(phone, product)


@mcp.tool()
def assign_technician(region: str, product: str, visit_date: str) -> dict | None:
    """배정 규칙(지역+제품군+근무일 → 그날 예약 최소 → 기사 ID 순)으로 그날 방문할 기사를 고른다. 없으면 null.

    Args:
        region: 고객 지역 (예: 서울 강남구)
        product: 제품군
        visit_date: 방문 희망일 YYYY-MM-DD
    """
    return tools.assign_technician(region, product, visit_date)


@mcp.tool()
def find_earliest_date(region: str, product: str, after_date: str) -> dict | None:
    """after_date 다음 날부터 14일 안에서 배정 가능한 가장 빠른 날짜와 기사를 찾는다. 없으면 null.

    Args:
        region: 고객 지역
        product: 제품군
        after_date: 이 날짜 이후부터 찾음 (YYYY-MM-DD)
    """
    return tools.find_earliest_date(region, product, after_date)


@mcp.tool()
def save_ticket(ticket: dict) -> dict:
    """새 AS 접수를 저장하고 접수번호가 붙은 접수를 반환한다. status는 예약확정 또는 대기.

    Args:
        ticket: customer_name, phone, region, product, symptom, technician_id, visit_date, status, proposal_attempts
    """
    return tools.save_ticket(ticket)


@mcp.tool()
def update_ticket_status(ticket_id: str, status: str) -> dict | None:
    """접수 상태를 바꾼다 (예약확정, 대기, 방문완료).

    Args:
        ticket_id: 접수번호
        status: 새 상태
    """
    return tools.update_ticket_status(ticket_id, status)


async def _call(name: str, args: dict):
    async with Client(mcp) as client:
        result = await client.call_tool(name, args)
        # 구조화 결과를 그대로 dict/list로 받는다 (list·None 반환은 {"result": ...}로 감싸져 옴)
        sc = result.structured_content or {}
        return sc["result"] if set(sc) == {"result"} else sc or None


_lock = threading.Lock()


def call_tool(name: str, **args):
    """에이전트용 동기 호출: MCP 클라이언트로 도구를 호출하고 결과(파이썬 값)를 돌려준다.

    여러 스레드(API 동시 요청, 병렬 평가)가 같은 서버 객체를 각자의 이벤트 루프에서 부르면 멈출 수 있어
    한 번에 하나씩만 호출한다. 도구는 JSON 파일을 읽고 쓰므로 순서대로 처리하는 편이 데이터에도 안전하다.
    """
    with _lock:
        return asyncio.run(_call(name, args))


if __name__ == "__main__":
    mcp.run()
