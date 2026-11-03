"""Field extraction: Docling's tables + text -> a structured bill (plan, usage, time-of-use charges).

Run:  python extract.py samples/riverbend_tou_summer.pdf   # one bill
      python extract.py                                    # score every sample against samples/expected.json

Note: trust content, not positions. Docling can swap or split cells,
so fields are found by what they look like (a date range, "Rate Schedule ...",
a column header containing "kWh"), not by row or column number.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

SAMPLES = Path(__file__).parent / "samples"
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
DATE_RANGE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:to|through|-)\s*(\d{4}-\d{2}-\d{2})")
PLAN = re.compile(r"Rate\s+Schedule\s*:?\s*(.+)", re.I)
TOTAL_DUE = re.compile(r"(total\s+amount\s+due|amount\s+due|total\s+due)", re.I)
RATE_WORDS = ("rate", "price", "$/kwh", "per kwh")

@dataclass
class Period:
    label: str     # as printed on the bill
    kind: str      # peak | mid_peak | off_peak | super_off_peak | tier | other
    kwh: float
    rate: float    # $/kWh
    amount: float  # $


@dataclass
class Bill:
    utility: str | None
    plan: str | None
    period_start: str | None
    period_end: str | None
    total_due: float | None
    periods: list[Period]
    warnings: list[str] = field(default_factory=list)

    @property
    def total_kwh(self) -> float:
        return sum(p.kwh for p in self.periods)

    @property
    def is_tou(self) -> bool:
        return any(p.kind == "peak" for p in self.periods)

    @property
    def days(self) -> int | None:
        if not (self.period_start and self.period_end):
            return None
        return (date.fromisoformat(self.period_end) - date.fromisoformat(self.period_start)).days


def to_number(cell) -> float | None:
    """'$1,234.56' -> 1234.56, '0.410 $/kWh' -> 0.41, '856 kWh' -> 856.0, '' -> None."""
    m = NUMBER.search(str(cell))
    return float(m.group().replace(",", "")) if m else None


def classify_period(label: str) -> str:
    """Map a printed label to a time-of-use period. Order matters: 'off-peak' also contains 'peak'."""
    s = label.lower().replace("-", " ")
    if re.search(r"super\s*off\s*peak", s):
        return "super_off_peak"
    if re.search(r"off\s*peak", s):
        return "off_peak"
    if re.search(r"(mid|partial)\s*peak|shoulder", s):
        return "mid_peak"
    if "peak" in s:
        return "peak"
    if re.search(r"tier|baseline|block", s):
        return "tier"
    return "other"

def row_texts(tables: list[pd.DataFrame]) -> list[str]:
    """Each table row joined into one string, so split or swapped cells read as one line."""
    out = []
    for df in tables:
        for row in df.astype(str).values.tolist():
            out.append(" ".join(v.strip() for v in row if v.strip() and v != "nan"))
    return out


def find_utility(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if text and "sample bill" not in text.lower():
                return text
    return None


def first_match(pattern: re.Pattern, lines: list[str]):
    for line in lines:
        m = pattern.search(line)
        if m:
            return m
    return None

def find_column(columns: list, include: tuple, exclude: tuple = ()):
    """First non-label column whose header contains an include word and no exclude word."""
    for c in columns[1:]:
        h = str(c).lower()
        if any(k in h for k in include) and not any(k in h for k in exclude):
            return c
    return None


def energy_columns(df: pd.DataFrame) -> tuple:
    cols = list(df.columns)
    kwh = find_column(cols, ("kwh", "usage", "used"), exclude=RATE_WORDS)
    rate = find_column(cols, RATE_WORDS)
    amount = find_column(cols, ("amount", "charge", "total", "cost"), exclude=RATE_WORDS + ("kwh",))
    return kwh, rate, amount


def find_energy_table(tables: list[pd.DataFrame]) -> pd.DataFrame | None:
    for df in tables:
        if all(c is not None for c in energy_columns(df)):
            return df
    return None


def read_periods(df: pd.DataFrame, warnings: list[str]) -> list[Period]:
    kwh_c, rate_c, amount_c = energy_columns(df)
    periods = []
    for _, row in df.iterrows():
        label = str(row[df.columns[0]]).strip()
        if not label or label.lower().startswith("total"):
            continue
        kwh, rate, amount = to_number(row[kwh_c]), to_number(row[rate_c]), to_number(row[amount_c])
        if kwh is None or (rate is None and amount is None):
            warnings.append(f"Skipped row '{label}': missing kWh or price")
            continue
        rate = rate if rate is not None else amount / kwh
        amount = amount if amount is not None else kwh * rate
        periods.append(Period(label, classify_period(label), kwh, round(rate, 4), round(amount, 2)))
    return periods

def validate(bill: Bill, energy_df: pd.DataFrame | None) -> None:
    """Cross-check the numbers against each other, the way an analyst would."""
    if not bill.periods:
        bill.warnings.append("No energy charges table found")
    for p in bill.periods:
        if abs(p.kwh * p.rate - p.amount) > 0.05:
            bill.warnings.append(f"'{p.label}': {p.kwh:g} kWh x ${p.rate} != ${p.amount}")
    if energy_df is not None:
        kwh_c = energy_columns(energy_df)[0]
        for _, row in energy_df.iterrows():
            if str(row[energy_df.columns[0]]).lower().startswith("total"):
                printed = to_number(row[kwh_c])
                if printed is not None and abs(printed - bill.total_kwh) > 0.5:
                    bill.warnings.append(f"Periods sum to {bill.total_kwh:g} kWh but the bill prints {printed:g}")
    for name in ("plan", "period_start", "total_due"):
        if getattr(bill, name) is None:
            bill.warnings.append(f"Could not find {name.replace('_', ' ')}")

def extract(parsed) -> Bill:
    """parsed: anything with .markdown (str) and .tables (list of DataFrames), e.g. parse.ParsedBill."""
    lines = row_texts(parsed.tables) + parsed.markdown.splitlines()
    plan = first_match(PLAN, lines)
    period = first_match(DATE_RANGE, lines)
    due_line = next((l for l in row_texts(parsed.tables) if TOTAL_DUE.search(l)), None)
    energy_df = find_energy_table(parsed.tables)

    bill = Bill(
        utility=find_utility(parsed.markdown),
        plan=plan.group(1).strip(" |") if plan else None,
        period_start=period.group(1) if period else None,
        period_end=period.group(2) if period else None,
        total_due=to_number(TOTAL_DUE.sub("", due_line)) if due_line else None,
        periods=[],
    )
    if energy_df is not None:
        bill.periods = read_periods(energy_df, bill.warnings)
    validate(bill, energy_df)
    return bill


def show(bill: Bill) -> None:
    print(f"Utility:  {bill.utility}")
    print(f"Plan:     {bill.plan}   ({'time-of-use' if bill.is_tou else 'not time-of-use'})")
    print(f"Period:   {bill.period_start} to {bill.period_end} ({bill.days} days)")
    print(f"Usage:    {bill.total_kwh:g} kWh   Total due: ${bill.total_due}")
    for p in bill.periods:
        print(f"  {p.kind:<15} {p.kwh:>6g} kWh  x ${p.rate:<7} = ${p.amount:>8.2f}   ({p.label})")
    for w in bill.warnings:
        print(f"  WARNING: {w}")

def score_samples() -> None:
    from parse import parse_pdf   # imported here so tests can use extract() without loading Docling

    truth = json.loads((SAMPLES / "expected.json").read_text(encoding="utf-8"))
    passed = total = 0
    for name, exp in truth.items():
        bill = extract(parse_pdf(SAMPLES / name))
        checks = {
            "utility": bill.utility == exp["utility"],
            "plan": bill.plan == exp["plan"],
            "period": (bill.period_start, bill.period_end) == (exp["period_start"], exp["period_end"]),
            "total_kwh": bill.total_kwh == exp["total_kwh"],
            "total_due": bill.total_due == exp["total_due"],
            "periods": [(p.kind, p.kwh, p.rate, p.amount) for p in bill.periods]
                       == [(q["kind"], q["kwh"], q["rate"], q["amount"]) for q in exp["periods"]],
        }
        passed, total = passed + sum(checks.values()), total + len(checks)
        misses = [k for k, ok in checks.items() if not ok]
        print(f"{name:<28} {sum(checks.values())}/{len(checks)}  {'all correct' if not misses else 'MISSED: ' + ', '.join(misses)}")
    print(f"\nField accuracy: {passed}/{total} = {passed / total:.0%}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        from parse import parse_pdf
        show(extract(parse_pdf(sys.argv[1])))
    else:
        score_samples()