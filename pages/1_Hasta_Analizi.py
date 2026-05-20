# ============================================================
# pages/1_Hasta_Analizi.py — Hasta Analiz & Karar Destek
# ============================================================
 
import logging
from datetime import datetime
 
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
 
from clinical_logic import (
    build_clinical_report,
    build_cohort_summary,
    calculate_cars_score,
    calculate_fall_risk,
    detect_ddi,
    detect_pim,
    get_badge_html,
    get_severity_color,
)
from data_utils import (
    FallRiskClass,
    Medication,
    Patient,
    PATIENTS_DB,
    RiskLevel,
    get_patient,
    get_patient_options,
)
 
logger = logging.getLogger(__name__)
 
# ── Sabitler ─────────────────────────────────────────────────
 
FREKANSLAR = [
    "1x1", "2x1", "3x1", "4x1",
    "gece 1x", "sabah 1x",
    "haftada 1x", "haftada 2x",
    "ayda 1x", "gerektiğinde",
]
 
DOZAJ_SEKILLERI = [
    "Tablet", "Kapsül", "Şurup (ml)", "Ampul (mg)",
    "Patch", "İnhaler", "Damla", "Toz", "Diğer",
]
 
BIRIMLER = ["mg", "mcg", "g", "ml", "IU", "mEq", "%"]
 
FALLRISK_MAP = {
    "KRİTİK":    FallRiskClass.CRITICAL,
    "YÜKSEK":    FallRiskClass.HIGH,
    "ORTA":      FallRiskClass.MODERATE,
    "DÜŞÜK":     FallRiskClass.LOW,
    "Bilinmiyor": FallRiskClass.LOW,   # güvenli varsayılan
}
 
KRONIK_HASTALIK_LISTESI = [
    "Hipertansiyon", "Tip 2 DM", "Tip 1 DM",
    "Kronik Böbrek Hastalığı Evre 1", "Kronik Böbrek Hastalığı Evre 2",
    "Kronik Böbrek Hastalığı Evre 3a", "Kronik Böbrek Hastalığı Evre 3b",
    "Kronik Böbrek Hastalığı Evre 4", "Kronik Böbrek Hastalığı Evre 5",
    "Kalp Yetmezliği (EF<%40)", "Kalp Yetmezliği (EF≥%40)",
    "Koroner Arter Hastalığı", "Miyokard Enfarktüsü (geçirilmiş)",
    "Atriyal Fibrilasyon (AF)", "KOAH", "Astım",
    "Dislipidemi", "Hipotiroidi", "Hipertiroidi",
    "Osteoporoz", "Osteoartrit", "Romatoid Artrit",
    "Demans / Alzheimer", "Parkinson",
    "Depresyon", "Anksiyete Bozukluğu",
    "Anemi", "Epilepsi", "Kanser (aktif)",
    "Karaciğer Yetmezliği", "Peptik Ülser",
    "İnme (geçirilmiş)", "Periferik Arter Hastalığı",
]
 
ALERJI_LISTESI = [
    "Penisilin", "Amoksisilin", "Sefalosporin",
    "Sulfonamid", "Eritromisin", "Tetrasiklin",
    "NSAID", "Aspirin", "İbuprofen",
    "Kodein", "Morfin", "Tramadol",
    "Kontrast Madde", "Lateks",
]
 
# ── Yardımcı Fonksiyonlar ─────────────────────────────────────
 
def _ilac_key(pid: int) -> str:
    return f"ilac_list_{pid}"
 
def _hasta_db_key() -> str:
    return "custom_patients_db"
 
def _get_active_db() -> list:
    """session_state'teki güncel hasta listesini döndürür."""
    if _hasta_db_key() not in st.session_state:
        st.session_state[_hasta_db_key()] = list(PATIENTS_DB)
    return st.session_state[_hasta_db_key()]
 
def _next_pid() -> int:
    db = _get_active_db()
    return max((p.hasta_id for p in db), default=1000) + 1
 
def _get_patient_from_db(pid: int) -> Patient | None:
    return next((p for p in _get_active_db() if p.hasta_id == pid), None)
 
def _get_patient_options_from_db() -> dict[str, int]:
    return {
        f"{p.hasta_id} — {p.ad_soyad} ({p.yas} yaş)": p.hasta_id
        for p in _get_active_db()
    }
 
# ── Session State Güvenlik Ağı ────────────────────────────────
 
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
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v
 
# Hasta DB'sini session_state'e yükle (ilk açılışta)
_get_active_db()
 
# ── Sidebar ───────────────────────────────────────────────────
 
with st.sidebar:
    st.markdown("### ⚕️ PharmaSentinel-RX")
    st.markdown("---")
 
    options = _get_patient_options_from_db()
    if options:
        sel_label = st.selectbox(
            "Hasta seçin", list(options.keys()), label_visibility="collapsed"
        )
        st.session_state.selected_patient_id = options[sel_label]
    else:
        st.warning("Kayıtlı hasta yok.")
 
    st.session_state.risk_filter = st.multiselect(
        "Risk Filtresi",
        ["KRİTİK", "YÜKSEK", "ORTA", "DÜŞÜK"],
        default=st.session_state.risk_filter,
    )
    st.session_state.show_ddi_heatmap = st.toggle(
        "DDI Isı Haritası", value=st.session_state.show_ddi_heatmap
    )
    st.session_state.show_cars_radar = st.toggle(
        "CARS™ Bileşen Grafiği", value=st.session_state.show_cars_radar
    )
    st.session_state.show_fall_chart = st.toggle(
        "Düşme Risk Grafiği", value=st.session_state.show_fall_chart
    )
    st.markdown("---")
    if st.button("🔬 ANALİZ BAŞLAT", use_container_width=True, type="primary"):
        st.session_state.analysis_triggered = True
        st.session_state.pharmacist_decision = None
        st.session_state.report_generated    = True
 
