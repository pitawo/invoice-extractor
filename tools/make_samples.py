"""架空の請求書・注文書を画像/PDFとして生成する。

出力: docs/samples/<id>.png（と、一部は .pdf）、tests/truth.json（照合用の正解）。
実在の社名・人名・住所・登録番号は使わない。全ての書類に「架空のサンプル」の表記を入れる。
"""
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "samples"
TRUTH = ROOT / "tests" / "truth.json"
W, H = 1240, 1754
FONT = "C:/Windows/Fonts/meiryo.ttc"
FONT_B = "C:/Windows/Fonts/meiryob.ttc"
SELF = "デモ販売株式会社"
DUMMY_ADDR = "〒000-0000 架空県サンプル市見本町1-2-3"
DUMMY_REG = "T0000000000000"


def f(size, bold=False):
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def yen(n, mark=True):
    s = f"{abs(n):,}"
    s = ("-" if n < 0 else "") + s
    return ("¥" + s) if mark else s


def calc(items):
    sub = sum(i["amount"] for i in items)
    by = {}
    for i in items:
        r = i["tax_rate"]
        by[r] = by.get(r, 0) + i["amount"]
    tax = sum(math.floor(v * r) for r, v in by.items())
    return sub, tax, sub + tax, by


def item(desc, q, u, r=0.1):
    return {"description": desc, "quantity": q, "unit_price": u, "amount": q * u, "tax_rate": r}


DOCS = [
    dict(id="inv_001", layout="L1", doc_type="invoice", doc_number="INV-2026-0142",
         date_text="2026年8月31日", issue_date="2026-08-31", due_text="2026年9月30日", due_date="2026-09-30",
         issuer="サンプル商事株式会社", recipient=SELF,
         items=[item("コピー用紙 A4 500枚入", 10, 480), item("ボールペン 黒 10本入", 5, 350),
                item("ファイルボックス", 12, 620)]),
    dict(id="inv_002", layout="L1", doc_type="invoice", doc_number="No.0087",
         date_text="令和8年9月5日", issue_date="2026-09-05", due_text="令和8年10月5日", due_date="2026-10-05",
         issuer="テスト工房有限会社", recipient=SELF,
         items=[item("チラシデザイン A4", 1, 18000), item("チラシ印刷 500部", 1, 9500),
                item("名刺デザイン", 2, 4000), item("名刺印刷 100枚", 2, 1800), item("データ修正対応", 3, 1500)]),
    dict(id="po_003", layout="L2", doc_type="purchase_order", doc_number="PO-260902-01",
         date_text="2026年9月2日", issue_date="2026-09-02", due_text="2026年9月16日", due_date="2026-09-16",
         issuer=SELF, recipient="ピヨピヨ電材株式会社",
         items=[item("LANケーブル 5m", 20, 380), item("電源タップ 6個口", 8, 1250),
                item("USB充電器 65W", 6, 2980), item("結束バンド 100本入", 10, 220)]),
    dict(id="po_004", layout="L2", doc_type="purchase_order", doc_number="PO-260909-02",
         date_text="2026年9月9日", issue_date="2026-09-09", due_text="2026年9月30日", due_date="2026-09-30",
         issuer=SELF, recipient="ほげほげ食品株式会社",
         items=[item("ミネラルウォーター 500ml", 1200, 35, 0.08)]),
    dict(id="dn_005", layout="L3", doc_type="delivery_note", doc_number="D-3310",
         date_text="2026/09/08", issue_date="2026-09-08", due_text=None, due_date=None,
         issuer="ふがふが印刷株式会社", recipient=SELF,
         items=[item("封筒 長3 100枚", 4, 700), item("お茶 500ml（軽減税率）", 24, 90, 0.08),
                item("付箋 75mm", 10, 210), item("コーヒー缶 190g（軽減税率）", 12, 100, 0.08)]),
    dict(id="inv_006", layout="L4", doc_type="invoice", doc_number="K-2609-15",
         date_text="令和8年9月10日", issue_date="2026-09-10", due_text="令和8年9月30日", due_date="2026-09-30",
         issuer="架空ビルメンテナンス株式会社", recipient=SELF,
         items=[item("月額清掃（9月分）", 1, 45000), item("窓ガラス清掃", 1, 12000),
                item("消耗品（洗剤・ごみ袋）", 1, 6800), item("継続割引", 1, -3000)]),
    dict(id="inv_007", layout="L1", doc_type="invoice", doc_number="HG-20260915",
         date_text="2026年9月15日", issue_date="2026-09-15", due_text="2026年10月15日", due_date="2026-10-15",
         issuer="ホゲ運輸株式会社", recipient=SELF, scan=True,
         items=[item("配送料 東エリア", 14, 850), item("配送料 西エリア", 9, 1100),
                item("再配達手数料", 3, 400)]),
    dict(id="po_008", layout="L3", doc_type="purchase_order", doc_number="P-0912",
         date_text="R8.9.12", issue_date="2026-09-12", due_text=None, due_date=None,
         issuer=SELF, recipient="ダミー文具店", pdf=True,
         items=[item("ノートA5 罫線", 30, 150), item("クリアファイル 10枚入", 15, 280),
                item("ホワイトボードマーカー 黒", 12, 130), item("マグネット 大", 20, 95),
                item("スティックのり", 25, 110), item("メモ帳 100枚", 40, 60)]),
]


