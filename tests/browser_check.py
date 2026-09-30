"""実ブラウザ（Edge/Chrome）でデモを開いて確かめる。playwright が必要（任意。単体テストには含めない）。

  pip install playwright
  python tests/browser_check.py            # 確認だけ
  python tests/browser_check.py --shots out/shots   # スクリーンショットも撮る

確かめること:
  1. ページが発生させたリクエストは、すべて配信元（127.0.0.1）宛て
  2. 「わざと試す」ボタンで、ブラウザが外部通信を止める（securitypolicyviolation が出る）
  3. 【検出できるかの確認】CSP を外した複製では、同じ確認が「止めた」と言わない
  4. 金額を書き換えると「要確認」が出る／CSV ダウンロードの中身が lib.js の出力と一致
"""
import functools
import http.server
import shutil
import sys
import tempfile
import threading
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def serve(directory):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass

    h = functools.partial(Quiet, directory=str(directory))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def launch(p):
    for ch in ("msedge", "chrome"):
        try:
            return p.chromium.launch(channel=ch)
        except Exception:
            continue
    raise SystemExit("Edge / Chrome を起動できません")


def probe(browser, url):
    """ページを開き、「わざと試す」を押して、(全リクエストのURL, 表示された結果文, 失敗したリクエスト) を返す。"""
    page = browser.new_page()
    reqs, failed = [], []
    page.on("request", lambda r: reqs.append(r.url))
    page.on("requestfailed", lambda r: failed.append(r.url))
    page.goto(url)
    page.wait_for_load_state("networkidle")
    before = list(reqs)
    page.click("#try-net")
    for _ in range(150):  # CSP のせいで文字列の評価（wait_for_function）は使えないので、外から待つ
        result = page.inner_text("#try-net-result")
        if result and "試しています" not in result:
            break
        page.wait_for_timeout(100)
    return page, before, result, failed, list(reqs)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    shots = None
    if "--shots" in sys.argv:
        shots = Path(sys.argv[sys.argv.index("--shots") + 1])
        shots.mkdir(parents=True, exist_ok=True)
    srv = serve(DOCS)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    # CSP を外した複製（検出できるかの確認用）
    tmp = Path(tempfile.mkdtemp())
    for f in DOCS.iterdir():
        if f.is_file():
            shutil.copy(f, tmp / f.name)
    shutil.copytree(DOCS / "samples", tmp / "samples")
    idx = (tmp / "index.html").read_text(encoding="utf-8")
    import re
    (tmp / "index.html").write_text(re.sub(r'<meta http-equiv="Content-Security-Policy"[^>]*>', "", idx), encoding="utf-8")
    srv2 = serve(tmp)
    base2 = f"http://127.0.0.1:{srv2.server_address[1]}"

    ok = True
    with sync_playwright() as p:
        b = launch(p)
        page, before, result, failed, allreqs = probe(b, base + "/")
        external = [u for u in before if not u.startswith(base)]
        print(f"[1] ページ読み込み時のリクエスト {len(before)} 件、配信元以外 {len(external)} 件")
        ok &= not external
        print("[2] 外部通信の試行（CSP あり）:", result)
        ok &= "ブロックされました" in result
        ext_after = [u for u in allreqs if not u.startswith(base)]
        print(f"[2b] 試行のあとも、配信元以外へのリクエストは {len(ext_after)} 件")
        ok &= not ext_after

        page3, _, result3, failed3, allreqs3 = probe(b, base2 + "/")
        print("[3] CSP を外した複製で同じ試行:", result3)
        ext3 = [u for u in allreqs3 if not u.startswith(base2)]
        print(f"[3b] CSP なしでは、配信元以外へのリクエストが {len(ext3)} 件出る（＝計測は外への通信を検出できる）")
        ok &= "ブロックされました" not in result3 and len(ext3) >= 1
        page3.close()

        # 4. 編集で要確認が出る・CSV
        page.goto(base + "/")
        page.wait_for_load_state("networkidle")
        n0 = page.locator("#flags li.clear").count()
        page.fill('input[aria-label="行1 amount"]', "9999")
        n1 = page.locator("#flags li:not(.clear)").count()
        print(f"[4] 金額を書き換える前は一致表示 {n0} / 書き換え後の要確認 {n1} 件")
        ok &= n0 == 1 and n1 >= 1
        with page.expect_download() as dl:
            page.click("#dl-csv")
        path = dl.value.path()
        text = Path(path).read_bytes().decode("utf-8")
        print("    CSV 先頭:", text[:60].replace("\r\n", " | "))
        ok &= text.startswith("﻿ファイル,") and "要確認" in text
        if shots:
            page.set_viewport_size({"width": 1200, "height": 900})
            page.click('#list button[data-i="0"]')
            page.screenshot(path=str(shots / "desktop.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 800})
            page.screenshot(path=str(shots / "mobile.png"), full_page=True)
        b.close()
    print("結果:", "OK" if ok else "NG")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