# ── Hesaplamalar ──────────────────────────────────────────────
 
pid     = st.session_state.selected_patient_id
patient = _get_patient_from_db(pid)
 
if patient is None:
    st.error("Hasta bulunamadı. Lütfen sol menüden hasta seçin.")
    st.stop()
 
# İlaç listesini session_state'e taşı (ilk seferinde)
if _ilac_key(pid) not in st.session_state:
    st.session_state[_ilac_key(pid)] = list(patient.aktif_ilaclar)
 
# ANALİZ DAIMA session_state'teki güncel ilaç listesiyle yapılır
patient.aktif_ilaclar = st.session_state[_ilac_key(pid)]
 
pim_hits  = detect_pim(patient)
ddi_hits  = detect_ddi(patient)
fall_risk = calculate_fall_risk(patient)
cars      = calculate_cars_score(patient, pim_hits, ddi_hits, fall_risk)
 
rf    = st.session_state.risk_filter
pim_f = [p for p in pim_hits if p["siddet"] in rf]
ddi_f = [d for d in ddi_hits if d["siddet"] in rf]
 
# ── Başlık ────────────────────────────────────────────────────
 
st.markdown("""
<div class="header-box">
  <p class="header-title">🔬 Hasta Analiz Paneli</p>
  <p class="header-subtitle">
    CARS™ · PDFI™ · PIM Tespiti · DDI Analizi · Klinik Karar Destek
  </p>
</div>
""", unsafe_allow_html=True)
 
st.error(
    "🔴 **DİKKAT:** Eğitim amaçlı prototip. "
    "Gerçek klinik kararlarda eczacı ve hekim kontrolü esastır."
)
 
# ── Hasta Kartı + Metrikler ───────────────────────────────────
 
col_card, col_metrics = st.columns([1.2, 2.8])
 
with col_card:
    badge = get_badge_html(cars["seviye"])
    color_egfr = (
        "#ef5350" if patient.egfr < 45
        else "#ffa726" if patient.egfr < 60
        else "#66bb6a"
    )
    color_alb = "#ef5350" if patient.albumin < 3.5 else "#66bb6a"
    st.markdown(f"""
    <div class="patient-card">
      <h4>👤 {patient.ad_soyad}</h4>
      <p>🆔 {patient.hasta_id} | 🎂 {patient.yas} yaş | {patient.cinsiyet}</p>
      <p>⚖️ {patient.kilo_kg} kg</p>
      <p>🧪 eGFR: <strong style="color:{color_egfr}">{patient.egfr} ml/dk/1.73m²</strong></p>
      <p>🩸 Albumin: <strong style="color:{color_alb}">{patient.albumin} g/dL</strong></p>
      <p>📊 Charlson: <strong>{patient.charlson_index}</strong></p>
      <p>🚶 Morse: <strong>{patient.morse_fall}/125</strong></p>
      <p>🏥 {', '.join(patient.kronik_hastaliklar)}</p>
      <p>⚠️ Alerjiler: {', '.join(patient.alerjiler) or '—'}</p>
      <p style="margin-top:10px">CARS™: {badge}</p>
    </div>
    """, unsafe_allow_html=True)
    st.caption(f"Son analiz: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
 
with col_metrics:
    m1, m2, m3, m4 = st.columns(4)
    def _mbox(val, label, color):
        return (
            f'<div class="metric-box">'
            f'<div class="metric-value" style="color:{color}">{val}</div>'
            f'<div class="metric-label">{label}</div></div>'
        )
    with m1:
        st.markdown(_mbox(cars["skor"],
            f"CARS™ Skor<br>({cars['seviye'].value})",
            get_severity_color(cars["seviye"])), unsafe_allow_html=True)
    with m2:
        crit_pim = sum(1 for p in pim_hits if p["siddet"] == RiskLevel.CRITICAL)
        st.markdown(_mbox(len(pim_hits),
            f"PIM Tespit<br>({crit_pim} KRİTİK)", "#ef5350"),
            unsafe_allow_html=True)
    with m3:
        crit_ddi = sum(1 for d in ddi_hits if d["siddet"] == RiskLevel.CRITICAL)
        st.markdown(_mbox(len(ddi_hits),
            f"DDI Etkileşim<br>({crit_ddi} KRİTİK)", "#ffa726"),
            unsafe_allow_html=True)
    with m4:
        st.markdown(_mbox(fall_risk["skor"],
            f"PDFI™ Skor<br>({fall_risk['seviye'].value})",
            get_severity_color(fall_risk["seviye"])), unsafe_allow_html=True)
 
    polypharmacy = "⚠️ Polifarmasi (≥5 ilaç)." if len(patient.aktif_ilaclar) >= 5 else ""
    st.caption(
        f"{len(patient.aktif_ilaclar)} aktif ilaç analiz edildi. {polypharmacy} "
        f"CARS™: {cars['skor']}/100 — {cars['seviye'].value}."
    )
 
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
 
# ── Grafikler ─────────────────────────────────────────────────
 
viz1, viz2 = st.columns(2)
 
with viz1:
    st.markdown("#### 🎯 CARS™ Kompozit Risk Göstergesi")
    gauge_color = get_severity_color(cars["seviye"])
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=cars["skor"],
        delta={"reference": 50,
               "increasing": {"color": "#ef5350"},
               "decreasing": {"color": "#66bb6a"}},
        number={"font": {"size": 48, "color": "#e3f2fd"}},
        gauge={
            "axis": {"range": [0, 100], "tickwidth": 1,
                     "tickcolor": "#546e7a", "tickfont": {"color": "#90caf9"}},
            "bar":  {"color": gauge_color, "thickness": 0.25},
            "bgcolor": "#1e2736", "borderwidth": 0,
            "steps": [
                {"range": [0,  30], "color": "#1b3a1f"},
                {"range": [30, 50], "color": "#3a2f0a"},
                {"range": [50, 70], "color": "#3a1f0a"},
                {"range": [70,100], "color": "#3a0a0a"},
            ],
            "threshold": {"line": {"color": "#ffffff", "width": 3},
                          "thickness": 0.8, "value": cars["skor"]},
        },
        title={"text": f"Risk: <b>{cars['seviye'].value}</b>",
               "font": {"color": gauge_color, "size": 16}},
    ))
    fig_g.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117",
                        height=280, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(fig_g, use_container_width=True)
 
    if st.session_state.show_cars_radar:
        comp_df = pd.DataFrame({
            "Bileşen": list(cars["bilesenler"].keys()),
            "Katkı":   list(cars["bilesenler"].values()),
        })
        fig_c = px.bar(comp_df, x="Katkı", y="Bileşen", orientation="h",
                       color="Katkı",
                       color_continuous_scale=[[0,"#2e7d32"],[0.4,"#f9a825"],[1,"#b71c1c"]],
                       title="CARS™ Bileşen Katkı Dağılımı")
        fig_c.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=260, coloraxis_showscale=False,
                            margin=dict(t=40,b=10,l=10,r=10),
                            xaxis=dict(title="Katkı Puanı",gridcolor="#263548"),
                            yaxis=dict(title="",automargin=True))
        st.plotly_chart(fig_c, use_container_width=True)
 
