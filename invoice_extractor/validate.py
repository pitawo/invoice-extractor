"""抽出結果の機械的な突き合わせ。LLM の自己申告の確信度は使わず、数字が合うかだけで「要確認」を出す。
docs/lib.js の validate と同じ規則（tests/test_js_parity.py で一致を確認）。"""
import math
import re

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check(doc):
    """戻り値: 要確認の理由（日本語）のリスト。空なら機械的には矛盾なし。"""
    flags = []
    if not doc.get("issue_date"):
        flags.append("発行日が読めていない")
    elif not DATE_RE.match(str(doc["issue_date"])):
        flags.append("発行日の形式が YYYY-MM-DD ではない")
    if doc.get("due_date") and not DATE_RE.match(str(doc["due_date"])):
        flags.append("期日の形式が YYYY-MM-DD ではない")
    if not doc.get("issuer"):
        flags.append("発行元が読めていない")
    if not doc.get("recipient"):
        flags.append("宛先が読めていない")
    items = doc.get("items") or []
    if not items:
        flags.append("明細が1行も無い")
    for n, it in enumerate(items, 1):
        q, u, a = it.get("quantity"), it.get("unit_price"), it.get("amount")
        if None in (q, u, a):
            flags.append(f"行{n}：数量・単価・金額のどれかが空")
        elif math.floor(q * u + 0.5) != a:
            flags.append(f"行{n}：数量×単価が金額と合わない")
    amounts = [it.get("amount") for it in items]
    if items and None not in amounts and doc.get("subtotal") is not None and sum(amounts) != doc["subtotal"]:
        flags.append("明細の合計が小計と合わない")
    if None not in (doc.get("subtotal"), doc.get("tax"), doc.get("total")) \
            and doc["subtotal"] + doc["tax"] != doc["total"]:
        flags.append("小計＋消費税が合計と合わない")
    if doc.get("total") is None:
        flags.append("合計が読めていない")
    return flags
