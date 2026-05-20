bash

cat > /mnt/user-data/outputs/1_Hasta_Analizi.py << 'ENDOFFILE'
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
    PATIENTS_DB,
    RiskLevel,
    Patient,
    Medication,
    get_patient,
    get_patient_options,
)

logger = logging.getLogger(__name__)

# ── Session State ────────────────────────────────────────────

DEFAULTS = {
    "selected_patient_id": 1001,
    "analysis_triggered":  False,
    "pharmacist_decision": None,
    "report_generated":    False,
    "decision_log":        [],
    "risk_filter":         ["KR\u0130T\u0130K", "Y\u00dcKSEK", "ORTA", "D\u00dc\u015e\u00dcK"],
    "show_ddi_heatmap":    True,
    "show_cars_radar":     True,
    "show_fall_chart":     True,
    "ek_hastalar":         [],
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Tum hasta listesi ─────────────────────────────────────────

tum_hastalar = PATIENTS_DB + st.session_state.ek_hastalar

# ── Sidebar ───────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### Hasta Secimi")

    secenekler = {
        f"{p.hasta_id} - {p.ad_soyad} ({p.yas} yas)": p.hasta_id
        for p in tum_hastalar
    }
    sec_label = st.selectbox("Hasta", list(secenekler.keys()), label_visibility="collapsed")
    st.session_state.selected_patient_id = secenekler[sec_label]

    st.markdown("---")
    st.markdown("### Risk Filtresi")
    st.session_state.risk_filter = st.multiselect(
        "Seviye",
        ["KR\u0130T\u0130K", "Y\u00dcKSEK", "ORTA", "D\u00dc\u015e\u00dcK"],
        default=st.session_state.risk_filter,
        label_visibility="collapsed",
    )

    st.session_state.show_ddi_heatmap = st.toggle("DDI Isi Haritasi", value=st.session_state.show_ddi_heatmap)
    st.session_state.show_cars_radar  = st.toggle("CARS Bilesen Grafigi", value=st.session_state.show_cars_radar)
    st.session_state.show_fall_chart  = st.toggle("Dusme Risk Grafigi", value=st.session_state.show_fall_chart)

    st.markdown("---")
    if st.button("Analiz Baslat", use_container_width=True, type="primary"):
        st.session_state.analysis_triggered = True
        st.session_state.pharmacist_decision = None
        st.session_state.report_generated = True

    # ── Yeni Hasta Formu ──────────────────────────────────────
    st.markdown("---")
    st.markdown("### Yeni Hasta Ekle")
    with st.expander("Hasta Formunu Ac"):
        f_ad       = st.text_input("Ad Soyad")
        f_yas      = st.number_input("Yas", min_value=18, max_value=110, value=70)
        f_cins     = st.selectbox("Cinsiyet", ["E", "K"])
        f_kilo     = st.number_input("Kilo (kg)", min_value=20.0, max_value=200.0, value=70.0)
        f_egfr     = st.number_input("eGFR (ml/dk)", min_value=0.0, max_value=200.0, value=60.0)
        f_albumin  = st.number_input("Albumin (g/dL)", min_value=0.0, max_value=10.0, value=4.0)
        f_charlson = st.number_input("Charlson Indeksi", min_value=0, max_value=37, value=0)
        f_morse    = st.number_input("Morse Dusme Skoru", min_value=0, max_value=125, value=20)
        f_tanilar  = st.text_input("Tanilar (virgülle ayir)", value="")
        f_alerjiler= st.text_input("Alerjiler (virgülle ayir)", value="")

        if st.button("Kaydet ve Ekle"):
            if not f_ad.strip():
                st.error("Ad soyad zorunludur.")
            else:
                yeni_id = 9000 + len(st.session_state.ek_hastalar)
                tani_listesi  = [t.strip() for t in f_tanilar.split(",")  if t.strip()]
                alerji_listesi= [a.strip() for a in f_alerjiler.split(",") if a.strip()]
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
                    st.success(f_ad.strip() + " basariyla eklendi!")
                    st.rerun()
                except Exception as e:
                    st.error("Hata: " + str(e))

# ── Aktif hasta ───────────────────────────────────────────────

tum_hastalar = PATIENTS_DB + st.session_state.ek_hastalar
patient = next((p for p in tum_hastalar if p.hasta_id == st.session_state.selected_patient_id), tum_hastalar[0])

# ── Yeni ilac ekleme (session state ile) ─────────────────────

ilac_listesi_mock = [
    {"isim": "Diazepam 5mg",     "atc": "N05BA01", "risk": FallRiskClass.CRITICAL},
    {"isim": "Midazolam 7.5mg",  "atc": "N05CD08", "risk": FallRiskClass.CRITICAL},
    {"isim": "Warfarin 5mg",     "atc": "B01AA03", "risk": FallRiskClass.CRITICAL},
    {"isim": "Digoksin 0.25mg",  "atc": "C01AA05", "risk": FallRiskClass.CRITICAL},
    {"isim": "Ketiyapin 25mg",   "atc": "N05AH03", "risk": FallRiskClass.CRITICAL},
    {"isim": "Furosemid 40mg",   "atc": "C03CA01", "risk": FallRiskClass.HIGH},
    {"isim": "Enalapril 10mg",   "atc": "C09AA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Ramipril 5mg",     "atc": "C09AA05", "risk": FallRiskClass.MODERATE},
    {"isim": "Metformin 500mg",  "atc": "A10BA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Metformin 1000mg", "atc": "A10BA02", "risk": FallRiskClass.MODERATE},
    {"isim": "Sertralin 50mg",   "atc": "N06AB06", "risk": FallRiskClass.MODERATE},
    {"isim": "Amlodipin 10mg",   "atc": "C08CA01", "risk": FallRiskClass.MODERATE},
    {"isim": "Aspirin 100mg",    "atc": "B01AC06", "risk": FallRiskClass.LOW},
    {"isim": "Simvastatin 40mg", "atc": "C10AA01", "risk": FallRiskClass.LOW},
    {"isim": "Parasetamol 500mg","atc": "N02BE01", "risk": FallRiskClass.LOW},
]

frekanslar = ["1x1", "2x1", "3x1", "gece 1x", "haftada 1x"]

ilac_key = f"ilaclar_{patient.hasta_id}"
if ilac_key not in st.session_state:
    st.session_state[ilac_key] = list(patient.aktif_ilaclar)

aktif_ilaclar = st.session_state[ilac_key]

# Patient nesnesini guncel ilaclarla yeniden olustur
patient = Patient(
    hasta_id=patient.hasta_id,
    ad_soyad=patient.ad_soyad,
    yas=patient.yas,
    cinsiyet=patient.cinsiyet,
    kilo_kg=patient.kilo_kg,
    egfr=patient.egfr,
    albumin=patient.albumin,
    charlson_index=patient.charlson_index,
    morse_fall=patient.morse_fall,
    kronik_hastaliklar=patient.kronik_hastaliklar,
    alerjiler=patient.alerjiler,
    aktif_ilaclar=aktif_ilaclar,
)

# ── Hesaplamalar ──────────────────────────────────────────────

pim_hits  = detect_pim(patient)
ddi_hits  = detect_ddi(patient)
fall_risk = calculate_fall_risk(patient)
cars      = calculate_cars_score(patient, pim_hits, ddi_hits, fall_risk)

rf    = st.session_state.risk_filter
pim_f = [p for p in pim_hits if p["siddet"] in rf]
ddi_f = [d for d in ddi_hits if d["siddet"] in rf]

# ── Baslik ────────────────────────────────────────────────────

st.title("Hasta Analiz Paneli")
st.caption("CARS - PDFI - PIM Tespiti - DDI Analizi - Klinik Karar Destek")

st.error(
    "DIKKAT: Egitim amacli prototip. "
    "Gercek klinik kararlarda eczaci ve hekim kontrolu sarttir."
)

# ── Hasta karti + metrikler ───────────────────────────────────

col_card, col_metrics = st.columns([1.2, 2.8])

with col_card:
    egfr_renk = "red" if patient.egfr < 45 else ("orange" if patient.egfr < 60 else "green")
    alb_renk  = "red" if patient.albumin < 3.5 else "green"
    st.markdown("**Hasta Profili**")
    st.markdown(f"Ad: **{patient.ad_soyad}**")
    st.markdown(f"ID: {patient.hasta_id} | Yas: {patient.yas} | Cinsiyet: {patient.cinsiyet}")
    st.markdown(f"eGFR: **{patient.egfr}** ml/dk")
    st.markdown(f"Albumin: **{patient.albumin}** g/dL")
    st.markdown(f"Charlson: **{patient.charlson_index}**")
    st.markdown(f"Morse: **{patient.morse_fall}**/125")
    st.markdown("**Tanilar:** " + ", ".join(patient.kronik_hastaliklar) if patient.kronik_hastaliklar else "Tani yok")
    st.markdown("**Alerjiler:** " + ", ".join(patient.alerjiler) if patient.alerjiler else "Alerji yok")
    st.caption(f"Son analiz: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

with col_metrics:
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("CARS Skoru", cars["skor"], help="0-100 arasi kompozit risk skoru")
    with m2:
        crit_pim = sum(1 for p in pim_hits if p["siddet"] == RiskLevel.CRITICAL)
        st.metric("PIM Tespit", len(pim_hits), delta=f"{crit_pim} kritik" if crit_pim else None, delta_color="inverse")
    with m3:
        crit_ddi = sum(1 for d in ddi_hits if d["siddet"] == RiskLevel.CRITICAL)
        st.metric("DDI Etkilesim", len(ddi_hits), delta=f"{crit_ddi} kritik" if crit_ddi else None, delta_color="inverse")
    with m4:
        st.metric("PDFI Skoru", fall_risk["skor"], help="Dusme risk skoru")

    poly = " - Polifarmasi tespit edildi (5+ ilac)!" if len(aktif_ilaclar) >= 5 else ""
    st.caption(
        f"{len(aktif_ilaclar)} aktif ilac analiz edildi.{poly} "
        f"CARS: {cars['skor']}/100 - Risk: {cars['seviye'].value}"
    )

st.markdown("---")

# ── Yeni ilac ekleme paneli ───────────────────────────────────

with st.expander("Recete Girisi - Yeni Ilac Ekle"):
    col_i1, col_i2, col_i3 = st.columns(3)
    with col_i1:
        sec_ilac = st.selectbox("Ilac Sec", [il["isim"] for il in ilac_listesi_mock])
    with col_i2:
        sec_doz = st.text_input("Doz (ornek: 5mg)", value="")
    with col_i3:
        sec_frek = st.selectbox("Frekans", frekanslar)

    if st.button("Ekle ve Analiz Et"):
        if not sec_doz.strip():
            st.warning("Doz alani bos birakilamaz.")
        else:
            bulunan = next((il for il in ilac_listesi_mock if il["isim"] == sec_ilac), None)
            if bulunan:
                yeni_ilac = Medication(
                    atc=bulunan["atc"],
                    isim=sec_ilac,
                    doz=sec_doz.strip(),
                    frekans=sec_frek,
                    fall_risk_class=bulunan["risk"],
                )
                st.session_state[ilac_key].append(yeni_ilac)
                st.success(sec_ilac + " eklendi!")
                st.rerun()

if aktif_ilaclar:
    st.markdown("**Aktif Ilac Listesi**")
    for idx, ilac in enumerate(aktif_ilaclar):
        col_il, col_sil = st.columns([5, 1])
        with col_il:
            st.markdown(
                f"**{ilac.isim}** | {ilac.doz} | {ilac.frekans} | "
                f"ATC: `{ilac.atc}` | Risk: {ilac.fall_risk_class.value}"
            )
        with col_sil:
            if st.button("Sil", key=f"sil_{patient.hasta_id}_{idx}"):
                st.session_state[ilac_key].pop(idx)
                st.rerun()

st.markdown("---")

# ── Grafikler ─────────────────────────────────────────────────

viz1, viz2 = st.columns(2)

with viz1:
    st.markdown("#### CARS Kompozit Risk Gostergesi")
    gauge_color = get_severity_color(cars["seviye"])
    fig_g = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=cars["skor"],
        delta={"reference": 50, "increasing": {"color": "#ef5350"}, "decreasing": {"color": "#66bb6a"}},
        number={"font": {"size": 48, "color": "#e3f2fd"}},
        gauge={
            "axis": {"range": [0, 100]},
            "bar":  {"color": gauge_color, "thickness": 0.25},
            "steps": [
                {"range": [0,  30], "color": "#1b3a1f"},
                {"range": [30, 50], "color": "#3a2f0a"},
                {"range": [50, 70], "color": "#3a1f0a"},
                {"range": [70,100], "color": "#3a0a0a"},
            ],
        },
        title={"text": f"Risk: {cars['seviye'].value}", "font": {"color": gauge_color, "size": 16}},
    ))
    fig_g.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#0f1117", height=280, margin=dict(t=40,b=10,l=20,r=20))
    st.plotly_chart(fig_g, use_container_width=True)

    if st.session_state.show_cars_radar and cars["bilesenler"]:
        comp_df = pd.DataFrame({
            "Bilesen": list(cars["bilesenler"].keys()),
            "Katki":   list(cars["bilesenler"].values()),
        })
        fig_c = px.bar(comp_df, x="Katki", y="Bilesen", orientation="h",
                       color="Katki",
                       color_continuous_scale=[[0,"#2e7d32"],[0.4,"#f9a825"],[1,"#b71c1c"]],
                       title="CARS Bilesen Katki Dagilimi")
        fig_c.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=260, coloraxis_showscale=False,
                            margin=dict(t=40,b=10,l=10,r=10),
                            xaxis=dict(title="Katki Puani", gridcolor="#263548"),
                            yaxis=dict(title="", automargin=True))
        st.plotly_chart(fig_c, use_container_width=True)

