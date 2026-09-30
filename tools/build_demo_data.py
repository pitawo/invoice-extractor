"""examples/results.json から、公開デモ用の docs/data.js を作る（書類画像は docs/samples/ を参照）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
r = json.loads((ROOT / "examples" / "results.json").read_text(encoding="utf-8"))
docs = [{"file": d["file"], "path": "samples/" + d["file"], "extraction": d["extraction"]} for d in r["documents"]]
data = {"meta": r["meta"], "documents": docs}
(ROOT / "docs" / "data.js").write_text("window.INVOICE_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
                                       encoding="utf-8")
print(len(docs), "docs")
