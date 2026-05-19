# ============================================================
# pages/2_Eczane_Operasyon.py — Eczane Operasyon Paneli
# ============================================================

import logging
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from data_utils import STOCK_DB, WORKFLOW_DB, StockItem, WorkflowItem

logger = logging.getLogger(__name__)

# ── Session State Güvenlik Ağı ────────────────────────────────

if "decision_log" not in st.session_state:
    st.session_state.decision_log = []

# ── Başlık ────────────────────────────────────────────────────

st.markdown("""
<div class="header-box">
  <p class="header-title">🏪 Eczane Operasyon Paneli</p>
  <p class="header-subtitle">
    Stok Yönetimi · Sipariş Tahmini · İş Akışı Otomasyonu
  </p>
</div>
""", unsafe_allow_html=True)

st.error(
    "🔴 **DİKKAT:** Eğitim amaçlı prototip. "
    "Tüm stok ve iş akışı verileri yapay (mock) veridir."
)

# ── Üst Metrik Özeti ──────────────────────────────────────────

total_items   = len(STOCK_DB)
critical_stok = sum(1 for s in STOCK_DB if s.kritik)
pending_wf    = sum(1 for w in WORKFLOW_DB if w.durum == "Bekliyor")
total_value   = sum(s.mevcut_stok * s.birim_fiyat for s in STOCK_DB)

m1, m2, m3, m4 = st.columns(4)
def _mbox(val, label, color="#e3f2fd"):
    return (
        f'<div class="metric-box">'
        f'<div class="metric-value" style="color:{color}">{val}</div>'
        f'<div class="metric-label">{label}</div></div>'
    )

with m1:
    st.markdown(_mbox(total_items, "Toplam İlaç Kalemi"), unsafe_allow_html=True)
with m2:
    st.markdown(_mbox(critical_stok, "Kritik Stok Uyarısı", "#ef5350"),
                unsafe_allow_html=True)
with m3:
    st.markdown(_mbox(pending_wf, "Bekleyen İş Akışı", "#ffa726"),
                unsafe_allow_html=True)
with m4:
    st.markdown(_mbox(f"₺{total_value:,.0f}", "Toplam Stok Değeri", "#66bb6a"),
                unsafe_allow_html=True)

st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

# ── Sekmeler ──────────────────────────────────────────────────

tab_stock, tab_forecast, tab_workflow = st.tabs([
    "📦 Stok Durumu",
    "📈 Tüketim Tahmini",
    "⚙️ İş Akışları",
])

# ── TAB 1: Stok Durumu ────────────────────────────────────────