with viz2:
    st.markdown("#### PDFI Dusme Risk Bilesenleri")
    if st.session_state.show_fall_chart:
        fall_df = pd.DataFrame({
            "Bilesen": list(fall_risk["bilesenler"].keys()),
            "Puan":    list(fall_risk["bilesenler"].values()),
        })
        fig_f = px.bar(fall_df, x="Bilesen", y="Puan", color="Puan",
                       color_continuous_scale=[[0,"#1b5e20"],[0.5,"#f57f17"],[1,"#b71c1c"]],
                       title=f"PDFI: {fall_risk['skor']}/100 ({fall_risk['seviye'].value})")
        fig_f.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=300, coloraxis_showscale=False,
                            margin=dict(t=50,b=20,l=20,r=20),
                            xaxis=dict(title="", tickangle=-20, automargin=True),
                            yaxis=dict(title="Puan", gridcolor="#263548", range=[0,35]))
        st.plotly_chart(fig_f, use_container_width=True)

    if st.session_state.show_ddi_heatmap and aktif_ilaclar:
        st.markdown("#### DDI Etkilesim Matrisi")
        drug_names = [d.isim.split()[0] for d in aktif_ilaclar]
        drug_atcs  = [d.atc for d in aktif_ilaclar]
        n = len(drug_names)
        matrix = np.zeros((n, n))
        sev_score = {RiskLevel.CRITICAL:3, RiskLevel.HIGH:2, RiskLevel.MODERATE:1, RiskLevel.LOW:0}
        for rule in ddi_hits:
            for i, ai in enumerate(drug_atcs):
                for j, aj in enumerate(drug_atcs):
                    if ai.startswith(rule["ilac_1_atc"][:7]) and aj.startswith(rule["ilac_2_atc"][:7]):
                        sv = sev_score.get(RiskLevel(rule["siddet"]), 0)
                        matrix[i][j] = sv
                        matrix[j][i] = sv
        labels = [["—","DUSUK","YUKSEK","KRITIK"][int(v)] for row in matrix for v in row]
        labels = [labels[i*n:(i+1)*n] for i in range(n)]
        fig_h = go.Figure(go.Heatmap(
            z=matrix, x=drug_names, y=drug_names,
            colorscale=[[0,"#1e2736"],[0.33,"#f9a825"],[0.66,"#ef5350"],[1,"#b71c1c"]],
            zmin=0, zmax=3, text=labels, texttemplate="%{text}",
            textfont={"size":9,"color":"#e3f2fd"}, showscale=False,
        ))
        fig_h.update_layout(paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
                            font_color="#b0bec5", height=260,
                            margin=dict(t=10,b=10,l=10,r=10),
                            xaxis=dict(tickangle=-30, tickfont=dict(size=9), automargin=True),
                            yaxis=dict(tickfont=dict(size=9), automargin=True))
        st.plotly_chart(fig_h, use_container_width=True)
        st.caption("Kirmizi hucre: KRITIK DDI - eczaci mudahalesi zorunlu.")