with viz2:
    st.markdown("#### 🚶 PDFI™ Düşme Risk Bileşenleri")
    if st.session_state.show_fall_chart:
        fall_df = pd.DataFrame({
            "Bileşen": list(fall_risk["bilesenler"].keys()),
            "Puan":    list(fall_risk["bilesenler"].values()),
        })
        fig_f = px.bar(fall_df, x="Bileşen", y="Puan", color="Puan",
                       color_continuous_scale=[[0,"#1b5e20"],[0.5,"#f57f17"],[1,"#b71c1c"]],
                       title=f"PDFI™: {fall_risk['skor']}/100 ({fall_risk['seviye'].value})")
        fig_f.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=300, coloraxis_showscale=False,
                            margin=dict(t=50,b=20,l=20,r=20),
                            xaxis=dict(title="", tickangle=-20, automargin=True),
                            yaxis=dict(title="Puan", gridcolor="#263548", range=[0,35]))
        st.plotly_chart(fig_f, use_container_width=True)
 
    if st.session_state.show_ddi_heatmap:
        st.markdown("#### 🔥 DDI Etkileşim Matrisi")
        # Her zaman güncel ilaç listesinden oku
        aktif = patient.aktif_ilaclar
        drug_names = [d.isim.split()[0] for d in aktif]
        drug_atcs  = [d.atc for d in aktif]
        n          = len(drug_names)
        matrix     = np.zeros((n, n))
        sev_score  = {RiskLevel.CRITICAL:3, RiskLevel.HIGH:2,
                      RiskLevel.MODERATE:1, RiskLevel.LOW:0}
        for rule in ddi_hits:
            for i, ai in enumerate(drug_atcs):
                for j, aj in enumerate(drug_atcs):
                    if (ai.startswith(rule["ilac_1_atc"][:7]) and
                            aj.startswith(rule["ilac_2_atc"][:7])):
                        sv = sev_score.get(RiskLevel(rule["siddet"]), 0)
                        matrix[i][j] = sv
                        matrix[j][i] = sv
        labels = [["—","DÜŞÜK","YÜKSEK","KRİTİK"][int(v)] for row in matrix for v in row]
        labels = [labels[i*n:(i+1)*n] for i in range(n)]
        fig_h = go.Figure(go.Heatmap(
            z=matrix, x=drug_names, y=drug_names,
            colorscale=[[0,"#1e2736"],[0.33,"#f9a825"],[0.66,"#ef5350"],[1,"#b71c1c"]],
            zmin=0, zmax=3, text=labels, texttemplate="%{text}",
            textfont={"size":9,"color":"#e3f2fd"}, showscale=False,
            hovertemplate="<b>%{y}</b> × <b>%{x}</b><br>%{text}<extra></extra>",
        ))
        fig_h.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=260,
                            margin=dict(t=10,b=10,l=10,r=10),
                            xaxis=dict(tickangle=-30, tickfont=dict(size=9), automargin=True),
                            yaxis=dict(tickfont=dict(size=9), automargin=True))
        st.plotly_chart(fig_h, use_container_width=True)
        st.caption("Isı haritası: Kırmızı hücre KRİTİK DDI — eczacı müdahalesi zorunlu.")
 
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
 