class Draw(ImageDraw.ImageDraw):
    """text の既定色を黒にする（Pillow 既定は白）。"""

    def text(self, xy, text, fill="black", **kw):
        super().text(xy, text, fill=fill, **kw)


def base():
    im = Image.new("RGB", (W, H), "white")
    return im, Draw(im)


def watermark(d):
    d.text((W // 2, H - 60), "※ この書類は架空のサンプルです（実在の会社・取引とは無関係）", font=f(22),
           fill="#777777", anchor="mm")


def right(d, x, y, s, size=26, bold=False, fill="black"):
    d.text((x, y), s, font=f(size, bold), fill=fill, anchor="ra")


def L1(doc):
    im, d = base()
    d.text((W // 2, 130), "請　求　書", font=f(64, True), anchor="mm")
    right(d, W - 90, 210, f"発行日　{doc['date_text']}")
    right(d, W - 90, 250, f"請求番号　{doc['doc_number']}")
    d.text((90, 310), f"{doc['recipient']}　御中", font=f(36, True))
    d.line((90, 362, 640, 362), fill="black", width=2)
    d.text((90, 400), "下記の通りご請求申し上げます。", font=f(24))
    right(d, W - 90, 330, doc["issuer"], 30, True)
    right(d, W - 90, 375, DUMMY_ADDR, 22)
    right(d, W - 90, 410, f"登録番号 {DUMMY_REG}", 22)
    sub, tax, total, _ = calc(doc["items"])
    d.rectangle((90, 500, 640, 590), outline="black", width=2)
    d.text((110, 520), "ご請求金額", font=f(26))
    right(d, 620, 525, yen(total) + "-", 40, True)
    if doc["due_text"]:
        d.text((90, 615), f"お支払期限　{doc['due_text']}", font=f(26))
    y = 690
    cols = [90, 690, 800, 960, W - 90]
    d.rectangle((90, y, W - 90, y + 50), fill="#e8e8e8", outline="black")
    for x, t in zip([100, 700, 810, 970], ["品名", "数量", "単価", "金額"]):
        d.text((x, y + 8), t, font=f(26, True))
    y += 50
    for it in doc["items"]:
        d.rectangle((90, y, W - 90, y + 56), outline="black")
        d.text((100, y + 10), it["description"], font=f(26))
        right(d, 780, y + 10, f"{it['quantity']:,}")
        right(d, 940, y + 10, yen(it["unit_price"], False))
        right(d, W - 100, y + 10, yen(it["amount"], False))
        y += 56
    y += 30
    for lab, v in [("小計", sub), ("消費税（10%）", tax), ("合計", total)]:
        d.rectangle((700, y, W - 90, y + 50), outline="black")
        d.text((715, y + 8), lab, font=f(26, lab == "合計"))
        right(d, W - 100, y + 8, yen(v), 26, lab == "合計")
        y += 50
    d.text((90, y + 60), "お振込先：架空銀行 見本支店 普通 0000000　（サンプル）", font=f(22))
    watermark(d)
    return im


def L2(doc):
    im, d = base()
    d.text((90, 110), "注 文 書", font=f(56, True))
    d.text((90, 200), f"{doc['recipient']}　御中", font=f(34, True))
    d.text((90, 260), "下記の通り注文いたします。", font=f(24))
    grid = [("発注番号", doc["doc_number"]), ("発注日", doc["date_text"]), ("納期", doc["due_text"] or "")]
    y = 90
    for k, v in grid:
        d.rectangle((760, y, 950, y + 46), fill="#dde6f0", outline="#444")
        d.rectangle((950, y, W - 90, y + 46), outline="#444")
        d.text((775, y + 8), k, font=f(24))
        d.text((965, y + 8), v, font=f(24))
        y += 46
    d.text((760, 260), doc["issuer"], font=f(28, True))
    d.text((760, 300), DUMMY_ADDR, font=f(20))
    y = 420
    d.rectangle((90, y, W - 90, y + 50), fill="#dde6f0", outline="#444")
    for x, t in [(100, "No."), (170, "品名"), (700, "数量"), (820, "単価（税抜）"), (1010, "金額（税抜）")]:
        d.text((x, y + 8), t, font=f(24, True))
    y += 50
    for n, it in enumerate(doc["items"], 1):
        d.rectangle((90, y, W - 90, y + 54), outline="#444")
        d.text((100, y + 10), str(n), font=f(24))
        d.text((170, y + 10), it["description"], font=f(26))
        right(d, 790, y + 10, f"{it['quantity']:,}", 26)
        right(d, 1000, y + 10, yen(it["unit_price"], False), 26)
        right(d, W - 100, y + 10, yen(it["amount"], False), 26)
        y += 54
    sub, tax, total, by = calc(doc["items"])
    rate = int(round(list(by)[0] * 100))
    y += 20
    for lab, v in [("小計", sub), (f"消費税（{rate}%）", tax), ("注文金額（税込）", total)]:
        d.rectangle((700, y, W - 90, y + 50), outline="#444")
        d.text((715, y + 8), lab, font=f(26, True))
        right(d, W - 100, y + 8, yen(v), 26, True)
        y += 50
    d.text((90, y + 50), "納品先：デモ販売株式会社 本社（架空）　支払条件：月末締め翌月末払い", font=f(22))
    watermark(d)
    return im


def L3(doc):
    im, d = base()
    x0, x1 = 300, 940
    title = {"delivery_note": "納 品 書", "purchase_order": "注 文 書"}[doc["doc_type"]]
    d.text((W // 2, 120), title, font=f(48, True), anchor="mm")
    d.text((x0, 190), f"発行元：{doc['issuer']}", font=f(24))
    d.text((x0, 230), f"宛先：{doc['recipient']} 御中", font=f(24))
    d.text((x0, 270), f"日付：{doc['date_text']}", font=f(24))
    d.text((x0, 310), f"伝票No：{doc['doc_number']}", font=f(24))

    def dash(y):
        for x in range(x0, x1, 14):
            d.line((x, y, x + 7, y), fill="black", width=2)

    y = 370
    dash(y)
    y += 12
    d.text((x0, y), "品名", font=f(22, True))
    right(d, x0 + 400, y, "数量", 22, True)
    right(d, x1, y, "金額", 22, True)
    y += 40
    for it in doc["items"]:
        mark = "※" if it["tax_rate"] == 0.08 else ""
        d.text((x0, y), mark + it["description"], font=f(24))
        y += 34
        right(d, x0 + 330, y, f"{it['quantity']:,} x {yen(it['unit_price'], False)}", 22)
        right(d, x1, y, yen(it["amount"], False), 24)
        y += 44
    dash(y)
    y += 14
    sub, tax, total, by = calc(doc["items"])
    right(d, x1, y, f"小計　{yen(sub)}", 24)
    y += 40
    for r, v in sorted(by.items()):
        right(d, x1, y, f"{int(round(r * 100))}%対象　{yen(v)}　税 {yen(math.floor(v * r))}", 22)
        y += 34
    y += 8
    right(d, x1, y, f"合計　{yen(total)}", 34, True)
    y += 70
    if any(i["tax_rate"] == 0.08 for i in doc["items"]):
        d.text((x0, y), "※は軽減税率（8%）対象", font=f(20))
    watermark(d)
    return im


def L4(doc):
    im, d = base()
    d.text((90, 100), "ご請求書", font=f(44, True))
    d.text((90, 180), f"{doc['date_text']}　　No. {doc['doc_number']}", font=f(24))
    d.text((90, 240), f"{doc['recipient']} 様", font=f(32, True))
    d.text((760, 240), doc["issuer"], font=f(26, True))
    d.text((760, 280), DUMMY_ADDR, font=f(19))
    d.text((760, 310), f"登録番号 {DUMMY_REG}", font=f(19))
    d.text((90, 380), "9月分のご請求内容は次の通りです。", font=f(24))
    y = 450
    for it in doc["items"]:
        q = it["quantity"]
        d.text((110, y), f"・{it['description']}", font=f(26))
        right(d, W - 100, y, yen(it["amount"]), 26)
        d.text((150, y + 36), f"（{q} 件 × {yen(it['unit_price'])}）", font=f(19), fill="#555")
        y += 84
    sub, tax, total, _ = calc(doc["items"])
    d.line((90, y, W - 90, y), fill="black", width=2)
    y += 20
    for lab, v in [("小計（税抜）", sub), ("消費税 10%", tax)]:
        d.text((700, y), lab, font=f(26))
        right(d, W - 100, y, yen(v), 26)
        y += 44
    d.text((700, y + 6), "ご請求合計", font=f(30, True))
    right(d, W - 100, y + 6, yen(total), 30, True)
    d.text((90, y + 110), f"お支払期限：{doc['due_text']}　振込手数料はご負担ください。", font=f(22))
    watermark(d)
    return im


def scanify(im, seed=7):
    rnd = random.Random(seed)
    im = im.convert("L").rotate(1.4, resample=Image.BICUBIC, expand=False, fillcolor=235)
    im = im.filter(ImageFilter.GaussianBlur(0.9))
    px = im.load()
    for _ in range(int(W * H * 0.06)):
        x, y = rnd.randrange(W), rnd.randrange(H)
        v = px[x, y] + rnd.randint(-45, 25)
        px[x, y] = max(0, min(255, v))
    return im.convert("RGB")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    truth = []
    for doc in DOCS:
        im = {"L1": L1, "L2": L2, "L3": L3, "L4": L4}[doc["layout"]](doc)
        if doc.get("scan"):
            im = scanify(im)
        im.save(OUT / f"{doc['id']}.png")
        if doc.get("pdf"):
            im.save(OUT / f"{doc['id']}.pdf", resolution=150)
        sub, tax, total, _ = calc(doc["items"])
        truth.append({
            "file": f"{doc['id']}.pdf" if doc.get("pdf") else f"{doc['id']}.png",
            "doc_type": doc["doc_type"], "doc_number": doc["doc_number"],
            "issue_date": doc["issue_date"], "due_date": doc["due_date"],
            "issuer": doc["issuer"], "recipient": doc["recipient"],
            "items": doc["items"], "subtotal": sub, "tax": tax, "total": total,
        })
    TRUTH.write_text(json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8")
    print(len(truth), "docs")


if __name__ == "__main__":
    main()