st.markdown("---")

# ── PIM / DDI / Ilac Sekmeleri ────────────────────────────────

tab_pim, tab_ddi, tab_drugs = st.tabs([
    f"PIM ({len(pim_f)})",
    f"DDI ({len(ddi_f)})",
    f"Ilaclar ({len(aktif_ilaclar)})",
])

with tab_pim:
    if not pim_f:
        st.success("Secili risk filtrelerine gore PIM tespit edilmedi.")
    for hit in pim_f:
        with st.expander(f"{hit['ilac']} - {hit['kategori']} | {hit['siddet']}"):
            ca, cb = st.columns(2)
            with ca:
                st.markdown(f"**Kaynak:** {hit['kural_kaynagi']}")
                st.markdown(f"**Siddet:** {hit['siddet']}")
                st.markdown(f"**ATC:** `{hit['atc']}`")
            with cb:
                st.info(hit["gerekce"])
            st.success(hit["oneri"])
            st.caption(f"Referans: {hit['kaynak_url']}")

with tab_ddi:
    if not ddi_f:
        st.success("Secili risk filtrelerine gore DDI tespit edilmedi.")
    for rule in ddi_f:
        is_crit = rule["siddet"] == RiskLevel.CRITICAL
        with st.expander(f"{rule['ilac_1_adi']} x {rule['ilac_2_adi']} | {rule['siddet']}", expanded=is_crit):
            cx, cy = st.columns(2)
            with cx:
                st.markdown(f"**Siddet:** {rule['siddet']}")
                st.markdown(f"**Kanit:** `{rule['kanit_duzeyi']}`")
                st.info(rule["mekanizma"])
            with cy:
                if is_crit:
                    st.error(rule["klinik_sonuc"])
                else:
                    st.warning(rule["klinik_sonuc"])
            st.success(rule["yonetim"])

