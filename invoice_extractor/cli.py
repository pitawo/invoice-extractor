import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from . import extract as ex
from .export import to_csv
from .safety import ConfigError, load_key, redact
from .validate import check

ROOT = Path(__file__).resolve().parent.parent
UI_FILES = ["index.html", "app.js", "lib.js", "csp-probe.js", "style.css", "favicon.svg"]


def cmd_extract(a):
    key = load_key()
    model = a.model or os.environ.get("ANTHROPIC_MODEL", "")
    if not model:
        raise ConfigError("モデル名を --model か環境変数 ANTHROPIC_MODEL で指定してください")
    prompt_hash = hashlib.sha256(ex.PROMPT_PATH.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    docs, failed = [], 0
    for p in a.files:
        p = Path(p)
        try:
            docs.append({"file": p.name, "extraction": ex.extract_file(p, key, model)})
            print(f"OK    {p.name}")
        except Exception as e:
            failed += 1
            docs.append({"file": p.name, "error": redact(f"{type(e).__name__}: {e}", key)[:300]})
            print(f"NG    {p.name}: {docs[-1]['error']}")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    result = {"meta": {"source": "api", "model": model, "prompt_sha256": prompt_hash}, "documents": docs}
    (out / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = [d for d in docs if "extraction" in d]
    need = sum(1 for d in ok if check(d["extraction"]))
    print(f"{len(ok)}/{len(docs)} 件を抽出。うち {need} 件は数字が合わないので確認が必要。{out / 'results.json'}")
    return 1 if failed else 0


def build_review(results_path, docs_dir, out_dir):
    """確認画面（docs/ と同じ HTML・JS）を out_dir に組み立てる。書類は out_dir/files/ にコピーする。"""
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    out = Path(out_dir)
    (out / "files").mkdir(parents=True, exist_ok=True)
    for f in UI_FILES:
        shutil.copy(ROOT / "docs" / f, out / f)
    documents = []
    for d in results["documents"]:
        if "extraction" not in d:
            continue
        src = Path(docs_dir) / d["file"]
        shutil.copy(src, out / "files" / d["file"])
        documents.append({"file": d["file"], "path": f"files/{d['file']}", "extraction": d["extraction"]})
    data = {"meta": results.get("meta", {}), "documents": documents}
    (out / "data.js").write_text("window.INVOICE_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n",
                                 encoding="utf-8")
    return out


def cmd_review(a):
    out = build_review(a.results, a.docs_dir, a.out)
    print(f"確認画面を作りました: {out}")
    if a.serve:
        import functools
        import http.server
        h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
        with http.server.ThreadingHTTPServer(("127.0.0.1", a.port), h) as s:
            print(f"http://127.0.0.1:{a.port}/ を開いてください（止めるには Ctrl+C）")
            try:
                s.serve_forever()
            except KeyboardInterrupt:
                pass
    else:
        print(f"次のコマンドで開けます: python -m http.server 8765 --bind 127.0.0.1 --directory {out}")
    return 0


def cmd_csv(a):
    results = json.loads(Path(a.results).read_text(encoding="utf-8"))
    docs = [d for d in results["documents"] if "extraction" in d]
    Path(a.out).write_text(to_csv(docs, a.self_name), encoding="utf-8", newline="")
    print(f"{len(docs)} 件を書き出しました: {a.out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="invoice_extractor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="書類を LLM API で読み取る（キーは環境変数 ANTHROPIC_API_KEY）")
    p.add_argument("files", nargs="+")
    p.add_argument("--model", default="")
    p.add_argument("--out", default="out")
    p.set_defaults(fn=cmd_extract)
    p = sub.add_parser("review", help="確認・修正画面を組み立てる")
    p.add_argument("results")
    p.add_argument("--docs-dir", required=True)
    p.add_argument("--out", default="out/review")
    p.add_argument("--serve", action="store_true")
    p.add_argument("--port", type=int, default=8765)
    p.set_defaults(fn=cmd_review)
    p = sub.add_parser("csv", help="確認画面を通さずに CSV にする")
    p.add_argument("results")
    p.add_argument("--out", default="out/invoices.csv")
    p.add_argument("--self-name", default="")
    p.set_defaults(fn=cmd_csv)
    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except SystemExit:
        raise
    except BaseException as e:  # traceback は出さない。メッセージは必ず伏せ字処理を通す
        try:
            key = load_key()
        except Exception:
            key = None
        print(f"エラー: {type(e).__name__}: {redact(e, key)[:300]}", file=sys.stderr)
        return 1