with tab_stock:
    st.markdown("#### Mevcut Stok Durumu")
    st.caption("Kritik stok seviyesindeki ilaçlar kırmızı ile işaretlenmiştir.")

    # Sidebar filtresi
    show_critical_only = st.toggle("Yalnızca Kritik Stok Göster", value=False)
    filtered_stock = [s for s in STOCK_DB if (not show_critical_only or s.kritik)]

    # Stok bar grafiği
    stock_df = pd.DataFrame([{
        "İlaç":          s.ilac_adi,
        "Mevcut Stok":   s.mevcut_stok,
        "Min. Stok":     s.min_stok,
        "Kritik":        s.kritik,
    } for s in filtered_stock])

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=stock_df["İlaç"], y=stock_df["Mevcut Stok"],
        name="Mevcut Stok",
        marker_color=[
            "#ef5350" if row["Kritik"] else "#1e88e5"
            for _, row in stock_df.iterrows()
        ],
    ))
    fig_bar.add_trace(go.Scatter(
        x=stock_df["İlaç"], y=stock_df["Min. Stok"],
        mode="markers+lines", name="Min. Stok Eşiği",
        marker=dict(color="#ffa726", size=10, symbol="line-ew"),
        line=dict(color="#ffa726", dash="dash"),
    ))
    fig_bar.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
        font_color="#b0bec5", height=350,
        margin=dict(t=30,b=30,l=20,r=20),
        xaxis=dict(title="", tickangle=-25, automargin=True),
        yaxis=dict(title="Adet", gridcolor="#263548"),
        legend=dict(bgcolor="#1e2736"),
        barmode="group",
    )
    st.plotly_chart(fig_bar, use_container_width=True)

    # Stok tablosu
    table_data = []
    for s in filtered_stock:
        kalan_gun = int((s.mevcut_stok / s.aylik_tuketim) * 30) if s.aylik_tuketim else 999
        durum = "🔴 KRİTİK" if s.kritik else ("🟡 UYARI" if kalan_gun < 20 else "🟢 YETERLİ")
        table_data.append({
            "İlaç Adı":       s.ilac_adi,
            "ATC":            s.atc,
            "Mevcut":         s.mevcut_stok,
            "Min. Stok":      s.min_stok,
            "Aylık Tüketim":  s.aylik_tuketim,
            "Kalan Gün (≈)":  kalan_gun,
            "Birim Fiyat (₺)":s.birim_fiyat,
            "Son Sipariş":    s.son_siparis,
            "Durum":          durum,
        })
    st.dataframe(
        pd.DataFrame(table_data),
        use_container_width=True, hide_index=True,
    )

    # Kritik stok uyarıları
    critical_list = [s for s in STOCK_DB if s.kritik]
    if critical_list:
        st.markdown("---")
        st.markdown("#### ⚠️ Kritik Stok Uyarıları — Hızlı Sipariş Önerileri")
        for s in critical_list:
            order_qty = (s.min_stok * 3) - s.mevcut_stok
            st.warning(
                f"**{s.ilac_adi}** ({s.atc}) → Mevcut: **{s.mevcut_stok}** adet "
                f"| Min. Eşik: {s.min_stok} | "
                f"Önerilen Sipariş: **{order_qty} adet** "
                f"| Tahmini Maliyet: ₺{order_qty * s.birim_fiyat:,.2f}"
            )
            if st.button(f"📋 Sipariş Formu Oluştur — {s.ilac_adi.split()[0]}",
                         key=f"order_{s.atc}"):
                st.success(
                    f"✅ {s.ilac_adi} için {order_qty} adet sipariş formu "
                    f"oluşturuldu (simüle). Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                )
                logger.info("Sipariş formu simüle edildi: %s × %d adet", s.ilac_adi, order_qty)


# ── TAB 2: Tüketim Tahmini ────────────────────────────────────

with tab_forecast:
    st.markdown("#### Aylık Tüketim Trendi & 3 Aylık Projeksiyon")
    st.caption("Hareketli ortalama ve doğrusal trend modeli ile simüle edilmiş projeksiyon.")

    sel_drug = st.selectbox(
        "İlaç Seçin",
        options=[s.ilac_adi for s in STOCK_DB],
    )
    drug_data = next(s for s in STOCK_DB if s.ilac_adi == sel_drug)

    # Geçmiş 6 ay simüle veri
    np_seed = sum(ord(c) for c in sel_drug) % 100
    import numpy as np
    rng         = np.random.default_rng(np_seed)
    base        = drug_data.aylik_tuketim
    history     = [max(0, int(base + rng.integers(-base//4, base//4)))
                   for _ in range(6)]
    months_past = [
        (datetime.now() - timedelta(days=30 * (6 - i))).strftime("%b %Y")
        for i in range(6)
    ]

    # 3 aylık projeksiyon (trend bazlı)
    trend       = (history[-1] - history[0]) / 5
    projection  = [max(0, int(history[-1] + trend * (i + 1))) for i in range(3)]
    months_proj = [
        (datetime.now() + timedelta(days=30 * (i + 1))).strftime("%b %Y")
        for i in range(3)
    ]

    fig_fc = go.Figure()
    fig_fc.add_trace(go.Scatter(
        x=months_past, y=history,
        mode="lines+markers", name="Geçmiş Tüketim",
        line=dict(color="#1e88e5", width=2),
        marker=dict(size=8),
    ))
    fig_fc.add_trace(go.Scatter(
        x=[months_past[-1]] + months_proj,
        y=[history[-1]] + projection,
        mode="lines+markers", name="3 Aylık Projeksiyon",
        line=dict(color="#ffa726", width=2, dash="dash"),
        marker=dict(size=8, symbol="diamond"),
    ))
    fig_fc.add_hline(
        y=drug_data.min_stok, line_dash="dot",
        line_color="#ef5350", annotation_text="Min. Stok",
        annotation_font_color="#ef5350",
    )
    fig_fc.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
        font_color="#b0bec5", height=380,
        margin=dict(t=30,b=30,l=30,r=30),
        xaxis=dict(title="", gridcolor="#263548"),
        yaxis=dict(title="Adet", gridcolor="#263548"),
        legend=dict(bgcolor="#1e2736"),
        title=f"{sel_drug} — Tüketim Trendi & Projeksiyon",
    )
    st.plotly_chart(fig_fc, use_container_width=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Mevcut Stok", f"{drug_data.mevcut_stok} adet")
    with col_b:
        kalan = int((drug_data.mevcut_stok / drug_data.aylik_tuketim) * 30) \
                if drug_data.aylik_tuketim else 999
        st.metric("Tahmini Stok Ömrü", f"≈ {kalan} gün")
    with col_c:
        st.metric("Aylık Tüketim (Ort.)", f"{int(sum(history)/len(history))} adet")

    st.caption(
        f"Projeksiyon: {months_proj[0]} → {projection[0]} adet | "
        f"{months_proj[1]} → {projection[1]} adet | "
        f"{months_proj[2]} → {projection[2]} adet"
    )


# ── TAB 3: İş Akışları ───────────────────────────────────────

with tab_workflow:
    st.markdown("#### Aktif İş Akışları")
    st.caption("Bekleyen ve işlemdeki görevler öncelik sırasına göre listelenmektedir.")

    # Filtre
    durum_filter = st.multiselect(
        "Durum Filtresi",
        ["Bekliyor", "İşlemde", "Tamamlandı"],
        default=["Bekliyor", "İşlemde"],
    )
    oncelik_filter = st.multiselect(
        "Öncelik Filtresi",
        ["Yüksek", "Orta", "Düşük"],
        default=["Yüksek", "Orta", "Düşük"],
    )

    filtered_wf = [
        w for w in WORKFLOW_DB
        if w.durum in durum_filter and w.oncelik in oncelik_filter
    ]

    # Özet metrikler
    wc1, wc2, wc3 = st.columns(3)
    with wc1:
        bekliyor = sum(1 for w in filtered_wf if w.durum == "Bekliyor")
        st.metric("Bekliyor", bekliyor)
    with wc2:
        islemde = sum(1 for w in filtered_wf if w.durum == "İşlemde")
        st.metric("İşlemde", islemde)
    with wc3:
        tamamlandi = sum(1 for w in filtered_wf if w.durum == "Tamamlandı")
        st.metric("Tamamlandı", tamamlandi)

    st.markdown("---")

    # İş akışı kartları
    oncelik_colors = {"Yüksek": "#ef5350", "Orta": "#ffa726", "Düşük": "#66bb6a"}
    durum_icons    = {"Bekliyor": "🔴", "İşlemde": "🟡", "Tamamlandı": "🟢"}

    if not filtered_wf:
        st.info("Seçili filtrelere uygun iş akışı bulunamadı.")

    for wf in filtered_wf:
        icon   = durum_icons.get(wf.durum, "⚪")
        color  = oncelik_colors.get(wf.oncelik, "#90caf9")
        hasta  = f"👤 {wf.hasta_adi}" if wf.hasta_adi else "🏪 Eczane"
        with st.expander(
            f"{icon} [{wf.is_id}] {wf.baslik}  |  {wf.oncelik} Öncelik  |  {wf.durum}",
            expanded=(wf.durum == "Bekliyor" and wf.oncelik == "Yüksek")
        ):
            col_left, col_right = st.columns([2, 1])
            with col_left:
                st.markdown(f"**Açıklama:** {wf.aciklama}")
                st.markdown(f"**İlgili:** {hasta}")
            with col_right:
                st.markdown(
                    f"**Öncelik:** "
                    f"<span style='color:{color};font-weight:700'>{wf.oncelik}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown(f"**Durum:** {icon} {wf.durum}")

            # Aksiyon butonları
            ba, bb = st.columns(2)
            with ba:
                if wf.durum != "Tamamlandı":
                    if st.button("✅ Tamamlandı Olarak İşaretle",
                                 key=f"complete_{wf.is_id}"):
                        st.success(
                            f"'{wf.baslik}' tamamlandı olarak işaretlendi "
                            f"({datetime.now().strftime('%H:%M')})"
                        )
                        logger.info("İş akışı tamamlandı: %s", wf.is_id)
            with bb:
                if st.button("📋 Rapor Oluştur", key=f"report_{wf.is_id}"):
                    st.info(
                        f"'{wf.baslik}' için PDF rapor oluşturuldu (simüle). "
                        f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
                    )

    # Gantt tarzı durum dağılım grafiği
    st.markdown("---")
    st.markdown("#### İş Akışı Durum Dağılımı")
    dist_data = pd.DataFrame({
        "Durum":  [w.durum    for w in WORKFLOW_DB],
        "Öncelik":[w.oncelik  for w in WORKFLOW_DB],
        "Başlık": [w.baslik   for w in WORKFLOW_DB],
    })
    fig_wf = px.histogram(
        dist_data, x="Durum", color="Öncelik",
        color_discrete_map={"Yüksek":"#ef5350","Orta":"#ffa726","Düşük":"#66bb6a"},
        title="İş Akışı Durum & Öncelik Dağılımı",
        barmode="group",
    )
    fig_wf.update_layout(
        paper_bgcolor="#0f1117", plot_bgcolor="#1e2736",
        font_color="#b0bec5", height=300,
        margin=dict(t=40,b=20,l=20,r=20),
        xaxis=dict(title="", gridcolor="#263548"),
        yaxis=dict(title="Adet", gridcolor="#263548"),
        legend=dict(bgcolor="#1e2736"),
    )
    st.plotly_chart(fig_wf, use_container_width=True)

st.markdown("""
<div class="footer-text">
  PharmaSentinel-RX v1.0.0 · Eczane Operasyon Modülü ·
  Tüm veriler eğitim amaçlı mock veridir.
</div>""", unsafe_allow_html=True)
