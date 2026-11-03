"""Hand-built stand-ins for Docling output, so tests run in milliseconds without loading models.

The tables copy what Docling really produces for some sample bills:
a swapped label/value pair and a label split across two cells.
"""

from types import SimpleNamespace

import pandas as pd
import pytest


def account_box(period_row, plan_row):
    return pd.DataFrame([
        ["Account Number", "XX-0000"],
        ["Customer", "Test Person"],
        period_row,
        plan_row,
    ])


def summary(total_due):
    return pd.DataFrame([["Electric Energy Charges", "$1.00"], ["Total Amount Due", total_due]],
                        columns=["Item", "Amount"])


@pytest.fixture
def tou_parsed():
    """Riverbend layout: kWh before rate, three TOU periods, swapped billing-period cells."""
    energy = pd.DataFrame([
        ["On-Peak (4 PM - 9 PM)", "212", "$0.5200", "$110.24"],
        ["Off-Peak", "486", "$0.3400", "$165.24"],
        ["Super Off-Peak (9 AM - 2 PM)", "158", "$0.2900", "$45.82"],
        ["Total energy", "856 kWh", "", "$321.30"],
    ], columns=["Time Period", "Usage (kWh)", "Rate ($/kWh)", "Amount"])
    return SimpleNamespace(
        markdown="## Riverbend Electric\n\n## SAMPLE BILL - FICTIONAL DATA FOR SOFTWARE TESTING\n",
        tables=[account_box(["2026-07-03 to 2026-08-01", "Billing Period"],
                            ["Rate Schedule", "Residential Time-of-Use 4-9 PM (TOU-49)"]),
                summary("$347.78"), energy],
    )


@pytest.fixture
def flat_parsed():
    """Prairie layout: tiered (not TOU) plan, 'Rate | Schedule ...' split across cells."""
    energy = pd.DataFrame([
        ["Tier 1 (first 500 kWh)", "500", "$0.160", "$80.00"],
        ["Tier 2 (above 500 kWh)", "274", "$0.190", "$52.06"],
        ["Total energy", "774 kWh", "", "$132.06"],
    ], columns=["Energy Charge", "kWh", "Price per kWh", "Total"])
    return SimpleNamespace(
        markdown="## Prairie Power Cooperative\n",
        tables=[account_box(["2026-06-10 to 2026-07-09", "Billing Period"],
                            ["Rate", "Schedule Standard Residential (R-1)"]),
                summary("$145.81"), energy],
    )