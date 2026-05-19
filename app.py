import logging
import streamlit as st

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

st.set_page_config(
    page_title="PharmaSentinel-RX | Ana Panel",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULTS = {
    "selected_patient_id": 1001,
    "analysis_triggered":  False,
    "pharmacist_decision": None,
    "report_generated":    False,
    "decision_log":        [],
    "risk_filter":         ["KRİTİK", "YÜKSEK", "ORTA", "DÜŞÜK"],
    "show_ddi_heatmap":    True,
    "show_cars_radar":     True,
    "show_fall_chart":     True,
}

for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.markdown("""
<style>
  .main { background-color: #0f1117; }
  .header-box {
    background: linear-gradient(135deg,#1a2332 0%,#0d3b5e 50%,#1a2332 100%);
    border:1px solid #1e88e5; border-radius:12px;
    padding:28px 36px; margin-bottom:24px;
    box-shadow:0 4px 24px rgba(30,136
