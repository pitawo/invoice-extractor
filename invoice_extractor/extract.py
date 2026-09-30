"""書類1枚を LLM API に送り、抽出結果の dict を返す。

送信先は API_URL の1つだけ（テストのときだけ 127.0.0.1 を許可）。リダイレクトは追わない
（追うと x-api-key ヘッダが別のホストに付いて行くため）。
"""
import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .safety import Secret, redact

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "extract_prompt.md"
MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
         ".webp": "image/webp", ".pdf": "application/pdf"}


class ExtractError(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _check_url(url):
    if url == API_URL:
        return
    u = urllib.parse.urlparse(url)
    if u.scheme == "http" and u.hostname == "127.0.0.1":  # テスト用の偽サーバだけ
        return
    raise ExtractError("送信先が許可されていません")


def build_payload(path, model, prompt):
    path = Path(path)
    media = MEDIA.get(path.suffix.lower())
    if media is None:
        raise ExtractError(f"対応していない形式です: {path.suffix}")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    kind = "document" if media == "application/pdf" else "image"
    return {
        "model": model,
        "max_tokens": 2048,
        "system": prompt,
        "messages": [{"role": "user", "content": [
            {"type": kind, "source": {"type": "base64", "media_type": media, "data": data}},
            {"type": "text", "text": "この書類を読み取り、指定の JSON だけを返してください。"},
        ]}],
    }


def call_api(payload, key, url=API_URL, timeout=90):
    _check_url(url)
    if not isinstance(key, Secret):
        raise ExtractError("key は Secret で渡してください")
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "x-api-key": key.reveal(), "anthropic-version": API_VERSION, "content-type": "application/json"})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read(500).decode("utf-8", "replace")
        except Exception:
            pass
        raise ExtractError(redact(f"HTTP {e.code} {body}", key)[:300]) from None
    except Exception as e:  # URLError・タイムアウト・JSON 不正など。元の例外は繋がない（本文にキーが混ざり得る）
        raise ExtractError(redact(f"{type(e).__name__}: {e}", key)[:300]) from None


def parse_reply(reply):
    try:
        text = "".join(b.get("text", "") for b in reply["content"] if b.get("type") == "text")
    except Exception:
        raise ExtractError("応答の形が想定と違います") from None
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ExtractError("応答に JSON が見つかりません")
    try:
        obj = json.loads(m.group(0))
    except ValueError:
        raise ExtractError("応答の JSON を読めませんでした") from None
    if not isinstance(obj, dict) or not isinstance(obj.get("items"), list):
        raise ExtractError("応答に items がありません")
    return obj


def extract_file(path, key, model, url=None):
    url = url or API_URL
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    return parse_reply(call_api(build_payload(path, model, prompt), key, url=url))