# ── Sekmeler ──────────────────────────────────────────────────
 
tab_pim, tab_ddi, tab_drugs, tab_recete, tab_hasta = st.tabs([
    f"🔴 PIM ({len(pim_f)})",
    f"🟠 DDI ({len(ddi_f)})",
    f"💊 İlaçlar ({len(patient.aktif_ilaclar)})",
    "📋 Reçete Girişi",
    "👤 Hasta Yönetimi",
])
 
# ════════════════════════════════════════════════════════════
# SEKME 1 — PIM
# ════════════════════════════════════════════════════════════
with tab_pim:
    if not pim_f:
        st.success("✅ Seçili risk filtrelerine göre PIM tespit edilmedi.")
    for hit in pim_f:
        with st.expander(f"⚠️ {hit['ilac']} — {hit['kategori']} | {hit['siddet']}",
                         expanded=True):
            ca, cb = st.columns(2)
            with ca:
                st.markdown(f"**Kaynak:** {hit['kural_kaynagi']}")
                st.markdown(f"**Şiddet:** {get_badge_html(hit['siddet'])}",
                            unsafe_allow_html=True)
                st.markdown(f"**ATC:** `{hit['atc']}`")
            with cb:
                st.info(hit["gerekce"])
            st.success(hit["oneri"])
            st.caption(f"📚 {hit['kaynak_url']}")
 
# ════════════════════════════════════════════════════════════
# SEKME 2 — DDI
# ════════════════════════════════════════════════════════════
with tab_ddi:
    if not ddi_f:
        st.success("✅ Seçili risk filtrelerine göre DDI tespit edilmedi.")
    for rule in ddi_f:
        is_critical = rule["siddet"] == RiskLevel.CRITICAL
        with st.expander(
            f"💥 {rule['ilac_1_adi']} × {rule['ilac_2_adi']} | {rule['siddet']}",
            expanded=is_critical
        ):
            cx, cy = st.columns(2)
            with cx:
                st.markdown(f"**Şiddet:** {get_badge_html(rule['siddet'])}",
                            unsafe_allow_html=True)
                st.markdown(f"**Kanıt:** `{rule['kanit_duzeyi']}`")
                st.info(rule["mekanizma"])
            with cy:
                if is_critical:
                    st.error(rule["klinik_sonuc"])
                else:
                    st.warning(rule["klinik_sonuc"])
            st.success(rule["yonetim"])
 
# ════════════════════════════════════════════════════════════
# SEKME 3 — İlaçlar
# ════════════════════════════════════════════════════════════
with tab_drugs:
    fc_colors = {FallRiskClass.CRITICAL: "pim", FallRiskClass.HIGH: "ddi",
                 FallRiskClass.MODERATE: "", FallRiskClass.LOW: ""}
    icons = {FallRiskClass.CRITICAL:"🔴", FallRiskClass.HIGH:"🟠",
             FallRiskClass.MODERATE:"🟡", FallRiskClass.LOW:"🟢"}
    st.caption("Renk: 🔴 KRİTİK · 🟠 YÜKSEK · 🟡 ORTA · 🟢 DÜŞÜK düşme riski")
    for drug in patient.aktif_ilaclar:
        css = fc_colors.get(drug.fall_risk_class, "")
        ico = icons.get(drug.fall_risk_class, "⚪")
        st.markdown(f"""
        <div class="drug-item {css}">
          {ico} <strong>{drug.isim}</strong>
          &nbsp;|&nbsp; Doz: <code>{drug.doz}</code>
          &nbsp;|&nbsp; Frekans: <code>{drug.frekans}</code>
          &nbsp;|&nbsp; ATC: <code>{drug.atc}</code>
          &nbsp;|&nbsp; Düşme: <strong>{drug.fall_risk_class.value}</strong>
        </div>""", unsafe_allow_html=True)
 
