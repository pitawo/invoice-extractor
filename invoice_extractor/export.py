"""確認済みの結果を CSV にする。1明細＝1行。小計・消費税・合計は書類の最初の行にだけ入れる
（全行に入れると、列を合計したときに二重に数えるため）。docs/lib.js と同じ出力（parity テスト）。"""
import csv
import io

from .validate import check

HEADER = ["ファイル", "種別", "書類番号", "発行日", "期日", "取引先", "発行元", "宛先",
          "品名", "数量", "単価", "金額", "税率", "小計", "消費税", "合計", "要確認"]
TYPE_JA = {"invoice": "請求書", "purchase_order": "注文書", "delivery_note": "納品書", "other": "その他"}
_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe_text(v):
    """表計算ソフトで式として実行される先頭文字（= + - @）を無効にする。文字列の列にだけ使う。"""
    s = "" if v is None else str(v)
    return "'" + s if s.startswith(_DANGEROUS) else s


def num(v):
    return "" if v is None else str(v)


def counterparty(doc, self_name):
    if self_name and doc.get("issuer") == self_name:
        return doc.get("recipient") or ""
    if self_name and doc.get("recipient") == self_name:
        return doc.get("issuer") or ""
    return ""


def rows(documents, self_name=""):
    out = []
    for d in documents:
        e = d["extraction"]
        flag = "要確認" if check(e) and not d.get("confirmed") else ""
        items = e.get("items") or [{}]
        for n, it in enumerate(items):
            first = n == 0
            out.append([
                safe_text(d["file"]), TYPE_JA.get(e.get("doc_type"), ""), safe_text(e.get("doc_number")),
                e.get("issue_date") or "", e.get("due_date") or "",
                safe_text(counterparty(e, self_name)), safe_text(e.get("issuer")), safe_text(e.get("recipient")),
                safe_text(it.get("description")), num(it.get("quantity")), num(it.get("unit_price")),
                num(it.get("amount")), num(it.get("tax_rate")),
                num(e.get("subtotal")) if first else "", num(e.get("tax")) if first else "",
                num(e.get("total")) if first else "", flag if first else "",
            ])
    return out


def to_csv(documents, self_name=""):
    """UTF-8 BOM 付き（Excel で文字化けしないため）。改行は CRLF。"""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADER)
    w.writerows(rows(documents, self_name))
    return "﻿" + buf.getvalue()
