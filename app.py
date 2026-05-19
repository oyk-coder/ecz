import streamlit as st

st.set_page_config(
    page_title="PharmaSentinel-RX",
    page_icon="+",
    layout="wide",
)

DEFAULTS = {
    "selected_patient_id": 1001,
    "analysis_triggered": False,
    "pharmacist_decision": None,
    "report_generated": False,
    "decision_log": [],
    "risk_filter": ["KRITIK", "YUKSEK", "ORTA", "DUSUK"],
    "show_ddi_heatmap": True,
    "show_cars_radar": True,
    "show_fall_chart": True,
}

for key, default in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title("PharmaSentinel-RX")
st.error("DIKKAT: Egitim amacli prototip.")
st.metric("Kayitli Hasta", 5)
st.info("Sol menuден hasta analizi sayfasina gecebilirsiniz.")
