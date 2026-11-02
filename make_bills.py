"""Generate fictional utility bills as PDFs along with true values for testing.

Run:  python make_bills.py   ->  samples/*.pdf and samples/expected.json

Every utility, customer, address and account number here is invented.
Rates are in the range of 2026 US residential time-of-use plans.
"""

from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT_DIR = Path(__file__).parent / "samples"
TAX_RATE = 0.03  # utility users tax, applied to energy + fixed charges

# Each energy row: (label, kind, kWh, $/kWh). kind is what extraction must recover.
BILLS = [
    {
        "file": "riverbend_tou_summer.pdf",
        "layout": "A",
        "utility": "Riverbend Electric",
        "account": "RB-4471-0093",
        "customer": "Jordan Sample",
        "address": "1200 Example Ave, Sampletown, CA 95000",
        "period": ("2026-07-03", "2026-08-01"),
        "plan": "Residential Time-of-Use 4-9 PM (TOU-49)",
        "energy": [
            ("On-Peak (4 PM - 9 PM)", "peak", 212, 0.52),
            ("Off-Peak", "off_peak", 486, 0.34),
            ("Super Off-Peak (9 AM - 2 PM)", "super_off_peak", 158, 0.29),
        ],
        "fixed": [("Base Services Charge", 12.00), ("Wildfire Fund Charge", 4.35)],
    },
    {
        "file": "lakeshore_tou_winter.pdf",
        "layout": "B",
        "utility": "Lakeshore Energy Cooperative",
        "account": "LEC-20-55817",
        "customer": "Alex Placeholder",
        "address": "48 Demo Street, Exampleville, MA 01000",
        "period": ("2026-01-05", "2026-02-03"),
        "plan": "Time of Day Residential (R-TOD)",
        "energy": [
            ("Peak 5-8 PM weekdays", "peak", 138, 0.41),
            ("Off Peak all other hours", "off_peak", 642, 0.24),
        ],
        "fixed": [("Customer Charge", 10.00), ("Distribution Charge", 31.20)],
    },
    {
        "file": "prairie_flat_rate.pdf",
        "layout": "C",
        "utility": "Prairie Power Cooperative",
        "account": "PPC-7731-204",
        "customer": "Sam Testcase",
        "address": "9 Fictional Road, Mocktown, MN 55000",
        "period": ("2026-06-10", "2026-07-09"),
        "plan": "Standard Residential (R-1)",
        "energy": [
            ("Tier 1 (first 500 kWh)", "tier", 500, 0.16),
            ("Tier 2 (above 500 kWh)", "tier", 274, 0.19),
        ],
        "fixed": [("Basic Service Charge", 9.50)],
    },
]


def totals(bill: dict) -> dict:
    energy = round(sum(kwh * rate for _, _, kwh, rate in bill["energy"]), 2)
    fixed = round(sum(amount for _, amount in bill["fixed"]), 2)
    tax = round((energy + fixed) * TAX_RATE, 2)
    return {"energy": energy, "fixed": fixed, "tax": tax, "total": round(energy + fixed + tax, 2)}


def energy_table(bill: dict) -> list[list[str]]:
    """Three layouts with different labels and column orders, like real utilities."""
    rows = bill["energy"]
    if bill["layout"] == "A":
        head = ["Time Period", "Usage (kWh)", "Rate ($/kWh)", "Amount"]
        body = [[lbl, f"{kwh:,}", f"${rate:.4f}", f"${kwh * rate:,.2f}"] for lbl, _, kwh, rate in rows]
    elif bill["layout"] == "B":
        head = ["Description", "Rate", "kWh Used", "Charge"]
        body = [[lbl, f"{rate:.3f} $/kWh", f"{kwh:,}", f"{kwh * rate:,.2f}"] for lbl, _, kwh, rate in rows]
    else:
        head = ["Energy Charge", "kWh", "Price per kWh", "Total"]
        body = [[lbl, f"{kwh:,}", f"${rate:.3f}", f"${kwh * rate:,.2f}"] for lbl, _, kwh, rate in rows]
    total_kwh, energy = sum(kwh for _, _, kwh, _ in rows), totals(bill)["energy"]
    if bill["layout"] == "B":
        total = ["Total energy", "", f"{total_kwh:,}", f"{energy:,.2f}"]
    else:
        total = ["Total energy", f"{total_kwh:,} kWh", "", f"${energy:,.2f}"]
    return [head, *body, total]