# ════════════════════════════════════════════════════════════
# SEKME 4 — REÇETE GİRİŞİ
# ════════════════════════════════════════════════════════════
with tab_recete:
    st.markdown("#### 📋 Reçete Girişi — İlaç Ekle / Sil")
    st.caption(
        "Eklenen ilaçlar anında PIM · DDI · CARS™ · PDFI™ analizine dahil edilir."
    )
 
    # ── Satır 1: Etkin madde + ATC ────────────────────────────
    col_r1, col_r2 = st.columns([3, 1])
    with col_r1:
        r_etkin = st.text_input(
            "💊 Etkin Madde Adı",
            key="r_etkin",
            placeholder="örn: Metformin, Warfarin, Enalapril",
        )
    with col_r2:
        r_atc = st.text_input(
            "ATC Kodu (opsiyonel)",
            key="r_atc",
            placeholder="örn: A10BA02",
            help="Boş bırakabilirsiniz — etkileşim analizi için gerekli değilse XXXX00 atanır.",
        )
 
    # ── Satır 2: Dozaj şekli + miktar + birim ─────────────────
    col_r3, col_r4, col_r5 = st.columns([2, 1, 1])
    with col_r3:
        r_sekil = st.selectbox("💉 Dozaj Şekli", DOZAJ_SEKILLERI, key="r_sekil")
    with col_r4:
        r_miktar = st.number_input(
            "Miktar", min_value=0.0, max_value=10000.0,
            value=0.0, step=0.5, key="r_miktar",
            help="Sayısal miktar — örn: 500 veya 2.5",
        )
    with col_r5:
        r_birim = st.selectbox("Birim", BIRIMLER, key="r_birim")
 
    # ── Satır 3: Sıklık + düşme riski ─────────────────────────
    col_r6, col_r7 = st.columns([2, 2])
    with col_r6:
        r_frek = st.selectbox("🔁 Dozlama Sıklığı", FREKANSLAR, key="r_frek")
    with col_r7:
        r_fallrisk = st.selectbox(
            "⚠️ Düşme Riski Sınıfı",
            ["Bilinmiyor", "DÜŞÜK", "ORTA", "YÜKSEK", "KRİTİK"],
            index=0,
            key="r_fallrisk",
            help=(
                "**Bilinmiyor** seçerseniz sistem otomatik olarak DÜŞÜK atar.\n\n"
                "Kılavuz: Benzodiazepin/hipnotik → KRİTİK · Diüretik → YÜKSEK · "
                "ACE inhibitörü → ORTA · Statin → DÜŞÜK"
            ),
        )
 
    # Bilinmiyor seçildiğinde açıklama göster
    if r_fallrisk == "Bilinmiyor":
        st.info(
            "ℹ️ Düşme riski bilinmiyor olarak işaretlendi. "
            "Sistem **DÜŞÜK** riski otomatik atayacak. "
            "İlaç grubuna göre öneri: \n"
            "- Benzodiazepin, uyku ilacı, antipsikotik → **KRİTİK**\n"
            "- Diüretik, antihipertansif → **YÜKSEK**\n"
            "- ACE inhibitörü, beta bloker → **ORTA**\n"
            "- Statin, PPI, metformin → **DÜŞÜK**"
        )
 
    col_ekle, _ = st.columns([1, 3])
    with col_ekle:
        if st.button("➕ Ekle ve Analiz Et", use_container_width=True, type="primary"):
            if not r_etkin.strip():
                st.warning("⚠️ Etkin madde adı boş bırakılamaz.")
            elif r_miktar <= 0:
                st.warning("⚠️ Miktar sıfırdan büyük olmalıdır.")
            else:
                doz_str  = f"{r_miktar:g} {r_birim} {r_sekil}"
                atc_str  = r_atc.strip().upper() if r_atc.strip() else "XXXX00"
                isim_str = f"{r_etkin.strip()} {r_miktar:g}{r_birim}"
                yeni_ilac = Medication(
                    atc=atc_str,
                    isim=isim_str,
                    doz=doz_str,
                    frekans=r_frek,
                    fall_risk_class=FALLRISK_MAP[r_fallrisk],
                )
                st.session_state[_ilac_key(pid)].append(yeni_ilac)
                st.success(f"✅ **{isim_str}** — {doz_str}, {r_frek} eklendi! Analiz güncellendi.")
                st.rerun()
 
    st.markdown("---")
    st.markdown("##### 📄 Mevcut Reçete")
 
    aktif = st.session_state[_ilac_key(pid)]
    if not aktif:
        st.info("ℹ️ Henüz ilaç eklenmedi.")
    else:
        icons_r = {
            FallRiskClass.CRITICAL: "🔴",
            FallRiskClass.HIGH:     "🟠",
            FallRiskClass.MODERATE: "🟡",
            FallRiskClass.LOW:      "🟢",
        }
        if len(aktif) >= 5:
            st.warning(f"⚠️ **Polifarmasi:** {len(aktif)} ilaç reçetede.")
        for idx, drug in enumerate(aktif):
            ico = icons_r.get(drug.fall_risk_class, "⚪")
            col_info, col_sil = st.columns([6, 1])
            with col_info:
                st.markdown(
                    f"{ico} **{drug.isim}** &nbsp;·&nbsp; "
                    f"`{drug.doz}` &nbsp;·&nbsp; `{drug.frekans}` &nbsp;·&nbsp; "
                    f"ATC: `{drug.atc}` &nbsp;·&nbsp; "
                    f"Düşme: **{drug.fall_risk_class.value}**"
                )
            with col_sil:
                if st.button("🗑️", key=f"rsil_{pid}_{idx}", help="İlacı sil"):
                    st.session_state[_ilac_key(pid)].pop(idx)
                    st.rerun()
 
