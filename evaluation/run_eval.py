"""평가 스크립트: 한 번 실행으로 4개 항목을 측정하고 건별 결과를 CSV로 저장한다.

실행 (miniPjt 폴더에서): python evaluation/run_eval.py
       일부만: python evaluation/run_eval.py --only inout,rag

1. 인-아웃 세트   evaluation/test_queries.csv 20건 → LLM 판정(JudgeResult) + trace로 기대 도구 호출 확인
                 통과 = expected_traits 모두 충족 + forbidden 없음 + expected_tools 모두 호출. 목표 90% 이상
2. RAG (RAGAS 4지표)  data/eval_rag.json 20건 → context_recall, context_precision, faithfulness, answer_relevancy
3. 기사 배정 정확도   data/eval_assign.json 15건 → MCP assign_technician 결과 vs 정답
4. 가드레일          data/eval_guard.json 30건 → 차단율(차단 20건 중) · 오차단률(정상 10건 중)

결과: evaluation/results/{inout,rag,assign,guard}.csv, summary.json
"""
import argparse
import csv
import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation import rag_metrics  # noqa: E402
from src.consult import retriever  # noqa: E402
from src.agent import run_turn  # noqa: E402
from src.judge.chains import judge_case  # noqa: E402
from src.config import settings  # noqa: E402
from src.guard.rules import check_input  # noqa: E402
from src.booking.sample_data import reset_data  # noqa: E402
from src.mcp_server import call_tool  # noqa: E402

RESULTS = ROOT / "evaluation" / "results"
PASS_TARGET = 0.90
TOOL_STEPS = {"search_faq", "find_open_ticket", "assign_technician", "find_earliest_date",
              "save_ticket", "update_ticket_status"}


def load_json(name: str) -> list[dict]:
    return json.loads((settings.data_dir / name).read_text(encoding="utf-8"))


def write_csv(name: str, rows: list[dict]) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    with open(RESULTS / name, "w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def split(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(";") if x.strip()]


# ---------------------------------------------------------------- 1. 인-아웃 세트
def eval_inout() -> dict:
    with open(ROOT / "evaluation" / "test_queries.csv", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))
    rows = []
    for c in cases:
        reset_data()  # 케이스마다 같은 초기 데이터에서 시작
        r = run_turn(str(uuid.uuid4()), c["input"])
        called = [t["step"] for t in r["trace"] if t["step"] in TOOL_STEPS]
        missing_tools = [t for t in split(c["expected_tools"]) if t not in called]
        # 판정 LLM에도 마스킹된 입력만 보낸다 (r["question"] = 주민·카드·전화번호 마스킹본)
        j = judge_case(r["question"], r["answer"], c["expected_traits"], c["forbidden"])
        passed = j["passed"] and not j["found_forbidden"] and not missing_tools
        rows.append({"id": c["id"], "category": c["category"], "passed": passed, "judge_passed": j["passed"],
                     "missing_traits": "; ".join(j["missing_traits"]), "found_forbidden": "; ".join(j["found_forbidden"]),
                     "expected_tools": c["expected_tools"], "called_tools": "; ".join(called),
                     "missing_tools": "; ".join(missing_tools), "reason": j["reason"],
                     "input": r["question"], "answer": r["answer"]})
        print(f"  [{'PASS' if passed else 'FAIL'}] #{c['id']:>2} {c['category']:<9} {r['question'][:40]}")
    reset_data()
    write_csv("inout.csv", rows)
    n, ok = len(rows), sum(r["passed"] for r in rows)
    by_cat = {}
    for r in rows:
        t = by_cat.setdefault(r["category"], [0, 0])
        t[0] += r["passed"]
        t[1] += 1
    return {"passed": ok, "total": n, "rate": ok / n, "target": PASS_TARGET,
            "goal_met": ok / n >= PASS_TARGET, "by_category": {k: f"{a}/{b}" for k, (a, b) in by_cat.items()}}


# ---------------------------------------------------------------- 2. RAG (RAGAS 4지표)
def _rag_one(item: dict) -> dict:
    r = run_turn(str(uuid.uuid4()), item["question"])
    hits = retriever.search(item["question"], k=3)          # 상담 노드와 같은 검색기(같은 거리 기준)
    contexts = [h["text"] for h in hits]
    scores = rag_metrics.score_all(item["question"], r["answer"], contexts, item["reference"])
    top = hits[0]["doc_id"] if hits else ""
    return {"id": item["id"], "question": item["question"], "expected_doc": item["doc_id"], "top_doc": top,
            "hit_at_1": top == item["doc_id"], **{k: round(v, 3) for k, v in scores.items()},
            "retrieved": "; ".join(h["doc_id"] for h in hits), "answer": r["answer"]}


def _rag_safe(item: dict) -> dict | None:
    """한 건이 실패해도(호출 한도 등) 전체 평가를 멈추지 않는다. 실패 건은 점수 평균에서 빼고 따로 보고."""
    try:
        return _rag_one(item)
    except Exception as e:
        print(f"  [오류] RAG #{item['id']}: {type(e).__name__}: {str(e)[:80]}")
        return {"id": item["id"], "error": f"{type(e).__name__}: {e}"}


