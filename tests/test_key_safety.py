"""キーが、ログ・出力ファイル・例外・画面に出ないことのテスト。

順番が大事：先に「漏れたら検出できる」ことを確かめ（TestDetectorWorks）、そのあとで「0件」を確かめる。
検出器が壊れていると、否定形のテストは空振りでも通ってしまうため。
"""
import base64
import contextlib
import http.server
import io
import json
import logging
import tempfile
import threading
import traceback
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from invoice_extractor import extract as ex
from invoice_extractor.cli import main
from invoice_extractor.safety import ConfigError, Secret, load_key, redact

KEY = "dummy-key-XXXX"
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "docs" / "samples" / "inv_001.png"
GOOD_TEXT = json.dumps({"doc_type": "invoice", "items": [{"description": "x", "quantity": 1, "unit_price": 1, "amount": 1}],
                        "issue_date": "2026-01-01", "issuer": "a", "recipient": "b", "subtotal": 1, "tax": 0, "total": 1})


def leaks(haystack, key=KEY):
    """キーが（そのまま・URL エンコード・base64・16進で）含まれていれば True。"""
    variants = [key, urllib.parse.quote(key), base64.b64encode(key.encode()).decode(), key.encode().hex()]
    return any(v in haystack for v in variants)


class Fake(http.server.BaseHTTPRequestHandler):
    mode = "ok"
    seen = []  # 受け取ったリクエストのヘッダ（リダイレクト先が何も受け取らないことの確認用）

    def log_message(self, *a):
        pass

    def do_POST(self):
        Fake.seen.append((self.server.server_port, {k.lower(): v for k, v in self.headers.items()}))
        self.rfile.read(int(self.headers.get("content-length", 0)))
        echo = self.headers.get("x-api-key", "")
        m = Fake.mode
        if m == "ok":
            self._send(200, {"content": [{"type": "text", "text": GOOD_TEXT}]})
        elif m == "401_echo":  # 悪意ある/雑なサーバ：本文にキーをそのまま返す
            self._send(401, {"error": {"message": f"invalid x-api-key: {echo}"}})
        elif m == "500_headers":
            self._send(500, {"headers": dict(self.headers)})
        elif m == "garbage":
            self._send(200, {"content": [{"type": "text", "text": "not json " + echo}]})
        elif m == "redirect":
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{Fake.other}/steal")
            self.end_headers()

    def do_GET(self):  # リダイレクトを追われた場合、ここに届く（ヘッダを記録する）
        Fake.seen.append((self.server.server_port, {k.lower(): v for k, v in self.headers.items()}))
        self._send(200, {})

    def _send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def start():
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