# ════════════════════════════════════════════════════════════
# SEKME 5 — HASTA YÖNETİMİ + CHARLSON/MORSE HESAPLAMA
# ════════════════════════════════════════════════════════════
with tab_hasta:
 
    sub_ekle, sub_sil, sub_skorlar = st.tabs([
        "➕ Yeni Hasta Ekle",
        "🗑️ Hasta Sil",
        "🧮 Charlson & Morse Hesaplama",
    ])
 
    # ── Alt Sekme: Yeni Hasta Ekle ───────────────────────────
    with sub_ekle:
        st.markdown("#### 👤 Yeni Hasta Kaydı")
        st.caption("Formu doldurup **Kaydet** butonuna tıklayın. Hasta listeye anında eklenir.")
 
        he1, he2, he3 = st.columns(3)
        with he1:
            f_ad    = st.text_input("Ad Soyad", key="f_ad", placeholder="örn: Ayşe T.")
            f_yas   = st.number_input("Yaş", min_value=0, max_value=120, value=65, key="f_yas")
            f_cinsiyet = st.selectbox("Cinsiyet", ["E", "K"], key="f_cinsiyet")
        with he2:
            f_kilo  = st.number_input("Kilo (kg)", min_value=1.0, max_value=300.0,
                                       value=70.0, step=0.5, key="f_kilo")
            f_egfr  = st.number_input("eGFR (ml/dk/1.73m²)", min_value=0.0,
                                       max_value=200.0, value=60.0, step=1.0, key="f_egfr")
            f_albumin = st.number_input("Albumin (g/dL)", min_value=0.0,
                                         max_value=6.0, value=3.8, step=0.1, key="f_albumin")
        with he3:
            # Charlson
            with st.expander("ℹ️ Charlson İndeksi nasıl hesaplanır?"):
                st.markdown("""
**Charlson Komorbidite İndeksi** — her tanı için puan toplanır:
 
| Puan | Tanı / Durum |
|------|-------------|
| **1** | MI, KKY, periferik vasküler hastalık, serebrovasküler hastalık, demans, KOAH, bağ doku hastalığı, peptik ülser, hafif KC hastalığı, DM (komplikasyonsuz) |
| **2** | DM (organ hasarı), hemipleji, orta-ağır böbrek hastalığı, solid tümör, lösemi, lenfoma |
| **3** | Orta-ağır karaciğer hastalığı |
| **6** | Metastatik solid tümör, AIDS |
 
**10 yıllık tahmini mortalite:** 0 → %12 · 1-2 → %26 · 3-4 → %52 · ≥5 → %85
                """)
            f_charlson = st.number_input("Charlson İndeksi (0–37)",
                                          min_value=0, max_value=37,
                                          value=0, key="f_charlson")
 
            # Morse
            with st.expander("ℹ️ Morse Düşme Skoru nasıl hesaplanır?"):
                st.markdown("""
**Morse Düşme Ölçeği** — 6 kriter toplanır:
 
| Puan | Kriter |
|------|--------|
| **25** | Düşme öyküsü (son 3 ay) |
| **15** | İkincil tanı varlığı |
| **15** | Yürüme yardımcısı (koltuk değneği / walker) |
| **30** | IV / heparin kilidi |
| **10** | Yürüyüş / transfer bozukluğu |
| **15** | Mental durum bozukluğu |
 
**Risk:** 0–24 → Düşük · 25–50 → Orta · ≥51 → Yüksek
                """)
            f_morse = st.number_input("Morse Düşme Skoru (0–125)",
                                       min_value=0, max_value=125,
                                       value=20, key="f_morse")
 
        f_kronik = st.multiselect(
            "🏥 Kronik Hastalıklar",
            KRONIK_HASTALIK_LISTESI,
            key="f_kronik",
        )
        f_alerji = st.multiselect(
            "⚠️ Alerjiler",
            ALERJI_LISTESI,
            key="f_alerji",
        )
 
        if st.button("💾 Hastayı Kaydet", use_container_width=True, type="primary"):
            if not f_ad.strip():
                st.warning("⚠️ Ad Soyad boş bırakılamaz.")
            else:
                yeni_pid = _next_pid()
                yeni_hasta = Patient(
                    hasta_id=yeni_pid,
                    ad_soyad=f_ad.strip(),
                    yas=f_yas,
                    cinsiyet=f_cinsiyet,
                    kilo_kg=f_kilo,
                    egfr=f_egfr,
                    albumin=f_albumin,
                    charlson_index=f_charlson,
                    morse_fall=f_morse,
                    kronik_hastaliklar=f_kronik if f_kronik else ["Bilinmiyor"],
                    alerjiler=f_alerji,
                    aktif_ilaclar=[],
                )
                st.session_state[_hasta_db_key()].append(yeni_hasta)
                st.session_state[_ilac_key(yeni_pid)] = []
                st.success(
                    f"✅ **{yeni_hasta.ad_soyad}** (ID: {yeni_pid}) başarıyla eklendi! "
                    "Sol menüden seçebilirsiniz."
                )
                st.rerun()
 
    # ── Alt Sekme: Hasta Sil ─────────────────────────────────
    with sub_sil:
        st.markdown("#### 🗑️ Hasta Sil")
        st.caption("Silme işlemi geri alınamaz. Yalnızca oturum boyunca geçerlidir.")
 
        db = _get_active_db()
        if not db:
            st.info("Kayıtlı hasta bulunmuyor.")
        else:
            sil_options = {
                f"{p.hasta_id} — {p.ad_soyad} ({p.yas} yaş)": p.hasta_id
                for p in db
            }
            sil_label = st.selectbox("Silinecek Hastayı Seçin", list(sil_options.keys()),
                                      key="sil_secim")
            sil_pid   = sil_options[sil_label]
            sil_hasta = next(p for p in db if p.hasta_id == sil_pid)
 
            st.warning(
                f"**{sil_hasta.ad_soyad}** silinecek. "
                f"Bu hastanın tüm ilaç kaydı da temizlenecektir."
            )
            col_sil_btn, _ = st.columns([1, 3])
            with col_sil_btn:
                if st.button("⛔ Evet, Hastayı Sil", use_container_width=True):
                    st.session_state[_hasta_db_key()] = [
                        p for p in db if p.hasta_id != sil_pid
                    ]
                    # İlaç listesini de temizle
                    key = _ilac_key(sil_pid)
                    if key in st.session_state:
                        del st.session_state[key]
                    # Eğer silinen hasta seçiliyse başka birine geç
                    remaining = _get_active_db()
                    if remaining:
                        st.session_state.selected_patient_id = remaining[0].hasta_id
                    st.success(f"✅ **{sil_hasta.ad_soyad}** silindi.")
                    st.rerun()
 
    # ── Alt Sekme: Charlson & Morse Hesaplama ────────────────
    with sub_skorlar:
        st.markdown("#### 🧮 Charlson & Morse İnteraktif Hesaplama")
        st.caption(
            "Tanıları ve kriterleri işaretleyerek skoru otomatik hesaplayın. "
            "Bu hesaplama yalnızca bilgilendirme amaçlıdır."
        )
 
        col_ch, col_mo = st.columns(2)
 
        # ── Charlson Hesaplama ────────────────────────────────
        with col_ch:
            st.markdown("##### 📊 Charlson Komorbidite İndeksi")
 
            ch_puan_1 = st.multiselect(
                "1 Puan — Tanılar",
                ["Miyokard enfarktüsü", "Konjestif kalp yetmezliği",
                 "Periferik vasküler hastalık", "Serebrovasküler hastalık",
                 "Demans", "KOAH", "Bağ doku hastalığı",
                 "Peptik ülser hastalığı", "Hafif karaciğer hastalığı",
                 "Diyabet (komplikasyonsuz)"],
                key="ch1",
            )
            ch_puan_2 = st.multiselect(
                "2 Puan — Tanılar",
                ["Diyabet (organ hasarı ile)", "Hemipleji/parapleji",
                 "Orta-ağır böbrek hastalığı", "Solid tümör (metastazsız)",
                 "Lösemi", "Lenfoma/multipl miyelom"],
                key="ch2",
            )
            ch_puan_3 = st.multiselect(
                "3 Puan — Tanılar",
                ["Orta-ağır karaciğer hastalığı"],
                key="ch3",
            )
            ch_puan_6 = st.multiselect(
                "6 Puan — Tanılar",
                ["Metastatik solid tümör", "AIDS"],
                key="ch6",
            )
 
            ch_toplam = (
                len(ch_puan_1) * 1 +
                len(ch_puan_2) * 2 +
                len(ch_puan_3) * 3 +
                len(ch_puan_6) * 6
            )
            if ch_toplam == 0:
                ch_renk, ch_yorum = "#66bb6a", "Düşük komorbidite — %12 on yıllık mortalite"
            elif ch_toplam <= 2:
                ch_renk, ch_yorum = "#ffa726", "Orta komorbidite — %26 on yıllık mortalite"
            elif ch_toplam <= 4:
                ch_renk, ch_yorum = "#ef5350", "Yüksek komorbidite — %52 on yıllık mortalite"
            else:
                ch_renk, ch_yorum = "#b71c1c", "Çok yüksek komorbidite — %85 on yıllık mortalite"
 
            st.markdown(
                f"<div style='background:#1e2736;border-radius:8px;padding:16px;margin-top:8px;'>"
                f"<span style='font-size:2rem;font-weight:bold;color:{ch_renk}'>{ch_toplam}</span>"
                f"<span style='color:#b0bec5;'> / 37 puan</span><br>"
                f"<span style='color:{ch_renk};font-size:0.9rem'>{ch_yorum}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
 
        # ── Morse Hesaplama ───────────────────────────────────
        with col_mo:
            st.markdown("##### 🚶 Morse Düşme Ölçeği")
 
            mo_dusme  = st.checkbox("Düşme öyküsü var (son 3 ay) — **+25 puan**", key="mo1")
            mo_ikinci = st.checkbox("İkincil tanı var — **+15 puan**", key="mo2")
            mo_yurume = st.checkbox("Yürüme yardımcısı kullanıyor — **+15 puan**", key="mo3")
            mo_iv     = st.checkbox("IV / heparin kilidi var — **+30 puan**", key="mo4")
            mo_yuruy  = st.checkbox("Yürüyüş / transfer bozukluğu — **+10 puan**", key="mo5")
            mo_mental = st.checkbox("Mental durum bozukluğu — **+15 puan**", key="mo6")
 
            mo_toplam = (
                (25 if mo_dusme  else 0) +
                (15 if mo_ikinci else 0) +
                (15 if mo_yurume else 0) +
                (30 if mo_iv     else 0) +
                (10 if mo_yuruy  else 0) +
                (15 if mo_mental else 0)
            )
            if mo_toplam < 25:
                mo_renk, mo_yorum = "#66bb6a", "DÜŞÜK risk — standart önlemler yeterli"
            elif mo_toplam <= 50:
                mo_renk, mo_yorum = "#ffa726", "ORTA risk — düşme önleme protokolü başlatın"
            else:
                mo_renk, mo_yorum = "#ef5350", "YÜKSEK risk — yoğun önleme + sürekli gözlem"
 
            st.markdown(
                f"<div style='background:#1e2736;border-radius:8px;padding:16px;margin-top:8px;'>"
                f"<span style='font-size:2rem;font-weight:bold;color:{mo_renk}'>{mo_toplam}</span>"
                f"<span style='color:#b0bec5;'> / 125 puan</span><br>"
                f"<span style='color:{mo_renk};font-size:0.9rem'>{mo_yorum}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
 
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
 
# ── Klinik Rapor ──────────────────────────────────────────────
 
st.markdown("### 📄 Yapay Zeka Destekli Klinik Öneri Raporu")
st.caption(
    "CARS™ algoritması + Beers/STOPP kural motoru. "
    "RAG-Grounded Inference — yalnızca doğrulanmış kaynaklara dayalı."
)
 
html_report = build_clinical_report(patient, pim_hits, ddi_hits, fall_risk, cars)
st.markdown(f'<div class="report-box">{html_report}</div>', unsafe_allow_html=True)
 
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
 
# ── Karar Paneli ──────────────────────────────────────────────
 
st.markdown("### 🩺 Eczacı Karar Paneli")
st.caption("Tüm kararlar audit trail'e işlenir.")
 
b1, b2, b3, b4 = st.columns(4)
with b1:
    if st.button("✅ Reçeteyi Onayla", use_container_width=True):
        st.session_state.pharmacist_decision = "ONAYLANDI"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "ONAYLANDI",
            "cars_skor": cars["skor"],
        })
