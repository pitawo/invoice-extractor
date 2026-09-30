"""抽出結果（examples/results.json）を、書類を作ったときの正解（tests/truth.json）と項目別に照合する。

使い方: python tools/compare_truth.py [results.json]
一致は「完全一致」のみ（会社名・品名は文字列一致）。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC_FIELDS = ["doc_type", "doc_number", "issue_date", "due_date", "issuer", "recipient", "subtotal", "tax", "total"]
ITEM_FIELDS = ["description", "quantity", "unit_price", "amount", "tax_rate"]


def compare(results, truth):
    """戻り値: (項目名 -> [一致数, 総数], 不一致の一覧)"""
    by_stem = {Path(t["file"]).stem: t for t in truth}
    stats = {k: [0, 0] for k in DOC_FIELDS + ["item_count"] + ["item." + k for k in ITEM_FIELDS]}
    misses = []
    for d in results["documents"]:
        stem = Path(d["file"]).stem
        t, e = by_stem[stem], d["extraction"]
        for k in DOC_FIELDS:
            stats[k][1] += 1
            if e.get(k) == t[k]:
                stats[k][0] += 1
            else:
                misses.append((stem, k, t[k], e.get(k)))
        ti, ei = t["items"], e.get("items") or []
        stats["item_count"][1] += 1
        if len(ti) == len(ei):
            stats["item_count"][0] += 1
        else:
            misses.append((stem, "item_count", len(ti), len(ei)))
        for a, b in zip(ti, ei):
            for k in ITEM_FIELDS:
                stats["item." + k][1] += 1
                if a[k] == b.get(k):
                    stats["item." + k][0] += 1
                else:
                    misses.append((stem, "item." + k, a[k], b.get(k)))
    return stats, misses


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "examples" / "results.json"
    results = json.loads(path.read_text(encoding="utf-8"))
    truth = json.loads((ROOT / "tests" / "truth.json").read_text(encoding="utf-8"))
    stats, misses = compare(results, truth)
    tot_ok = sum(v[0] for v in stats.values())
    tot = sum(v[1] for v in stats.values())
    for k, (ok, n) in stats.items():
        print(f"{k:22s} {ok}/{n}")
    print(f"{'合計':22s} {tot_ok}/{tot}")
    print("不一致:", len(misses))
    for m in misses:
        print("  ", m)


if __name__ == "__main__":
    main()