with tab_drugs:
    if not aktif_ilaclar:
        st.info("Bu hasta icin henuz ilac eklenmemistir.")
    icons = {FallRiskClass.CRITICAL:"Kritik", FallRiskClass.HIGH:"Yuksek",
             FallRiskClass.MODERATE:"Orta", FallRiskClass.LOW:"Dusuk"}
    for drug in aktif_ilaclar:
        st.markdown(
            f"**{drug.isim}** | Doz: `{drug.doz}` | Frekans: `{drug.frekans}` | "
            f"ATC: `{drug.atc}` | Dusme Riski: {icons.get(drug.fall_risk_class, '?')}"
        )

st.markdown("---")

# ── Klinik Rapor ──────────────────────────────────────────────

st.markdown("### Yapay Zeka Destekli Klinik Oneri Raporu")
st.caption("CARS algoritmasi + Beers/STOPP kural motoru. RAG-Grounded Inference.")

html_report = build_clinical_report(patient, pim_hits, ddi_hits, fall_risk, cars)
st.markdown(f'<div style="background:#12202f;border:1px solid #1565c0;border-radius:10px;padding:22px;color:#cfd8dc;font-size:.9rem;line-height:1.8">{html_report}</div>', unsafe_allow_html=True)

st.markdown("---")

# ── Karar Paneli ──────────────────────────────────────────────

