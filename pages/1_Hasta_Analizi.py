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
    PATIENTS_DB,
    RiskLevel,
    get_patient,
    get_patient_options,
)
 
logger = logging.getLogger(__name__)
 
# ── İlaç Kataloğu (Reçete Sekmesi için) ──────────────────────
 
ILAC_KATALOGU = [
    {"isim": "Warfarin",         "atc": "B01AA03", "risk": FallRiskClass.CRITICAL},
    {"isim": "Amlodipin",        "atc": "C08CA01", "risk": FallRiskClass.HIGH},
    {"isim": "Metformin",        "atc": "A10BA02", "risk": FallRiskClass.LOW},
    {"isim": "Enalapril",        "atc": "C09AA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Metoprolol",       "atc": "C07AB02", "risk": FallRiskClass.MODERATE},
    {"isim": "Furosemid",        "atc": "C03CA01", "risk": FallRiskClass.HIGH},
    {"isim": "Spironolakton",    "atc": "C03DA01", "risk": FallRiskClass.MODERATE},
    {"isim": "Atorvastatin",     "atc": "C10AA05", "risk": FallRiskClass.LOW},
    {"isim": "Omeprazol",        "atc": "A02BC01", "risk": FallRiskClass.LOW},
    {"isim": "Metilprednizolon", "atc": "H02AB04", "risk": FallRiskClass.MODERATE},
    {"isim": "Alprazolam",       "atc": "N05BA12", "risk": FallRiskClass.CRITICAL},
    {"isim": "Zolpidem",         "atc": "N05CF02", "risk": FallRiskClass.CRITICAL},
    {"isim": "Amitriptilin",     "atc": "N06AA09", "risk": FallRiskClass.CRITICAL},
    {"isim": "Haloperidol",      "atc": "N05AD01", "risk": FallRiskClass.HIGH},
    {"isim": "Tramadol",         "atc": "N02AX02", "risk": FallRiskClass.HIGH},
    {"isim": "Gabapentin",       "atc": "N03AX12", "risk": FallRiskClass.HIGH},
    {"isim": "Digoksin",         "atc": "C01AA05", "risk": FallRiskClass.HIGH},
    {"isim": "Levotiroksin",     "atc": "H03AA01", "risk": FallRiskClass.LOW},
    {"isim": "Metoklopramid",    "atc": "A03FA01", "risk": FallRiskClass.MODERATE},
    {"isim": "Karvedilol",       "atc": "C07AG02", "risk": FallRiskClass.HIGH},
]
 
FREKANSLAR = [
    "1x1", "2x1", "3x1", "4x1",
    "gece 1x", "sabah 1x",
    "haftada 1x", "haftada 2x",
    "ayda 1x", "gerektiğinde",
]
 
 
def _ilac_key(pid: int) -> str:
    """Her hasta için session_state'te ilaç listesi anahtarı."""
    return f"ilac_list_{pid}"
 
 
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
 
# ── Sidebar ───────────────────────────────────────────────────
 
with st.sidebar:
    st.markdown("### ⚕️ PharmaSentinel-RX")
    st.markdown("---")
 
    options = get_patient_options()
    sel_label = st.selectbox(
        "Hasta seçin", list(options.keys()), label_visibility="collapsed"
    )
    st.session_state.selected_patient_id = options[sel_label]
 
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
patient = get_patient(pid)
 
# Reçete sekmesinden eklenen ilaçlar session_state'te saklanır;
# henüz anahtar yoksa hastanın mevcut listesiyle başlat.
if _ilac_key(pid) not in st.session_state:
    st.session_state[_ilac_key(pid)] = list(patient.aktif_ilaclar)
 
# Analiz her zaman session_state'teki güncel ilaç listesiyle yapılır.
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
 
    # ── Charlson İndeksi Bilgi Kutusu ─────────────────────────
    with st.expander("ℹ️ Charlson İndeksi nasıl hesaplanır?"):
        st.markdown("""
**Charlson Komorbidite İndeksi** — her tanı için puan toplanır:
 
| Puan | Tanı / Durum |
|------|-------------|
| **1** | Miyokard enfarktüsü, KKY, periferik vasküler hastalık, serebrovasküler hastalık, demans, KOAH, bağ doku hastalığı, peptik ülser, hafif karaciğer hastalığı, diyabet (komplikasyonsuz) |
| **2** | Diyabet (organ hasarı ile), hemipleji, orta-ağır böbrek hastalığı, solid tümör, lösemi, lenfoma |
| **3** | Orta-ağır karaciğer hastalığı |
| **6** | Metastatik solid tümör, AIDS |
 
**10 yıllık tahmini mortalite:**
- 0 puan → %12
- 1-2 puan → %26
- 3-4 puan → %52
- ≥5 puan → %85
        """)
 
    # ── Morse Düşme Skoru Bilgi Kutusu ────────────────────────
    with st.expander("ℹ️ Morse Düşme Skoru nasıl hesaplanır?"):
        st.markdown("""
**Morse Düşme Ölçeği** — 6 kriter toplanır:
 
| Puan | Kriter |
|------|--------|
| **25** | Düşme öyküsü (son 3 ayda) |
| **15** | İkincil tanı varlığı |
| **15** | Yürüme yardımcısı kullanımı (koltuk değneği / walker) |
| **30** | IV / heparin kilidi |
| **10** | Yürüyüş / transfer bozukluğu |
| **15** | Mental durum bozukluğu |
 
**Risk sınıflandırması:**
- 0–24 → Düşük Risk
- 25–50 → Orta Risk
- ≥51 → Yüksek Risk
        """)
 
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
        drug_names = [d.isim.split()[0] for d in patient.aktif_ilaclar]
        drug_atcs  = [d.atc for d in patient.aktif_ilaclar]
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
 
