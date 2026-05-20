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
 
# ── İlaç kataloğu (reçete girişi için) ───────────────────────
 
ILAC_KATALOGU = [
    {"isim": "Diazepam 5mg",      "atc": "N05BA01", "risk": FallRiskClass.CRITICAL},
    {"isim": "Midazolam 7.5mg",   "atc": "N05CD08", "risk": FallRiskClass.CRITICAL},
    {"isim": "Warfarin 5mg",      "atc": "B01AA03", "risk": FallRiskClass.CRITICAL},
    {"isim": "Digoksin 0.25mg",   "atc": "C01AA05", "risk": FallRiskClass.CRITICAL},
    {"isim": "Ketiyapin 25mg",    "atc": "N05AH03", "risk": FallRiskClass.CRITICAL},
    {"isim": "Furosemid 40mg",    "atc": "C03CA01", "risk": FallRiskClass.HIGH},
    {"isim": "Enalapril 10mg",    "atc": "C09AA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Ramipril 5mg",      "atc": "C09AA05", "risk": FallRiskClass.MODERATE},
    {"isim": "Metformin 500mg",   "atc": "A10BA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Metformin 1000mg",  "atc": "A10BA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Sertralin 50mg",    "atc": "N06AB06", "risk": FallRiskClass.MODERATE},
    {"isim": "Amlodipin 10mg",    "atc": "C08CA01", "risk": FallRiskClass.MODERATE},
    {"isim": "Aspirin 100mg",     "atc": "B01AC06", "risk": FallRiskClass.LOW},
    {"isim": "Simvastatin 40mg",  "atc": "C10AA01", "risk": FallRiskClass.LOW},
    {"isim": "Parasetamol 500mg", "atc": "N02BE01", "risk": FallRiskClass.LOW},
]
 
FREKANSLAR = ["1x1", "2x1", "3x1", "gece 1x", "haftada 1x"]
 
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
    "ek_hastalar":         [],
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v
 
# ── Yardımcı fonksiyonlar ─────────────────────────────────────
 
def tum_hastalar():
    return PATIENTS_DB + st.session_state.ek_hastalar
 
def get_hasta(hasta_id):
    return next((p for p in tum_hastalar() if p.hasta_id == hasta_id), tum_hastalar()[0])
 
def _ilac_key(hasta_id):
    return f"ilaclar_{hasta_id}"
 
def aktif_ilaclar(hasta_id):
    key = _ilac_key(hasta_id)
    if key not in st.session_state:
        st.session_state[key] = list(get_hasta(hasta_id).aktif_ilaclar)
    # dict olarak saklanmışsa Medication nesnesine çevir
    result = []
    for item in st.session_state[key]:
        if isinstance(item, dict):
            result.append(Medication(**item))
        elif isinstance(item, Medication):
            result.append(item)
    st.session_state[key] = result
    return result
 
# ── Sidebar ───────────────────────────────────────────────────
 
