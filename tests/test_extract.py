import pandas as pd
import pytest

from extract import classify_period, energy_columns, extract, to_number


@pytest.mark.parametrize("cell, expected", [
    ("$1,234.56", 1234.56), ("0.410 $/kWh", 0.41), ("856 kWh", 856.0), ("", None), ("nan", None),
])
def test_to_number_ignores_units_and_symbols(cell, expected):
    assert to_number(cell) == expected


@pytest.mark.parametrize("label, kind", [
    ("On-Peak (4 PM - 9 PM)", "peak"),
    ("Peak 5-8 PM weekdays", "peak"),
    ("Off Peak all other hours", "off_peak"),
    ("Super Off-Peak (9 AM - 2 PM)", "super_off_peak"),
    ("Mid-Peak", "mid_peak"),
    ("Tier 1 (first 500 kWh)", "tier"),
])
def test_classify_period_checks_off_peak_before_peak(label, kind):
    assert classify_period(label) == kind


def test_columns_found_by_header_not_position():
    df = pd.DataFrame(columns=["Description", "Rate", "kWh Used", "Charge"])        # rate before kWh
    assert energy_columns(df) == ("kWh Used", "Rate", "Charge")
    df = pd.DataFrame(columns=["Energy Charge", "kWh", "Price per kWh", "Total"])   # 'Charge' in label col
    assert energy_columns(df) == ("kWh", "Price per kWh", "Total")


def test_tou_bill_fields(tou_parsed):
    bill = extract(tou_parsed)
    assert bill.utility == "Riverbend Electric"                       # SAMPLE banner heading skipped
    assert bill.plan == "Residential Time-of-Use 4-9 PM (TOU-49)"
    assert (bill.period_start, bill.period_end) == ("2026-07-03", "2026-08-01")   # swapped cells
    assert bill.days == 29
    assert bill.total_due == 347.78
    assert [p.kind for p in bill.periods] == ["peak", "off_peak", "super_off_peak"]
    assert bill.total_kwh == 856
    assert bill.is_tou
    assert bill.warnings == []


def test_split_cell_plan_and_flat_rate(flat_parsed):
    bill = extract(flat_parsed)
    assert bill.plan == "Standard Residential (R-1)"                  # 'Rate' | 'Schedule ...' rejoined
    assert not bill.is_tou
    assert bill.warnings == []


def test_misread_digit_is_flagged(tou_parsed):
    tou_parsed.tables[2].iloc[0, 1] = "242"        # Docling misreads 212 as 242
    warnings = extract(tou_parsed).warnings
    assert any("On-Peak" in w for w in warnings)                      # kWh x rate != amount
    assert any("856" in w for w in warnings)                          # periods no longer sum to total


def test_missing_rate_is_derived_from_amount(tou_parsed):
    tou_parsed.tables[2].iloc[0, 2] = ""           # rate cell blank on the bill
    peak = extract(tou_parsed).periods[0]
    assert peak.rate == pytest.approx(0.52)


def test_no_energy_table_warns_instead_of_crashing(tou_parsed):
    tou_parsed.tables = tou_parsed.tables[:2]
    bill = extract(tou_parsed)
    assert bill.periods == []
    assert "No energy charges table found" in bill.warnings