with b2:
    if st.button("🔄 Değişiklik İste", use_container_width=True):
        st.session_state.pharmacist_decision = "REVİZE"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "REVİZE",
            "cars_skor": cars["skor"],
        })
with b3:
    if st.button("📞 Prescriber'ı Ara", use_container_width=True):
        st.session_state.pharmacist_decision = "HEKIM_ARAND"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "HEKİM ARANACAK",
            "cars_skor": cars["skor"],
        })
with b4:
    if st.button("⛔ Reçeteyi Durdur", use_container_width=True):
        st.session_state.pharmacist_decision = "DURDURULDU"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "DURDURULDU",
            "cars_skor": cars["skor"],
        })
 
decision_map = {
    "ONAYLANDI":   ("success", "✅ Reçete **ONAYLANDI**. Risk kabul edildi."),
    "REVİZE":      ("warning", "🔄 Revizyon talep edildi. Prescriber'a bildirim gönderildi."),
    "HEKIM_ARAND": ("warning", "📞 Hekim acil bildirim protokolü başlatıldı."),
    "DURDURULDU":  ("error",   "⛔ Reçete **DURDURULDU**. Olay kaydı oluşturuldu."),
}
if st.session_state.pharmacist_decision:
    mtype, mtext = decision_map[st.session_state.pharmacist_decision]
    getattr(st, mtype)(mtext)
 