def eval_rag() -> dict:
    with ThreadPoolExecutor(max_workers=2) as ex:   # 동시 호출이 많으면 Bedrock 호출 한도에 걸림
        results = list(ex.map(_rag_safe, load_json("eval_rag.json")))
    errors = [r for r in results if "error" in r]
    rows = [r for r in results if "error" not in r]
    if not rows:
        return {"errors": len(errors)}
    for r in rows:
        print(f"  #{r['id']:>2} hit@1={'O' if r['hit_at_1'] else 'X'} recall={r['context_recall']:.2f} "
              f"precision={r['context_precision']:.2f} faith={r['faithfulness']:.2f} relevancy={r['answer_relevancy']:.2f}")
    write_csv("rag.csv", rows)
    keys = ["context_recall", "context_precision", "faithfulness", "answer_relevancy"]
    out = {k: round(sum(r[k] for r in rows) / len(rows), 3) for k in keys}
    out["hit_at_1"] = round(sum(r["hit_at_1"] for r in rows) / len(rows), 3)
    out["evaluated"], out["errors"] = len(rows), len(errors)
    return out


# ---------------------------------------------------------------- 3. 기사 배정
def eval_assign() -> dict:
    reset_data()
    rows = []
    for a in load_json("eval_assign.json"):
        hit = call_tool("assign_technician", region=a["region"], product=a["product"], visit_date=a["visit_date"])
        got = hit["technician_id"] if hit else None
        rows.append({"id": a["id"], "region": a["region"], "product": a["product"], "visit_date": a["visit_date"],
                     "expected": a["expected"], "got": got, "correct": got == a["expected"], "note": a["note"]})
    write_csv("assign.csv", rows)
    ok = sum(r["correct"] for r in rows)
    return {"correct": ok, "total": len(rows), "accuracy": round(ok / len(rows), 3)}


# ---------------------------------------------------------------- 4. 가드레일
def _guard_one(g: dict) -> dict:
    r = check_input(g["text"])
    want_block = g["expected"] == "block"
    return {"id": g["id"], "expected": g["expected"], "expected_category": g["category"],
            "blocked": r["blocked"], "category": r["category"], "by": r["by"],
            "correct": r["blocked"] == want_block, "text": g["text"], "reason": r["reason"]}


def eval_guard() -> dict:
    with ThreadPoolExecutor(max_workers=4) as ex:
        rows = list(ex.map(_guard_one, load_json("eval_guard.json")))
    write_csv("guard.csv", rows)
    attacks = [r for r in rows if r["expected"] == "block"]
    normals = [r for r in rows if r["expected"] == "allow"]
    blocked = sum(r["blocked"] for r in attacks)
    false_blocked = sum(r["blocked"] for r in normals)
    for r in rows:
        if not r["correct"]:
            print(f"  [오판] #{r['id']} 기대={r['expected']} 결과={'차단' if r['blocked'] else '통과'} | {r['text']}")
    return {"block_rate": round(blocked / len(attacks), 3), "blocked": f"{blocked}/{len(attacks)}",
            "false_block_rate": round(false_blocked / len(normals), 3), "false_blocked": f"{false_blocked}/{len(normals)}"}


# ---------------------------------------------------------------- 실행
STEPS = {"inout": ("인-아웃 세트", eval_inout), "rag": ("RAG (RAGAS 4지표)", eval_rag),
         "assign": ("기사 배정", eval_assign), "guard": ("가드레일", eval_guard)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=",".join(STEPS), help="실행할 항목 (쉼표 구분): " + ",".join(STEPS))
    names = [n for n in ap.parse_args().only.split(",") if n in STEPS]

    summary = {"run_at": datetime.now().isoformat(timespec="seconds"),
               "models": {"answer": settings.llm_model_id, "judge": settings.judge_model_id,
                          "embedding": settings.embed_model_id}}
    for n in names:
        title, fn = STEPS[n]
        print(f"\n=== {title}")
        summary[n] = fn()
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n================ 평가 요약 ================")
    if "inout" in summary:
        s = summary["inout"]
        print(f"인-아웃 세트   : {s['passed']}/{s['total']} 통과 ({s['rate']:.0%}) · 목표 {PASS_TARGET:.0%} "
              f"→ {'PASS' if s['goal_met'] else 'FAIL'}  {s['by_category']}")
    if "rag" in summary:
        s = summary["rag"]
        if "context_recall" not in s:
            print(f"RAG (RAGAS)    : 모든 건 오류 ({s['errors']}건)")
        else:
            print(f"RAG (RAGAS)    : context_recall {s['context_recall']:.2f} · context_precision {s['context_precision']:.2f}"
                  f" · faithfulness {s['faithfulness']:.2f} · answer_relevancy {s['answer_relevancy']:.2f}"
                  f" · hit@1 {s['hit_at_1']:.2f} ({s['evaluated']}건 평가, 오류 {s['errors']}건)")
    if "assign" in summary:
        s = summary["assign"]
        print(f"기사 배정      : {s['correct']}/{s['total']} 정확도 {s['accuracy']:.0%}")
    if "guard" in summary:
        s = summary["guard"]
        print(f"가드레일       : 차단율 {s['block_rate']:.0%} ({s['blocked']}) · 오차단률 {s['false_block_rate']:.0%} ({s['false_blocked']})")
    print(f"건별 결과      : {RESULTS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
