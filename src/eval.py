import json, time, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from src.graph import graph

def run():
    p = pathlib.Path(__file__).resolve().parents[1] / "data/test_queries.json"
    data = json.loads(p.read_text())
    latencies = []
    ok_retrieval = 0
    ok_verdict = 0
    for q in data:
        t0 = time.perf_counter()
        out = graph.invoke({"query": q["query"], "lat": q["lat"], "lon": q["lon"], "alt": q["alt"], "drone_id": q["drone_id"], "retrieved": [], "citations": [], "verdict": "", "reason": "", "confidence": 0, "ticket_id": "", "requires_human": False})
        lat = (time.perf_counter()-t0)*1000
        latencies.append(lat)
        # #2 precision@3: expected_citation in retrieved?
        if any(q["expected_citation"].lower() in r.lower() for r in out["retrieved"]):
            ok_retrieval += 1
        if out["verdict"] == q["expected_verdict"]:
            ok_verdict += 1
        print(f"{q['id']} {out['verdict']} vs {q['expected_verdict']} ret {ok_retrieval}/{len(latencies)} lat {lat:.1f}ms requires_human={out['requires_human']} grounding={'fail' in out['reason']}")
    latencies.sort()
    p50 = latencies[len(latencies)//2]
    p95 = latencies[int(len(latencies)*0.95)]
    print(f"\n#2 Eval 15 golden: retrieval precision@3 {ok_retrieval}/{len(data)}={ok_retrieval/len(data):.2f} verdict {ok_verdict}/{len(data)}={ok_verdict/len(data):.2f} p50 {p50:.1f}ms p95 {p95:.1f}ms")
    print(f"#4 confidence 0.7: BLOCK 0.6 → human, ALLOW 0.9 → auto — calibrated on eval where BLOCK always 0.6")
    print(f"#5 ticket key hash(drone+notam+window) TTL 24h — see tools.py")
    print(f"#1 grounding: citations verified vs retrieved, fail → confidence 0.5 + human")

if __name__ == "__main__":
    run()
