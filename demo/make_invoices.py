"""Demo invoices: HTML pages printed to PDF with Edge (or Chrome) in headless mode.

The PDFs have a real text layer and Turkish characters, and look like the
e-Arşiv invoices a Turkish SME receives. All companies and numbers are made up.

    python demo/make_invoices.py
"""

import html
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).resolve().parent / "faturalar"

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "msedge", "google-chrome", "chromium",
]

BUYER = ("XYZ Market Ltd. Şti.", "9876543210", "Atatürk Cad. No: 42, Kadıköy / İstanbul")

INVOICES = [
    {
        # Known supplier, under the 10,000 TL limit: approved automatically.
        "file": "1-abc-gida-otomatik-onay.pdf",
        "supplier": ("ABC Gıda Sanayi ve Ticaret A.Ş.", "1234567890",
                     "Organize Sanayi Bölgesi 3. Cad. No: 7, Gebze / Kocaeli", "Gebze"),
        "number": "ABC2026000318426", "date": "25.11.2026", "color": "#1f6f43",
        "lines": [("Un 50 kg", 2, "1250.00"), ("Şeker 25 kg", 1, "1000.00")],
    },
    {
        # Supplier not on the approved list: goes to Telegram for approval.
        "file": "2-deniz-ambalaj-onay-gerekli.pdf",
        "supplier": ("Deniz Ambalaj San. Tic. Ltd. Şti.", "4567890123",
                     "İkitelli OSB Mah. Ambalajcılar Sitesi B Blok No: 12, Başakşehir / İstanbul",
                     "İkitelli"),
        "number": "DNZ2026000427153", "date": "26.11.2026", "color": "#1d4e89",
        "lines": [("Oluklu koli 40x30x30 (100 adet)", 3, "1450.00"),
                  ("Streç film 50 cm", 10, "190.00")],
    },
    {
        # Known supplier, but over the limit: needs the accounting manager.
        "file": "3-abc-gida-limit-ustu.pdf",
        "supplier": ("ABC Gıda Sanayi ve Ticaret A.Ş.", "1234567890",
                     "Organize Sanayi Bölgesi 3. Cad. No: 7, Gebze / Kocaeli", "Gebze"),
        "number": "ABC2026000318431", "date": "26.11.2026", "color": "#1f6f43",
        "lines": [("Un 50 kg", 8, "1250.00"), ("Ayçiçek yağı 18 L", 3, "1900.00")],
    },
]

VAT_RATE = Decimal("0.20")


def money(value: Decimal) -> str:
    """1234.5 -> 1.234,50 (Turkish format)."""

    whole, cents = f"{value:.2f}".split(".")
    groups = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return ".".join(groups) + "," + cents


def page(invoice: dict) -> str:
    name, tax_id, address, tax_office = invoice["supplier"]
    rows, subtotal = [], Decimal(0)
    for number, (item, quantity, price) in enumerate(invoice["lines"], start=1):
        amount = Decimal(price) * quantity
        subtotal += amount
        rows.append(f"<tr><td>{number}</td><td>{html.escape(item)}</td><td class=r>{quantity}</td>"
                    f"<td class=r>{money(Decimal(price))} TL</td><td class=r>%20</td>"
                    f"<td class=r>{money(amount)} TL</td></tr>")
    vat = (subtotal * VAT_RATE).quantize(Decimal("0.01"))
    total = subtotal + vat
    e = html.escape
    return f"""<!doctype html><html lang="tr"><head><meta charset="utf-8"><style>
@page {{ size: A4; margin: 18mm 16mm; }}
body {{ font-family: "Segoe UI", Arial, sans-serif; color: #222; font-size: 10.5pt; }}
.top {{ display: flex; justify-content: space-between; border-bottom: 3px solid {invoice["color"]}; padding-bottom: 10px; }}
.brand {{ font-size: 17pt; font-weight: 700; color: {invoice["color"]}; }}
.muted {{ color: #666; font-size: 9pt; line-height: 1.5; }}
.title {{ text-align: right; }}
.title h1 {{ margin: 0; font-size: 22pt; letter-spacing: 2px; color: {invoice["color"]}; }}
.meta {{ display: flex; justify-content: space-between; margin: 18px 0; }}
.box {{ border: 1px solid #ddd; border-radius: 6px; padding: 10px 12px; width: 46%; }}
.box b {{ display: block; color: {invoice["color"]}; font-size: 9pt; text-transform: uppercase; margin-bottom: 4px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
th {{ background: {invoice["color"]}; color: #fff; text-align: left; padding: 7px; font-size: 9pt; }}
td {{ padding: 7px; border-bottom: 1px solid #eee; }}
.r {{ text-align: right; }}
.totals {{ width: 44%; margin-left: auto; margin-top: 14px; }}
.totals td {{ border: none; padding: 4px 7px; }}
.grand td {{ font-size: 13pt; font-weight: 700; border-top: 2px solid {invoice["color"]}; padding-top: 8px; }}
.foot {{ margin-top: 40px; font-size: 8.5pt; color: #777; border-top: 1px solid #eee; padding-top: 8px; }}
</style></head><body>
<div class="top">
  <div><div class="brand">{e(name)}</div>
    <div class="muted">{e(address)}<br>Vergi Dairesi: {e(tax_office)} &nbsp;·&nbsp; VKN: {tax_id}</div></div>
  <div class="title"><h1>FATURA</h1><div class="muted">e-Arşiv Fatura</div></div>
</div>
<div class="meta">
  <div class="box"><b>Sayın</b>{e(BUYER[0])}<br><span class="muted">{e(BUYER[2])}<br>VKN: {BUYER[1]}</span></div>
  <div class="box"><b>Fatura bilgileri</b>
    Fatura No: {invoice["number"]}<br>Fatura Tarihi: {invoice["date"]}<br>
    Senaryo: TEMELFATURA &nbsp;·&nbsp; Tipi: SATIŞ</div>
</div>
<table><tr><th>#</th><th>Mal / Hizmet</th><th class=r>Miktar</th><th class=r>Birim Fiyat</th>
<th class=r>KDV</th><th class=r>Tutar</th></tr>{''.join(rows)}</table>
<table class="totals">
  <tr><td>Ara Toplam</td><td class=r>{money(subtotal)} TL</td></tr>
  <tr><td>KDV (%20)</td><td class=r>{money(vat)} TL</td></tr>
  <tr class="grand"><td>Genel Toplam</td><td class=r>{money(total)} TL</td></tr>
</table>
<div class="foot">Ödeme: fatura tarihinden itibaren 30 gün. Bu belge demo amaçlı üretilmiştir; şirketler ve tutarlar gerçek değildir.</div>
</body></html>"""


def browser() -> str:
    for candidate in BROWSERS:
        found = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if found:
            return found
    raise SystemExit("Edge or Chrome not found; it prints the HTML to PDF.")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    exe = browser()
    with tempfile.TemporaryDirectory() as tmp:
        for invoice in INVOICES:
            source = Path(tmp) / (invoice["file"] + ".html")
            source.write_text(page(invoice), encoding="utf-8")
            target = OUT / invoice["file"]
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                            f"--print-to-pdf={target}", source.as_uri()],
                           check=True, capture_output=True, timeout=60)
            print(f"written: {target.relative_to(OUT.parent.parent)}")


if __name__ == "__main__":
    main()