st.markdown("### Eczaci Karar Paneli")
st.caption("Tum kararlar audit trail'e islenir.")

b1, b2, b3, b4 = st.columns(4)
with b1:
    if st.button("Receteyi Onayla", use_container_width=True):
        st.session_state.pharmacist_decision = "ONAYLANDI"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "ONAYLANDI", "cars_skor": cars["skor"],
        })
with b2:
    if st.button("Degisiklik Iste", use_container_width=True):
        st.session_state.pharmacist_decision = "REVIZE"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "REVIZE", "cars_skor": cars["skor"],
        })
with b3:
    if st.button("Prescriber'i Ara", use_container_width=True):
        st.session_state.pharmacist_decision = "HEKIM_ARAND"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "HEKIM ARANACAK", "cars_skor": cars["skor"],
        })
with b4:
    if st.button("Receteyi Durdur", use_container_width=True):
        st.session_state.pharmacist_decision = "DURDURULDU"
        st.session_state.decision_log.append({
            "zaman": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "hasta": patient.ad_soyad, "karar": "DURDURULDU", "cars_skor": cars["skor"],
        })

decision_map = {
    "ONAYLANDI":   ("success", "Recete ONAYLANDI. Risk kabul edildi."),
    "REVIZE":      ("warning", "Revizyon talep edildi."),
    "HEKIM_ARAND": ("warning", "Hekim acil bildirim protokolu baslatildi."),
    "DURDURULDU":  ("error",   "Recete DURDURULDU. Olay kaydi olusturuldu."),
}
if st.session_state.pharmacist_decision:
    mtype, mtext = decision_map.get(st.session_state.pharmacist_decision, ("info",""))
    getattr(st, mtype)(mtext)