with st.sidebar:
    st.markdown("### ⚕️ PharmaSentinel-RX")
    st.markdown("---")
 
    hasta_secenekleri = {
        f"{p.hasta_id} — {p.ad_soyad} ({p.yas} yaş)": p.hasta_id
        for p in tum_hastalar()
    }
    sel_label = st.selectbox(
        "Hasta seçin", list(hasta_secenekleri.keys()), label_visibility="collapsed"
    )
    st.session_state.selected_patient_id = hasta_secenekleri[sel_label]
 
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
 
    # ── Yeni Hasta Ekleme ─────────────────────────────────────
    st.markdown("---")
    st.markdown("### 👤 Yeni Hasta Ekle")
    with st.expander("➕ Hasta Formu"):
        f_ad       = st.text_input("Ad Soyad", key="f_ad")
        f_yas      = st.number_input("Yaş", min_value=18, max_value=110, value=70, key="f_yas")
        f_cins     = st.selectbox("Cinsiyet", ["E", "K"], key="f_cins")
        f_kilo     = st.number_input("Kilo (kg)", min_value=20.0, max_value=200.0, value=70.0, key="f_kilo")
        f_egfr     = st.number_input("eGFR (ml/dk)", min_value=0.0, max_value=200.0, value=60.0, key="f_egfr")
        f_albumin  = st.number_input("Albumin (g/dL)", min_value=0.0, max_value=10.0, value=4.0, key="f_albumin")
        f_charlson = st.number_input("Charlson İndeksi", min_value=0, max_value=37, value=0, key="f_charlson")
        f_morse    = st.number_input("Morse Düşme Skoru", min_value=0, max_value=125, value=20, key="f_morse")
        f_tanilar  = st.text_input("Tanılar (virgülle ayır)", value="", key="f_tanilar")
        f_alerjiler = st.text_input("Alerjiler (virgülle ayır)", value="", key="f_alerjiler")
 
        if st.button("💾 Kaydet ve Ekle", key="hasta_ekle_btn"):
            if not f_ad.strip():
                st.error("Ad soyad zorunludur.")
            else:
                yeni_id = 9000 + len(st.session_state.ek_hastalar)
                tani_listesi   = [t.strip() for t in f_tanilar.split(",")  if t.strip()]
                alerji_listesi = [a.strip() for a in f_alerjiler.split(",") if a.strip()]
                try:
                    yeni_hasta = Patient(
                        hasta_id=yeni_id,
                        ad_soyad=f_ad.strip(),
                        yas=int(f_yas),
                        cinsiyet=f_cins,
                        kilo_kg=float(f_kilo),
                        egfr=float(f_egfr),
                        albumin=float(f_albumin),
                        charlson_index=int(f_charlson),
                        morse_fall=int(f_morse),
                        kronik_hastaliklar=tani_listesi,
                        alerjiler=alerji_listesi,
                        aktif_ilaclar=[],
                    )
                    st.session_state.ek_hastalar.append(yeni_hasta)
                    st.session_state.selected_patient_id = yeni_id
                    st.success(f"✅ {f_ad.strip()} eklendi!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hata: {e}")
 
# ── Aktif hasta + güncel ilaç listesi ────────────────────────
 
pid      = st.session_state.selected_patient_id
_base    = get_hasta(pid)
_ilaclar = aktif_ilaclar(pid)
 
# model_copy ile sadece aktif_ilaclar alanını güncelle (Pydantic v2)
patient  = _base.model_copy(update={"aktif_ilaclar": _ilaclar})
 
# ── Hesaplamalar ──────────────────────────────────────────────
 
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
 
# ── PIM / DDI / İlaç / Reçete Sekmeleri ──────────────────────
 
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
    icons = {FallRiskClass.CRITICAL: "🔴", FallRiskClass.HIGH: "🟠",
             FallRiskClass.MODERATE: "🟡", FallRiskClass.LOW: "🟢"}
    st.caption("Renk: 🔴 KRİTİK · 🟠 YÜKSEK · 🟡 ORTA · 🟢 DÜŞÜK düşme riski")
 
    if not patient.aktif_ilaclar:
        st.info("ℹ️ Bu hasta için henüz ilaç eklenmemiştir. 'Reçete Girişi' sekmesinden ekleyebilirsiniz.")
    else:
        for idx, drug in enumerate(patient.aktif_ilaclar):
            css = fc_colors.get(drug.fall_risk_class, "")
            ico = icons.get(drug.fall_risk_class, "⚪")
            col_drug, col_del = st.columns([6, 1])
            with col_drug:
                st.markdown(f"""
                <div class="drug-item {css}">
                  {ico} <strong>{drug.isim}</strong>
                  &nbsp;|&nbsp; Doz: <code>{drug.doz}</code>
                  &nbsp;|&nbsp; Frekans: <code>{drug.frekans}</code>
                  &nbsp;|&nbsp; ATC: <code>{drug.atc}</code>
                  &nbsp;|&nbsp; Düşme: <strong>{drug.fall_risk_class.value}</strong>
                </div>""", unsafe_allow_html=True)
            with col_del:
                if st.button("🗑️", key=f"del_{pid}_{idx}", help="İlacı listeden kaldır"):
                    st.session_state[_ilac_key(pid)].pop(idx)
                    st.rerun()
 
