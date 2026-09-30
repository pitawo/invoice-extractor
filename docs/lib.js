// 検証・CSV 化の純粋関数。invoice_extractor/validate.py・export.py と同じ規則（tests/test_js_parity.py で一致を確認）。
(function (root) {
  "use strict";
  var DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
  var HEADER = ["ファイル", "種別", "書類番号", "発行日", "期日", "取引先", "発行元", "宛先",
    "品名", "数量", "単価", "金額", "税率", "小計", "消費税", "合計", "要確認"];
  var TYPE_JA = { invoice: "請求書", purchase_order: "注文書", delivery_note: "納品書", other: "その他" };

  function isNull(v) { return v === null || v === undefined; }

  function check(doc) {
    var f = [];
    if (!doc.issue_date) f.push("発行日が読めていない");
    else if (!DATE_RE.test(String(doc.issue_date))) f.push("発行日の形式が YYYY-MM-DD ではない");
    if (doc.due_date && !DATE_RE.test(String(doc.due_date))) f.push("期日の形式が YYYY-MM-DD ではない");
    if (!doc.issuer) f.push("発行元が読めていない");
    if (!doc.recipient) f.push("宛先が読めていない");
    var items = doc.items || [];
    if (!items.length) f.push("明細が1行も無い");
    items.forEach(function (it, i) {
      var n = i + 1;
      if (isNull(it.quantity) || isNull(it.unit_price) || isNull(it.amount)) f.push("行" + n + "：数量・単価・金額のどれかが空");
      else if (Math.floor(it.quantity * it.unit_price + 0.5) !== it.amount) f.push("行" + n + "：数量×単価が金額と合わない");
    });
    var amounts = items.map(function (it) { return it.amount; });
    if (items.length && !amounts.some(isNull) && !isNull(doc.subtotal) &&
      amounts.reduce(function (a, b) { return a + b; }, 0) !== doc.subtotal) f.push("明細の合計が小計と合わない");
    if (!isNull(doc.subtotal) && !isNull(doc.tax) && !isNull(doc.total) && doc.subtotal + doc.tax !== doc.total)
      f.push("小計＋消費税が合計と合わない");
    if (isNull(doc.total)) f.push("合計が読めていない");
    return f;
  }

  // 表計算ソフトで式として実行される先頭文字を無効にする。文字列の列にだけ使う。
  function safeText(v) {
    var s = isNull(v) ? "" : String(v);
    return /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
  }
  function num(v) { return isNull(v) ? "" : String(v); }

  function counterparty(doc, self) {
    if (self && doc.issuer === self) return doc.recipient || "";
    if (self && doc.recipient === self) return doc.issuer || "";
    return "";
  }

  function rows(documents, self) {
    var out = [];
    documents.forEach(function (d) {
      var e = d.extraction;
      var flag = check(e).length && !d.confirmed ? "要確認" : "";
      var items = (e.items && e.items.length) ? e.items : [{}];
      items.forEach(function (it, n) {
        var first = n === 0;
        out.push([
          safeText(d.file), TYPE_JA[e.doc_type] || "", safeText(e.doc_number),
          e.issue_date || "", e.due_date || "",
          safeText(counterparty(e, self)), safeText(e.issuer), safeText(e.recipient),
          safeText(it.description), num(it.quantity), num(it.unit_price), num(it.amount), num(it.tax_rate),
          first ? num(e.subtotal) : "", first ? num(e.tax) : "", first ? num(e.total) : "", first ? flag : ""
        ]);
      });
    });
    return out;
  }

  function csvCell(s) { return /[",\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; }
  function toDelimited(documents, self, sep, eol) {
    var all = [HEADER].concat(rows(documents, self));
    return all.map(function (r) { return r.map(sep === "," ? csvCell : function (s) { return s.replace(/[\t\r\n]/g, " "); }).join(sep); }).join(eol) + eol;
  }
  // UTF-8 BOM 付き・CRLF（Excel で文字化けしないため）。Python 版 to_csv と同じ出力。
  function toCsv(documents, self) { return "﻿" + toDelimited(documents, self, ",", "\r\n"); }
  // スプレッドシートに貼り付ける用（タブ区切り）
  function toTsv(documents, self) { return toDelimited(documents, self, "\t", "\n"); }

  var api = { check: check, rows: rows, toCsv: toCsv, toTsv: toTsv, HEADER: HEADER };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.InvoiceLib = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