if st.session_state.decision_log:
    st.markdown("**Oturum Karar Logu**")
    st.dataframe(
        pd.DataFrame(st.session_state.decision_log),
        use_container_width=True, hide_index=True,
    )

st.markdown("---")

# ── Kohort ───────────────────────────────────────────────────

st.markdown("### Tum Hasta Kohort Risk Haritasi")
cohort = build_cohort_summary(tum_hastalar)
cohort_df = pd.DataFrame(cohort)

if not cohort_df.empty:
    sel_row = cohort_df[cohort_df["hasta_id"] == st.session_state.selected_patient_id]
    fig_s = px.scatter(
        cohort_df, x="CARS™ Skoru", y="PDFI™ Skoru", size="PIM Sayisi",
        color="Risk Seviyesi",
        color_discrete_map={"KRITIK":"#ef5350","YUKSEK":"#ffa726","ORTA":"#ffee58","DUSUK":"#66bb6a"},
        hover_name="Hasta",
        hover_data={"Yas":True,"DDI Sayisi":True,"hasta_id":False},
        title="Kohort: CARS vs PDFI (Bubble = PIM Yuku)",
        size_max=35,
    )
    if not sel_row.empty:
        row = sel_row.iloc[0]
        fig_s.add_annotation(
            x=row["CARS™ Skoru"], y=row["PDFI™ Skoru"],
            text=f"< {row['Hasta']}",
            showarrow=True, arrowhead=2, arrowcolor="#ff9800",
            font=dict(color="#ff9800", size=11), bgcolor="#1e2736",
            bordercolor="#ff9800", borderwidth=1,
        )
    fig_s.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
        font_color="#b0bec5", height=380,
        margin=dict(t=50,b=30,l=30,r=30),
        xaxis=dict(title="CARS (0-100)", gridcolor="#263548", range=[0,105]),
        yaxis=dict(title="PDFI (0-100)", gridcolor="#263548", range=[0,105]),
        legend=dict(bgcolor="#1e2736", bordercolor="#263548", borderwidth=1),
    )
    st.plotly_chart(fig_s, use_container_width=True)

st.caption("PharmaSentinel-RX v1.0.0 - Egitim Prototipi")
ENDOFFILE
echo "done"