def grid(data: list[list[str]], widths: list[float], header: bool = True, total_row: bool = False) -> Table:
    """A ruled table. header=False gives a plain label/value box; total_row bolds the last row."""
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9aa9b3")),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3b4d")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                  ("ALIGN", (1, 0), (-1, -1), "RIGHT")]
    else:
        style += [("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                  ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e8eef2"))]
    if total_row:
        style.append(("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"))
    t = Table(data, colWidths=[w * inch for w in widths])
    t.setStyle(TableStyle(style))
    return t


def render(bill: dict, path: Path) -> None:
    styles = getSampleStyleSheet()
    t = totals(bill)
    start, end = bill["period"]
    story = [
        Paragraph(f"<b>{bill['utility']}</b>", styles["Title"]),
        Paragraph("<font color='#b03030'>SAMPLE BILL - FICTIONAL DATA FOR SOFTWARE TESTING</font>", styles["Normal"]),
        Spacer(1, 10),
        grid([
            ["Account Number", bill["account"]],
            ["Customer", bill["customer"]],
            ["Service Address", bill["address"]],
            ["Billing Period", f"{start} to {end}"],
            ["Rate Schedule", bill["plan"]],
        ], [1.8, 4.9], header=False),
        Spacer(1, 14),
        Paragraph("<b>Account Summary</b>", styles["Heading3"]),
        grid([
            ["Item", "Amount"],
            ["Electric Energy Charges", f"${t['energy']:,.2f}"],
            ["Fixed and Delivery Charges", f"${t['fixed']:,.2f}"],
            [f"Utility Users Tax ({TAX_RATE:.0%})", f"${t['tax']:,.2f}"],
            ["Total Amount Due", f"${t['total']:,.2f}"],
        ], [4.7, 2.0], total_row=True),
        Spacer(1, 14),
        Paragraph("<b>Electric Energy Charges</b>", styles["Heading3"]),
        grid(energy_table(bill), [2.6, 1.3, 1.4, 1.4], total_row=True),
        Spacer(1, 14),
        Paragraph("<b>Fixed and Delivery Charges</b>", styles["Heading3"]),
        grid([["Charge", "Amount"], *[[lbl, f"${amt:,.2f}"] for lbl, amt in bill["fixed"]]], [4.7, 2.0]),
    ]
    SimpleDocTemplate(str(path), pagesize=LETTER, title=f"{bill['utility']} sample bill").build(story)


def expected(bill: dict) -> dict:
    """Ground truth that the extractor should recover from the PDF."""
    return {
        "utility": bill["utility"],
        "plan": bill["plan"],
        "period_start": bill["period"][0],
        "period_end": bill["period"][1],
        "total_kwh": sum(kwh for _, _, kwh, _ in bill["energy"]),
        "total_due": totals(bill)["total"],
        "periods": [{"label": lbl, "kind": kind, "kwh": kwh, "rate": rate, "amount": round(kwh * rate, 2)}
                    for lbl, kind, kwh, rate in bill["energy"]],
    }


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    truth = {}
    for bill in BILLS:
        render(bill, OUT_DIR / bill["file"])
        truth[bill["file"]] = expected(bill)
        print(f"{bill['file']:<28} {truth[bill['file']]['total_kwh']:>5} kWh   ${truth[bill['file']]['total_due']:>8,.2f}")
    (OUT_DIR / "expected.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(f"\nWrote {len(BILLS)} PDFs and expected.json to {OUT_DIR.name}/")


if __name__ == "__main__":
    main()