"""Battery load-shift analysis: how much of a time-of-use bill could a home battery move off-peak?

Run:  python battery.py samples/riverbend_tou_summer.pdf
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from extract import Bill, Period


@dataclass(frozen=True)
class Battery:
    model: str
    usable_kwh: float       # energy it can deliver per full cycle
    efficiency: float       # round trip: kWh out / kWh in
    installed_cost: float   # $, before incentives


# Fictional sample product from "An Electrification Company"
EC_BAT_5 = Battery(model="EC-BAT-5", usable_kwh=5.0, efficiency=0.90, installed_cost=4500.0)

CHARGE_PREFERENCE = ("super_off_peak", "off_peak", "mid_peak")   # periods a battery may charge in


@dataclass
class ShiftResult:
    eligible: bool
    reason: str
    peak_rate: float = 0.0
    charge_rate: float = 0.0
    shifted_kwh: float = 0.0          # peak kWh served by the battery this bill
    monthly_savings: float = 0.0
    annual_savings: float = 0.0       # this bill's daily savings x 365
    payback_years: float | None = None
    before: dict[str, float] | None = None   # $ by period kind
    after: dict[str, float] | None = None


def find(periods: list[Period], kind: str) -> Period | None:
    return next((p for p in periods if p.kind == kind), None)


def charge_period(periods: list[Period]) -> Period | None:
    """Cheapest non-peak period to charge from."""
    candidates = [p for p in periods if p.kind in CHARGE_PREFERENCE]
    return min(candidates, key=lambda p: p.rate, default=None)


def cost_by_kind(periods: list[Period]) -> dict[str, float]:
    out: dict[str, float] = {}
    for p in periods:
        out[p.kind] = round(out.get(p.kind, 0.0) + p.amount, 2)
    return out


def analyze(bill: Bill, battery: Battery = EC_BAT_5) -> ShiftResult:
    peak, charge = find(bill.periods, "peak"), charge_period(bill.periods)
    if not bill.is_tou or peak is None or charge is None:
        return ShiftResult(False, "Not a time-of-use plan: the price depends on how much you use, not when, "
                                  "so shifting usage with a battery saves nothing.")
    if not bill.days:
        return ShiftResult(False, "Billing period not found, so daily usage can't be estimated.")

    # One full cycle per day: charge cheap, discharge into peak, never more than the peak load.
    daily_peak_kwh = peak.kwh / bill.days
    daily_shift = min(battery.usable_kwh, daily_peak_kwh)
    daily_saving = daily_shift * peak.rate - (daily_shift / battery.efficiency) * charge.rate
    if daily_saving <= 0:
        return ShiftResult(False, f"Rate gap too small: ${peak.rate}/kWh peak vs ${charge.rate}/kWh "
                                  f"charging doesn't cover {1 - battery.efficiency:.0%} battery losses.",
                           peak_rate=peak.rate, charge_rate=charge.rate)

    shifted = daily_shift * bill.days
    monthly = round(daily_saving * bill.days, 2)
    annual = round(daily_saving * 365, 2)

    before = cost_by_kind(bill.periods)
    after = dict(before)
    after["peak"] = round(before["peak"] - shifted * peak.rate, 2)
    after[charge.kind] = round(before[charge.kind] + shifted / battery.efficiency * charge.rate, 2)

    return ShiftResult(
        eligible=True,
        reason=f"Charges from {charge.kind.replace('_', '-')} at ${charge.rate}/kWh and covers "
               f"{shifted / peak.kwh:.0%} of peak usage at ${peak.rate}/kWh.",
        peak_rate=peak.rate, charge_rate=charge.rate, shifted_kwh=round(shifted, 1),
        monthly_savings=monthly, annual_savings=annual,
        payback_years=round(battery.installed_cost / annual, 1),
        before=before, after=after,
    )


if __name__ == "__main__":
    from extract import extract
    from parse import parse_pdf

    bill = extract(parse_pdf(sys.argv[1]))
    r = analyze(bill)
    print(f"{bill.utility} | {bill.plan}")
    print(f"Eligible: {r.eligible} | {r.reason}")
    if r.eligible:
        print(f"Shifted:  {r.shifted_kwh:g} kWh this bill")
        print(f"Savings:  ${r.monthly_savings:.2f} this bill, ~${r.annual_savings:,.0f}/yr at this season's rates")
        print(f"Payback:  {r.payback_years} years on ${EC_BAT_5.installed_cost:,.0f} installed")
        print(f"Before:   {r.before}")
        print(f"After:    {r.after}")