if st.session_state.decision_log:
    st.markdown("**📋 Oturum Karar Logu**")
    st.dataframe(
        pd.DataFrame(st.session_state.decision_log),
        use_container_width=True, hide_index=True,
        column_config={
            "zaman":     st.column_config.TextColumn("Zaman"),
            "hasta":     st.column_config.TextColumn("Hasta"),
            "karar":     st.column_config.TextColumn("Karar"),
            "cars_skor": st.column_config.NumberColumn("CARS™", format="%.1f"),
        },
    )
 
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
 
# ── Kohort Scatter ────────────────────────────────────────────
 
st.markdown("### 📊 Tüm Hasta Kohort Risk Haritası")
cohort    = build_cohort_summary(_get_active_db())
cohort_df = pd.DataFrame(cohort)
 
if not cohort_df.empty and pid in cohort_df["hasta_id"].values:
    sel_row = cohort_df[cohort_df["hasta_id"] == pid].iloc[0]
 
    fig_s = px.scatter(
        cohort_df, x="CARS™ Skoru", y="PDFI™ Skoru", size="PIM Sayısı",
        color="Risk Seviyesi",
        color_discrete_map={"KRİTİK":"#ef5350","YÜKSEK":"#ffa726",
                            "ORTA":"#ffee58","DÜŞÜK":"#66bb6a"},
        hover_name="Hasta",
        hover_data={"Yaş":True,"DDI Sayısı":True,"hasta_id":False},
        title="Kohort: CARS™ vs PDFI™ (Bubble = PIM Yükü)",
        size_max=35,
    )
    fig_s.add_annotation(
        x=sel_row["CARS™ Skoru"], y=sel_row["PDFI™ Skoru"],
        text=f"◀ {sel_row['Hasta']}",
        showarrow=True, arrowhead=2, arrowcolor="#ff9800",
        font=dict(color="#ff9800", size=11), bgcolor="#1e2736",
        bordercolor="#ff9800", borderwidth=1,
    )
    fig_s.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
        font_color="#b0bec5", height=380,
        margin=dict(t=50,b=30,l=30,r=30),
        xaxis=dict(title="CARS™ (0-100)", gridcolor="#263548", range=[0,105]),
        yaxis=dict(title="PDFI™ (0-100)", gridcolor="#263548", range=[0,105]),
        legend=dict(bgcolor="#1e2736", bordercolor="#263548", borderwidth=1),
    )
    st.plotly_chart(fig_s, use_container_width=True)
    crit_cnt = sum(1 for r in cohort if r["Risk Seviyesi"] == "KRİTİK")
    high_cnt = sum(1 for r in cohort if r["Risk Seviyesi"] == "YÜKSEK")
    st.caption(f"Kohort: {len(_get_active_db())} hasta · KRİTİK: {crit_cnt} · YÜKSEK: {high_cnt}")
 
st.markdown("""
<div class="footer-text">
  PharmaSentinel-RX v1.0.0 · Beers 2023 · STOPP/START v3 · FDA AI/ML SaMD
</div>""", unsafe_allow_html=True)
 
