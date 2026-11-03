"""Bill X-Ray: drop in a utility bill PDF -> plan, usage, time-of-use charges and battery savings.

Run:  streamlit run app.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from battery import EC_BAT_5, Battery, analyze
from extract import SAMPLES, extract

st.set_page_config(page_title="Bill X-Ray", page_icon="⚡", layout="wide")
KIND_LABELS = {"peak": "Peak", "mid_peak": "Mid-peak", "off_peak": "Off-peak",
               "super_off_peak": "Super off-peak", "tier": "Tiered", "other": "Other"}


# ---------- Docling, loaded once ----------

@st.cache_resource(show_spinner="Loading document AI models (first run only)...")
def get_parser():
    from parse import make_converter, parse_pdf
    make_converter()          # warm up the models so the first bill isn't slow
    return parse_pdf


@st.cache_data(show_spinner="Reading the bill with Docling...")
def parse_bytes(data: bytes, ocr: bool):
    """Docling reads files, so write the upload to a temp file. Cached by file content."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(data)
        path = f.name
    try:
        return get_parser()(path, ocr=ocr)
    finally:
        Path(path).unlink(missing_ok=True)


# ---------- sidebar: input ----------

with st.sidebar:
    st.header("1. Bill")
    source = st.radio("Source", ["Sample bill", "Upload a PDF"], horizontal=True)
    pdf_bytes = None
    if source == "Sample bill":
        name = st.selectbox("Sample (fictional)", sorted(p.name for p in SAMPLES.glob("*.pdf")))
        pdf_bytes = (SAMPLES / name).read_bytes()
    else:
        upload = st.file_uploader("Utility bill PDF", type="pdf")
        pdf_bytes = upload.getvalue() if upload else None
    ocr = st.checkbox("Scanned bill (use OCR)", help="Turn on for photos or scans. Slower.")
    st.header("2. Battery")
    capacity = st.number_input("Usable capacity (kWh)", 1.0, 40.0, EC_BAT_5.usable_kwh, 0.5)
    efficiency = st.slider("Round-trip efficiency", 0.70, 0.98, EC_BAT_5.efficiency, 0.01)
    cost = st.number_input("Installed cost ($)", 0.0, 50000.0, EC_BAT_5.installed_cost, 250.0)
    battery = Battery(EC_BAT_5.model if capacity == EC_BAT_5.usable_kwh else "Custom", capacity, efficiency, cost)
    st.caption(f"Default: {EC_BAT_5.model}, a fictional sample battery.")


# ---------- main page ----------

st.title("⚡ Bill X-Ray")
st.caption("Document AI reads a utility bill, finds the time-of-use charges, and estimates "
           "how much a home battery could save by shifting peak usage.")

if pdf_bytes is None:
    st.info("Pick a sample bill or upload a PDF in the sidebar.")
    st.stop()

parsed = parse_bytes(pdf_bytes, ocr)
bill = extract(parsed)

# --- what the bill says ---
st.subheader(bill.utility or "Unknown utility")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total due", f"${bill.total_due:,.2f}" if bill.total_due is not None else "not found")
c2.metric("Usage", f"{bill.total_kwh:,.0f} kWh")
c3.metric("Billing days", bill.days or "not found")
c4.metric("Plan type", "Time-of-use" if bill.is_tou else "Not time-of-use")
st.write(f"**Rate plan:** {bill.plan or 'not found'}  \n"
         f"**Billing period:** {bill.period_start or '?'} to {bill.period_end or '?'}")

for w in bill.warnings:
    st.warning(w)

if bill.periods:
    st.dataframe(pd.DataFrame([{
        "Period": KIND_LABELS.get(p.kind, p.kind), "As printed": p.label, "kWh": p.kwh,
        "Rate ($/kWh)": p.rate, "Amount ($)": p.amount,
        "Share of energy $": f"{p.amount / sum(q.amount for q in bill.periods):.0%}",
    } for p in bill.periods]), hide_index=True, width="stretch")


# --- what a battery would do ---
st.subheader(f"Battery: {battery.model} ({battery.usable_kwh:g} kWh)")
result = analyze(bill, battery)

if not result.eligible:
    st.info(result.reason)
else:
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Savings this bill", f"${result.monthly_savings:,.2f}")
    m2.metric("Per year (est.)", f"${result.annual_savings:,.0f}")
    m3.metric("Payback", f"{result.payback_years:g} years")
    m4.metric("Peak kWh covered", f"{result.shifted_kwh / next(p.kwh for p in bill.periods if p.kind == 'peak'):.0%}")
    st.success(result.reason)

    chart = pd.DataFrame({
        "Without battery": result.before,
        "With battery": result.after,
    }).rename(index=KIND_LABELS)
    st.write("**Energy charges by period ($)**")
    st.bar_chart(chart, stack=False, color=["#9aa9b3", "#2bb59a"])
    st.caption("Annual figure scales this bill's season to a full year; summer and winter rates differ. "
               "Savings from shifting alone; backup power, incentives and solar are not included.")

# --- under the hood ---
with st.expander("What Docling saw (layout + tables)"):
    st.markdown(parsed.markdown)
    for i, df in enumerate(parsed.tables):
        st.write(f"Table {i}")
        st.dataframe(df, hide_index=True)

st.caption("Prototype. Sample bills are fictional. Not financial advice.")