with tab_recete:
    st.markdown("#### 📋 Reçete Girişi — İlaç Ekle")
    st.caption("Seçilen hastanın aktif ilaç listesine yeni ilaç ekleyin. Analiz otomatik güncellenir.")
 
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        sec_ilac = st.selectbox(
            "💊 İlaç Seç",
            [il["isim"] for il in ILAC_KATALOGU],
            key="recete_ilac",
        )
    with col_r2:
        sec_doz = st.text_input(
            "📏 Doz (örn: 5mg, 10mg)",
            value="",
            key="recete_doz",
            placeholder="5mg",
        )
    with col_r3:
        sec_frek = st.selectbox(
            "🔁 Frekans",
            FREKANSLAR,
            key="recete_frek",
        )
 
    col_ekle, _ = st.columns([1, 3])
    with col_ekle:
        if st.button("➕ Ekle ve Analiz Et", use_container_width=True, type="primary"):
            if not sec_doz.strip():
                st.warning("⚠️ Doz alanı boş bırakılamaz.")
            else:
                bulunan = next((il for il in ILAC_KATALOGU if il["isim"] == sec_ilac), None)
                if bulunan:
                    yeni_ilac = Medication(
                        atc=bulunan["atc"],
                        isim=sec_ilac,
                        doz=sec_doz.strip(),
                        frekans=sec_frek,
                        fall_risk_class=bulunan["risk"],
                    )
                    st.session_state[_ilac_key(pid)].append(yeni_ilac)
                    st.success(f"✅ **{sec_ilac}** ({sec_doz.strip()}, {sec_frek}) eklendi!")
                    st.rerun()
 
    st.markdown("---")
    st.markdown("##### 📄 Mevcut Reçete")
 
    if not patient.aktif_ilaclar:
        st.info("ℹ️ Henüz ilaç eklenmedi.")
    else:
        icons_r = {FallRiskClass.CRITICAL: "🔴", FallRiskClass.HIGH: "🟠",
                   FallRiskClass.MODERATE: "🟡", FallRiskClass.LOW: "🟢"}
        if len(patient.aktif_ilaclar) >= 5:
            st.warning(f"⚠️ **Polifarmasi:** {len(patient.aktif_ilaclar)} ilaç reçetede. Dikkatli değerlendirin.")
 
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
st.caption("CARS™ algoritması + Beers/STOPP kural motoru. "
           "RAG-Grounded Inference — yalnızca doğrulanmış kaynaklara dayalı.")
 
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
cohort    = build_cohort_summary(tum_hastalar())
cohort_df = pd.DataFrame(cohort)
sel_rows  = cohort_df[cohort_df["hasta_id"] == st.session_state.selected_patient_id]
 
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
if not sel_rows.empty:
    row = sel_rows.iloc[0]
    fig_s.add_annotation(
        x=row["CARS™ Skoru"], y=row["PDFI™ Skoru"],
        text=f"◀ {row['Hasta']}",
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
 
tum = tum_hastalar()
crit_cnt = sum(1 for r in cohort if r["Risk Seviyesi"] == "KRİTİK")
high_cnt = sum(1 for r in cohort if r["Risk Seviyesi"] == "YÜKSEK")
st.caption(f"Kohort: {len(tum)} hasta · KRİTİK: {crit_cnt} · YÜKSEK: {high_cnt}")
 
st.markdown("""
<div class="footer-text">
  PharmaSentinel-RX v1.0.0 · Beers 2023 · STOPP/START v3 · FDA AI/ML SaMD
</div>""", unsafe_allow_html=True)
