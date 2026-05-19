import logging
import streamlit as st

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)

st.set_page_config(
    page_title="PharmaSentinel-RX | Ana Panel",
    page_icon="⚕",
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

st.error(
    "DİKKAT: Bu uygulama egitim amacli bir yapay zeka prototipidir. "
    "Gercek klinik kararlarda eczaci ve hekim kontrolu esastir."
)

st.title("PharmaSentinel-RX")
st.subheader("Polypharmacy Intelligence & PIM Detection Engine")
st.write("Geriatrik Hasta
