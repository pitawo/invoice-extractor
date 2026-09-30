(function () {
  "use strict";
  var data = window.INVOICE_DATA;
  var Lib = window.InvoiceLib;
  var docs = data.documents.map(function (d) {
    return { file: d.file, path: d.path, confirmed: false, extraction: JSON.parse(JSON.stringify(d.extraction)) };
  });
  var current = 0;
  var TYPES = [["invoice", "請求書"], ["purchase_order", "注文書"], ["delivery_note", "納品書"], ["other", "その他"]];

  function h(tag, attrs, kids) {
    var el = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") el.textContent = attrs[k];
      else el.setAttribute(k, attrs[k]);
    });
    (kids || []).forEach(function (c) { el.appendChild(c); });
    return el;
  }
  function $(id) { return document.getElementById(id); }
  function toNum(s) { return s === "" ? null : Number(s); }
  function toText(s) { return s === "" ? null : s; }
  function show(v) { return v === null || v === undefined ? "" : String(v); }

  if (data.meta && data.meta.source === "claude-code-preextracted") $("demo-note").hidden = false;

  // ---- 一覧 ----
  function renderList() {
    var list = $("list");
    list.textContent = "";
    docs.forEach(function (d, i) {
      var e = d.extraction, n = Lib.check(e).length;
      var b = h("button", { type: "button", "data-i": String(i) }, [
        h("div", { class: "name", text: d.file }),
        h("div", { class: "meta", text: (e.issuer || "（発行元不明）") + " / " + (e.issue_date || "日付不明") }),
        h("span", { class: "badge " + (d.confirmed ? "ok" : n ? "warn" : ""), text: d.confirmed ? "確認済み" : n ? "要確認 " + n + "件" : "数字は一致" })
      ]);
      if (i === current) b.setAttribute("aria-current", "true");
      list.appendChild(b);
    });
  }
  $("list").addEventListener("click", function (ev) {
    var b = ev.target.closest("button");
    if (!b) return;
    current = Number(b.getAttribute("data-i"));
    renderList();
    renderDetail();
  });

  // ---- 詳細 ----
  function field(label, id, value, type, onchange) {
    var input = h("input", { type: type, id: id, value: show(value) });
    if (type === "number") input.setAttribute("step", "any");
    input.addEventListener("input", function () { onchange(input.value); refresh(); });
    return h("div", {}, [h("label", { for: id, text: label }), input]);
  }

  function renderDetail() {
    var d = docs[current], e = d.extraction, root = $("detail");
    root.textContent = "";
    var preview = h("div", { class: "preview" });
    if (/\.(png|jpe?g|gif|webp)$/i.test(d.path)) preview.appendChild(h("img", { src: d.path, alt: d.file + " の書類画像" }));
    else preview.appendChild(h("a", { href: d.path, target: "_blank", rel: "noopener", text: d.file + " を開く（PDF）" }));

    var sel = h("select", { id: "f-type" }, TYPES.map(function (t) {
      var o = h("option", { value: t[0], text: t[1] });
      if (e.doc_type === t[0]) o.selected = true;
      return o;
    }));
    sel.addEventListener("change", function () { e.doc_type = sel.value; refresh(); });

    var fields = h("div", { class: "fields" }, [
      h("div", {}, [h("label", { for: "f-type", text: "種別" }), sel]),
      field("書類番号", "f-no", e.doc_number, "text", function (v) { e.doc_number = toText(v); }),
      field("発行日（YYYY-MM-DD）", "f-issue", e.issue_date, "text", function (v) { e.issue_date = toText(v); }),
      field("期日（支払期限・納期）", "f-due", e.due_date, "text", function (v) { e.due_date = toText(v); }),
      field("発行元", "f-issuer", e.issuer, "text", function (v) { e.issuer = toText(v); }),
      field("宛先", "f-recipient", e.recipient, "text", function (v) { e.recipient = toText(v); }),
      field("小計", "f-sub", e.subtotal, "number", function (v) { e.subtotal = toNum(v); }),
      field("消費税", "f-tax", e.tax, "number", function (v) { e.tax = toNum(v); }),
      field("合計", "f-total", e.total, "number", function (v) { e.total = toNum(v); })
    ]);

    var tbody = h("tbody");
    (e.items || []).forEach(function (it, i) {
      function cell(key, type) {
        var inp = h("input", { type: type, "aria-label": "行" + (i + 1) + " " + key, value: show(it[key]) });
        if (type === "number") { inp.setAttribute("step", "any"); inp.className = "num"; }
        inp.addEventListener("input", function () { it[key] = type === "number" ? toNum(inp.value) : toText(inp.value); refresh(); });
        return h("td", {}, [inp]);
      }
      var del = h("button", { type: "button", class: "sub", "aria-label": "行" + (i + 1) + "を削除", text: "削除" });
      del.addEventListener("click", function () { e.items.splice(i, 1); renderDetail(); refresh(); });
      tbody.appendChild(h("tr", {}, [cell("description", "text"), cell("quantity", "number"), cell("unit_price", "number"),
        cell("amount", "number"), cell("tax_rate", "number"), h("td", {}, [del])]));
    });
    var add = h("button", { type: "button", class: "sub", text: "行を追加" });
    add.addEventListener("click", function () {
      e.items.push({ description: null, quantity: null, unit_price: null, amount: null, tax_rate: null });
      renderDetail(); refresh();
    });
    var table = h("table", {}, [
      h("thead", {}, [h("tr", {}, ["品名", "数量", "単価", "金額", "税率", ""].map(function (t) { return h("th", { text: t }); }))]),
      tbody
    ]);

    var conf = h("input", { type: "checkbox", id: "f-confirmed" });
    conf.checked = d.confirmed;
    conf.addEventListener("change", function () { d.confirmed = conf.checked; refresh(); });

    root.appendChild(h("div", { class: "detail-grid" }, [
      preview,
      h("div", {}, [fields, h("div", { class: "table-wrap" }, [table]), add,
        h("ul", { class: "flags", id: "flags", "aria-live": "polite" }),
        h("div", { class: "row" }, [conf, h("label", { for: "f-confirmed", text: "この書類は目で見て確認した" })])])
    ]));
    renderFlags();
  }

  function renderFlags() {
    var ul = $("flags");
    if (!ul) return;
    ul.textContent = "";
    var f = Lib.check(docs[current].extraction);
    if (!f.length) ul.appendChild(h("li", { class: "clear", text: "数字は互いに一致しています（明細の合計＝小計、小計＋消費税＝合計）" }));
    f.forEach(function (t) { ul.appendChild(h("li", { text: t })); });
  }

  function refresh() { renderFlags(); renderList(); }

  // ---- 書き出し ----
  function status(t) { $("export-status").textContent = t; }
  $("dl-csv").addEventListener("click", function () {
    var blob = new Blob([Lib.toCsv(docs, $("self-name").value)], { type: "text/csv;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = h("a", { href: url, download: "invoices.csv" });
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    status("invoices.csv を書き出しました（" + docs.length + " 件）");
  });
  $("copy-tsv").addEventListener("click", function () {
    var text = Lib.toTsv(docs, $("self-name").value);
    function fallback() {
      var ta = h("textarea", {});
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      var ok = document.execCommand("copy");
      document.body.removeChild(ta);
      status(ok ? "コピーしました。表計算ソフトに貼り付けてください" : "コピーできませんでした");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { status("コピーしました。表計算ソフトに貼り付けてください"); }, fallback);
    } else fallback();
  });

  // ---- 安全性の節：この画面に効いている CSP を、自分のソースから読み出して見せる ----
  var meta = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
  $("csp-text").textContent = meta ? meta.getAttribute("content").split("; ").join(";\n") : "（CSP が設定されていません）";

  renderList();
  renderDetail();
})();