class TestDetectorWorks(unittest.TestCase):
    """検出器の確認。わざと漏らしたキーを、全ての出口で見つけられるか。"""

    def test_detects_raw_encoded_and_in_files(self):
        self.assertTrue(leaks(f"error: {KEY}"))
        self.assertTrue(leaks(urllib.parse.quote(KEY)))
        self.assertTrue(leaks(base64.b64encode(KEY.encode()).decode()))
        self.assertTrue(leaks("x" + KEY.encode().hex()))
        self.assertFalse(leaks("nothing here"))

    def test_detects_deliberate_leaks_on_each_channel(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            print(KEY)
            print(KEY, file=__import__("sys").stderr)
        self.assertTrue(leaks(out.getvalue()) and leaks(err.getvalue()))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            p.write_text(json.dumps({"k": KEY}))
            self.assertTrue(leaks(p.read_text()))
        try:
            raise RuntimeError(f"failed with {KEY}")
        except RuntimeError as e:
            self.assertTrue(leaks("".join(traceback.format_exception(e))))
        rec = []

        class H(logging.Handler):
            def emit(self, r):
                rec.append(r.getMessage())

        lg = logging.getLogger("canary")
        lg.addHandler(H())
        lg.warning("key=%s", KEY)
        self.assertTrue(leaks(" ".join(rec)))

    def test_detects_a_leaky_implementation(self):
        """キーを素の文字列で持つ実装だと、f-string で簡単に漏れる。Secret ならそうならない。"""
        self.assertTrue(leaks(f"{KEY}"))
        self.assertFalse(leaks(f"{Secret(KEY)} {Secret(KEY)!r} %s" % Secret(KEY)))


class TestSecretBox(unittest.TestCase):
    def test_never_stringifies(self):
        s = Secret(KEY)
        for text in (str(s), repr(s), f"{s}", "%s" % s, "{}".format(s), f"{s:>20}"):
            self.assertFalse(leaks(text), text)
        with self.assertRaises(TypeError):
            json.dumps({"k": s})

    def test_redact(self):
        self.assertNotIn(KEY, redact(f"boom {KEY} boom", Secret(KEY)))
        self.assertNotIn("sk-ant-abcdefghijk", redact("x sk-ant-abcdefghijk y"))

    def test_missing_key_message(self):
        with self.assertRaises(ConfigError) as c:
            load_key({})
        self.assertIn("ANTHROPIC_API_KEY", str(c.exception))
        self.assertEqual(load_key({"ANTHROPIC_API_KEY": KEY}).reveal(), KEY)


class TestEndToEndAgainstFakeServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv, cls.other = start(), start()
        Fake.other = cls.other.server_port
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}/v1/messages"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.other.shutdown()

    def run_cli(self, mode, key=KEY):
        """CLI を丸ごと動かし、出口（stdout / stderr / ログ / 出力ファイル）を全部集めて返す。"""
        Fake.mode, Fake.seen = mode, []
        out, err, logs = io.StringIO(), io.StringIO(), []

        class H(logging.Handler):
            def emit(self, r):
                logs.append(r.getMessage())

        h = H()
        logging.getLogger().addHandler(h)
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            with tempfile.TemporaryDirectory() as d, mock.patch.object(ex, "API_URL", self.url), \
                    mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": key}), \
                    contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["extract", str(SAMPLE), "--model", "test-model", "--out", d])
                files = "".join(p.read_text(encoding="utf-8") for p in Path(d).rglob("*") if p.is_file())
        finally:
            logging.getLogger().removeHandler(h)
        return code, out.getvalue(), err.getvalue(), " ".join(logs), files

    def test_success_path_has_no_leak_and_writes_result(self):
        code, out, err, logs, files = self.run_cli("ok")
        self.assertEqual(code, 0)
        self.assertIn("issue_date", files)  # 空振りでないこと：出力ファイルは実際に書かれている
        for name, text in (("stdout", out), ("stderr", err), ("log", logs), ("files", files)):
            self.assertFalse(leaks(text), name)
        # サーバはキーを受け取っている（=送る経路は生きている）
        self.assertTrue(any(h.get("x-api-key") == KEY for _, h in Fake.seen))

    def test_hostile_error_paths_have_no_leak(self):
        for mode in ("401_echo", "500_headers", "garbage"):
            code, out, err, logs, files = self.run_cli(mode)
            self.assertEqual(code, 1, mode)
            self.assertIn("NG", out, mode)  # 失敗が実際に処理された（空振りでない）
            for name, text in (("stdout", out), ("stderr", err), ("log", logs), ("files", files)):
                self.assertFalse(leaks(text), f"{mode}/{name}: {text[:200]}")

    def test_exception_text_and_traceback_have_no_leak(self):
        for mode in ("401_echo", "500_headers", "garbage"):
            Fake.mode = mode
            try:
                ex.call_api({"x": 1}, Secret(KEY), url=self.url)
                if mode == "garbage":
                    ex.parse_reply(ex.call_api({"x": 1}, Secret(KEY), url=self.url))
                self.fail("例外が出ていない（テストが空振り）")
            except ex.ExtractError as e:
                tb = "".join(traceback.format_exception(e))
                self.assertFalse(leaks(str(e)) or leaks(tb), mode)

    def test_redirect_is_not_followed(self):
        code, out, err, logs, files = self.run_cli("redirect")
        self.assertEqual(code, 1)
        self.assertTrue(any(p == self.srv.server_port for p, _ in Fake.seen))
        self.assertFalse(any(p == self.other.server_port for p, _ in Fake.seen), "リダイレクト先にリクエストが届いた")
        self.assertFalse(any(h.get("x-api-key") == KEY for p, h in Fake.seen if p == self.other.server_port))

    def test_only_allowed_destinations(self):
        """許可外の宛先は、通信を始める前に「送信先が許可されていません」で拒否される（通信の関数が呼ばれない）。"""
        for bad in ("https://example.com/v1/messages", "http://localhost:1/", "http://evil.test/"):
            with mock.patch.object(ex.urllib.request, "build_opener") as bo:
                with self.assertRaises(ex.ExtractError) as c:
                    ex.call_api({}, Secret(KEY), url=bad)
                self.assertIn("送信先が許可されていません", str(c.exception))
                bo.assert_not_called()
        with self.assertRaises(ex.ExtractError):
            ex.call_api({}, KEY, url=self.url)  # 素の文字列のキーは受け付けない

    def test_key_not_matching_key_pattern_is_still_redacted(self):
        """sk-… の形ではないキーでも、キーそのものの一致で伏せる（パターン頼みにしない）。"""
        odd = "zzz_secret_123456"
        self.assertNotIn(odd, redact(f"bad key {odd} here", Secret(odd)))
        self.assertIn(odd, redact(f"bad key {odd} here"))  # キーを渡さなければ残る＝置換が効いていることの対照
        code, out, err, logs, files = self.run_cli("401_echo", key=odd)
        self.assertEqual(code, 1)
        for name, text in (("stdout", out), ("stderr", err), ("log", logs), ("files", files)):
            self.assertFalse(leaks(text, odd), name)

    def test_connection_error_has_no_leak(self):
        with self.assertRaises(ex.ExtractError) as c:
            ex.call_api({}, Secret(KEY), url="http://127.0.0.1:1/x")
        self.assertFalse(leaks(str(c.exception)))


if __name__ == "__main__":
    unittest.main()