# ── PIM / DDI / İlaçlar / Reçete Sekmeleri ───────────────────
 
tab_pim, tab_ddi, tab_drugs, tab_recete = st.tabs([
    f"🔴 PIM ({len(pim_f)})",
    f"🟠 DDI ({len(ddi_f)})",
    f"💊 İlaçlar ({len(patient.aktif_ilaclar)})",
    "📋 Reçete Girişi",
])
 
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
 
# ── Reçete Girişi Sekmesi ─────────────────────────────────────
 
with tab_recete:
    st.markdown("#### 📋 Reçete Girişi — İlaç Ekle")
    st.caption(
        "Etkin madde adı, dozaj şekli, miktar ve sıklık girerek hastanın "
        "ilaç listesine ekleyin. Analiz otomatik güncellenir."
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
        )
 
    # ── Satır 2: Dozaj şekli + miktar + birim ─────────────────
    col_r3, col_r4, col_r5 = st.columns([2, 1, 1])
    with col_r3:
        r_sekil = st.selectbox(
            "💉 Dozaj Şekli",
            ["Tablet", "Kapsül", "Şurup (ml)", "Ampul (mg)",
             "Patch", "İnhaler", "Damla", "Toz", "Diğer"],
            key="r_sekil",
        )
    with col_r4:
        r_miktar = st.number_input(
            "Miktar",
            min_value=0.0,
            max_value=10000.0,
            value=0.0,
            step=0.5,
            key="r_miktar",
            help="Sayısal miktar (örn: 500, 2.5)",
        )
    with col_r5:
        r_birim = st.selectbox(
            "Birim",
            ["mg", "mcg", "g", "ml", "IU", "mEq", "%"],
            key="r_birim",
        )
 
    # ── Satır 3: Sıklık + düşme riski ─────────────────────────
    col_r6, col_r7 = st.columns([2, 2])
    with col_r6:
        r_frek = st.selectbox(
            "🔁 Dozlama Sıklığı",
            FREKANSLAR,
            key="r_frek",
        )
    with col_r7:
        r_fallrisk = st.selectbox(
            "⚠️ Düşme Riski Sınıfı",
            ["KRİTİK", "YÜKSEK", "ORTA", "DÜŞÜK"],
            index=3,
            key="r_fallrisk",
            help="İlacın düşme riskine katkısını seçin",
        )
 
    _fallrisk_map = {
        "KRİTİK": FallRiskClass.CRITICAL,
        "YÜKSEK": FallRiskClass.HIGH,
        "ORTA":   FallRiskClass.MODERATE,
        "DÜŞÜK":  FallRiskClass.LOW,
    }
 
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
                    fall_risk_class=_fallrisk_map[r_fallrisk],
                )
                st.session_state[_ilac_key(pid)].append(yeni_ilac)
                st.success(f"✅ **{isim_str}** — {doz_str}, {r_frek} eklendi!")
                st.rerun()
 
    st.markdown("---")
    st.markdown("##### 📄 Mevcut Reçete")
 
    if not patient.aktif_ilaclar:
        st.info("ℹ️ Henüz ilaç eklenmedi.")
    else:
        icons_r = {
            FallRiskClass.CRITICAL: "🔴",
            FallRiskClass.HIGH:     "🟠",
            FallRiskClass.MODERATE: "🟡",
            FallRiskClass.LOW:      "🟢",
        }
        if len(patient.aktif_ilaclar) >= 5:
            st.warning(
                f"⚠️ **Polifarmasi:** {len(patient.aktif_ilaclar)} ilaç reçetede. "
                "Dikkatli değerlendirin."
            )
        for idx, drug in enumerate(patient.aktif_ilaclar):
            ico = icons_r.get(drug.fall_risk_class, "⚪")
            col_info, col_sil = st.columns([6, 1])
            with col_info:
                st.markdown(
                    f"{ico} **{drug.isim}** &nbsp;·&nbsp; "
                    f"`{drug.doz}` &nbsp;·&nbsp; `{drug.frekans}` &nbsp;·&nbsp; "
                    f"ATC: `{drug.atc}`"
                )
            with col_sil:
                if st.button("🗑️ Sil", key=f"rsil_{pid}_{idx}"):
                    st.session_state[_ilac_key(pid)].pop(idx)
                    st.rerun()
 
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
cohort    = build_cohort_summary(PATIENTS_DB)
cohort_df = pd.DataFrame(cohort)
sel_row   = cohort_df[cohort_df["hasta_id"] == st.session_state.selected_patient_id].iloc[0]
 
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
st.caption(f"Kohort: {len(PATIENTS_DB)} hasta · KRİTİK: {crit_cnt} · YÜKSEK: {high_cnt}")
 
st.markdown("""
<div class="footer-text">
  PharmaSentinel-RX v1.0.0 · Beers 2023 · STOPP/START v3 · FDA AI/ML SaMD
</div>""", unsafe_allow_html=True)
