"""公開デモの静的な検査、リポジトリのキー検査、検証・CSV・照合ツールのテスト。
どの検査も、先に「壊した複製を検出できる」ことを確かめてから、実物が問題なしであることを確かめる。"""
import copy
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from invoice_extractor.export import to_csv
from invoice_extractor.validate import check

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import check_no_secrets  # noqa: E402
import compare_truth  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
RESULTS = json.loads((ROOT / "examples" / "results.json").read_text(encoding="utf-8"))
TRUTH = json.loads((ROOT / "tests" / "truth.json").read_text(encoding="utf-8"))


def read(name):
    return (DOCS / name).read_text(encoding="utf-8")


# ---- 公開デモの静的ルール（違反の一覧を返す） ----
def demo_problems(html, scripts):
    """html: index.html の文字列、scripts: {ファイル名: 中身}"""
    p = []
    m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"', html)
    if not m:
        p.append("CSP の meta が無い")
    else:
        csp = m.group(1)
        for need in ("default-src 'none'", "connect-src 'none'", "form-action 'none'"):
            if need not in csp:
                p.append(f"CSP に {need} が無い")
        if "unsafe-inline" in csp or "unsafe-eval" in csp or "*" in csp:
            p.append("CSP が緩い")
        head_before = html[:m.start()]
        if re.search(r"<(script|link|img)\b", head_before):
            p.append("CSP より前にリソース読み込みがある")
    if re.search(r"https?://", html):
        p.append("index.html に外部 URL がある")
    if re.search(r"<input[^>]*type=[\"']password", html, re.I):
        p.append("password 入力欄がある")
    if re.search(r"<script(?![^>]*\bsrc=)", html):
        p.append("インライン script がある")
    for name, js in scripts.items():
        if re.search(r"https?://", js) and name != "csp-probe.js":
            p.append(f"{name} に外部 URL がある")
        pat = r"\b(XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts)\b|\bimport\s*\(" + \
              ("" if name == "csp-probe.js" else r"|\bfetch\s*\(")
        if re.search(pat, js):
            p.append(f"{name} に通信のコードがある")
        if re.search(r"(?i)(api[_-]?key|x-api-key|password|secret)", js) and name != "data.js":
            p.append(f"{name} にキー関連の語がある")
        if name == "csp-probe.js" and re.search(r"\bbody\s*:", js):
            p.append("csp-probe.js が body を送っている")
    return p


def real_scripts():
    return {n: read(n) for n in ("app.js", "lib.js", "csp-probe.js", "data.js")}


