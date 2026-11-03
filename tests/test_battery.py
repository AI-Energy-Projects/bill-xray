import pytest

from battery import Battery, analyze
from extract import Bill, Period, extract


def make_bill(periods, start="2026-07-01", end="2026-07-31"):   # 30 days
    return Bill("Test Utility", "Test plan", start, end, 100.0, periods)


def test_riverbend_savings_match_hand_calculation(tou_parsed):
    r = analyze(extract(tou_parsed))
    # 5 kWh/day: 5 x 0.52 avoided - 5/0.9 x 0.29 charging = $0.989/day, over 29 days
    assert r.eligible
    assert r.charge_rate == 0.29                         # cheapest period (super off-peak), not off-peak
    assert r.shifted_kwh == 145.0
    assert r.monthly_savings == pytest.approx(28.68, abs=0.01)
    assert r.payback_years == 12.5


def test_flat_rate_is_not_eligible(flat_parsed):
    r = analyze(extract(flat_parsed))
    assert not r.eligible
    assert "Not a time-of-use plan" in r.reason
    assert r.monthly_savings == 0


def test_shift_capped_by_peak_usage():
    bill = make_bill([Period("Peak", "peak", 60, 0.50, 30.0), Period("Off-Peak", "off_peak", 600, 0.20, 120.0)])
    r = analyze(bill)                                    # 2 kWh/day of peak < 5 kWh battery
    assert r.shifted_kwh == 60.0
    assert r.after["peak"] == 0.0


def test_small_rate_gap_loses_money():
    bill = make_bill([Period("Peak", "peak", 300, 0.30, 90.0), Period("Off-Peak", "off_peak", 600, 0.28, 168.0)])
    r = analyze(bill)                                    # 0.30 < 0.28 / 0.9 = 0.311
    assert not r.eligible
    assert "Rate gap too small" in r.reason


def test_bigger_battery_shifts_more():
    bill = make_bill([Period("Peak", "peak", 600, 0.50, 300.0), Period("Off-Peak", "off_peak", 600, 0.20, 120.0)])
    small = analyze(bill)
    large = analyze(bill, Battery("TEST-10", 10.0, 0.9, 9000.0))
    assert large.shifted_kwh == 2 * small.shifted_kwh


def test_before_after_costs_balance():
    bill = make_bill([Period("Peak", "peak", 300, 0.50, 150.0), Period("Off-Peak", "off_peak", 600, 0.20, 120.0)])
    r = analyze(bill)
    saved = sum(r.before.values()) - sum(r.after.values())
    assert saved == pytest.approx(r.monthly_savings, abs=0.02)