class TestDemoStaticRules(unittest.TestCase):
    def test_rules_detect_broken_copies(self):
        html, sc = read("index.html"), real_scripts()
        cases = {
            "CSP を外す": (re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", html), sc),
            "connect-src を緩める": (html.replace("connect-src 'none'", "connect-src *"), sc),
            "unsafe-inline": (html.replace("style-src 'self'", "style-src 'self' 'unsafe-inline'"), sc),
            "外部 URL": (html.replace("<main>", '<main><a href="https://example.org/">x</a>'), sc),
            "password 欄": (html.replace("<main>", '<main><input type="password">'), sc),
            "インライン script": (html.replace("</body>", "<script>1</script></body>"), sc),
            "CSP より前に script": (html.replace("<head>", '<head><script src="x.js"></script>'), sc),
            "fetch を足す": (html, {**sc, "app.js": sc["app.js"] + "\nfetch('/x');"}),
            "XHR を足す": (html, {**sc, "lib.js": sc["lib.js"] + "\nnew XMLHttpRequest();"}),
            "キー欄を足す": (html, {**sc, "app.js": sc["app.js"] + "\nvar apiKey = 1;"}),
            "probe が body を送る": (html, {**sc, "csp-probe.js": sc["csp-probe.js"] + "\nfetch(u,{body:1})"}),
        }
        for name, (h, s) in cases.items():
            self.assertTrue(demo_problems(h, s), f"検出できていない: {name}")

    def test_real_demo_is_clean(self):
        self.assertEqual(demo_problems(read("index.html"), real_scripts()), [])


class TestRepoSecretsScan(unittest.TestCase):
    def test_scanner_detects_planted_keys(self):
        planted = ["sk-ant-" + "A" * 30, "sk-" + "b" * 40, "AIza" + "C" * 35, 'api_key = "' + "d" * 20 + '"']
        for s in planted:
            with tempfile.TemporaryDirectory() as d:
                (Path(d) / ".gitignore").write_text(".env\n")
                (Path(d) / "x.py").write_text(f"x = '{s}'\n" if "=" not in s else s + "\n")
                self.assertTrue(check_no_secrets.scan(d), f"検出できていない: {s[:8]}…")

    def test_scanner_detects_missing_gitignore_env(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / ".gitignore").write_text("out/\n")
            self.assertTrue(check_no_secrets.scan(d))

    def test_real_repo_is_clean(self):
        self.assertEqual(check_no_secrets.scan(ROOT), [])
        self.assertEqual(check_no_secrets.tracked_env_files(ROOT), [])


class TestPreextractedResults(unittest.TestCase):
    def test_prompt_hash_matches_bundled_prompt(self):
        h = hashlib.sha256((ROOT / "prompts" / "extract_prompt.md").read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        self.assertEqual(RESULTS["meta"]["prompt_sha256"], h)

    def test_compare_detects_mismatch_then_reports_actual(self):
        bad = copy.deepcopy(RESULTS)
        bad["documents"][0]["extraction"]["total"] += 1
        bad["documents"][1]["extraction"]["items"][0]["description"] += "x"
        bad["documents"][2]["extraction"]["items"].pop()
        _, misses = compare_truth.compare(bad, TRUTH)
        fields = {m[1] for m in misses}
        self.assertTrue({"total", "item.description", "item_count"} <= fields)
        stats, misses = compare_truth.compare(RESULTS, TRUTH)
        self.assertEqual(misses, [])
        self.assertEqual(sum(v[1] for v in stats.values()), 230)

    def test_demo_data_js_matches_results(self):
        js = read("data.js")
        data = json.loads(js[js.index("=") + 1:].strip().rstrip(";"))
        self.assertEqual([d["extraction"] for d in data["documents"]], [d["extraction"] for d in RESULTS["documents"]])

    def test_all_sample_documents_are_marked_fictional(self):
        for d in RESULTS["documents"]:
            self.assertTrue((DOCS / "samples" / d["file"]).exists(), d["file"])


class TestValidate(unittest.TestCase):
    def doc(self):
        return copy.deepcopy(RESULTS["documents"][0]["extraction"])

    def test_real_results_have_no_flags(self):
        self.assertEqual([check(d["extraction"]) for d in RESULTS["documents"]], [[] for _ in RESULTS["documents"]])

    def test_detects_each_kind_of_inconsistency(self):
        d = self.doc(); d["items"][0]["amount"] += 1
        self.assertEqual(len(check(d)), 2)  # 行の掛け算・小計
        d = self.doc(); d["total"] += 1
        self.assertEqual(check(d), ["小計＋消費税が合計と合わない"])
        d = self.doc(); d["issue_date"] = None
        self.assertEqual(check(d), ["発行日が読めていない"])
        d = self.doc(); d["issue_date"] = "2026/08/31"
        self.assertEqual(check(d), ["発行日の形式が YYYY-MM-DD ではない"])
        d = self.doc(); d["items"] = []
        self.assertIn("明細が1行も無い", check(d))


TRICKY = {"file": "=evil.png", "extraction": {
    "doc_type": "invoice", "doc_number": "-1+2", "issue_date": "2026-01-01", "due_date": None,
    "issuer": '会社,"A"', "recipient": "デモ販売株式会社",
    "items": [{"description": "=HYPERLINK(\"http://x\")", "quantity": 1.5, "unit_price": 100, "amount": 150, "tax_rate": 0.1},
              {"description": "改行\nあり", "quantity": 1, "unit_price": -50, "amount": -50, "tax_rate": None}],
    "subtotal": 100, "tax": 10, "total": 110}}


class TestCsvAndJsParity(unittest.TestCase):
    def js(self, documents, self_name):
        r = subprocess.run(["node", str(ROOT / "tests" / "js_runner.js")], input=json.dumps({"documents": documents, "self": self_name}),
                           capture_output=True, text=True, encoding="utf-8", check=True)
        return json.loads(r.stdout)

    def cases(self):
        bad = copy.deepcopy(RESULTS["documents"][3]); bad["extraction"]["items"][0]["amount"] = 1
        bad2 = copy.deepcopy(RESULTS["documents"][4]); bad2["confirmed"] = True; bad2["extraction"]["total"] = 0
        return RESULTS["documents"] + [TRICKY, bad, bad2]

    def test_formula_injection_is_neutralised(self):
        csv_text = to_csv([TRICKY], "デモ販売株式会社")
        self.assertIn("'=evil.png", csv_text)
        self.assertIn("'-1+2", csv_text)
        self.assertNotIn(",=HYPERLINK", csv_text)
        self.assertIn(",-50,", csv_text)  # 数値の負数は式扱いにしない（先頭に ' を付けない）

    def test_python_and_js_agree(self):
        docs = self.cases()
        out = self.js(docs, "デモ販売株式会社")
        self.assertEqual(out["csv"], to_csv(docs, "デモ販売株式会社"))
        self.assertEqual(out["flags"], [check(d["extraction"]) for d in docs])
        self.assertTrue(any(out["flags"]))  # 空振りでない：不整合ありの入力が含まれている

    def test_counterparty_column(self):
        rows = to_csv(RESULTS["documents"][:3], "デモ販売株式会社").splitlines()
        self.assertEqual(rows[1].split(",")[5], "サンプル商事株式会社")  # 請求書：発行元
        self.assertEqual(rows[-1].split(",")[5], "ピヨピヨ電材株式会社")  # 注文書：宛先


if __name__ == "__main__":
    unittest.main()
