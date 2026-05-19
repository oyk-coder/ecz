# ============================================================
# clinical_logic.py — Klinik Hesaplama Motoru
# Saf Python fonksiyonları — sıfır Streamlit bağımlılığı
# ============================================================

from __future__ import annotations
import logging
from data_utils import (
    Patient, PIMRule, DDIRule, RiskLevel,
    FallRiskClass, PIM_RULES_DB, DDI_RULES_DB,
)

logger = logging.getLogger(__name__)

# ── Sabitler ─────────────────────────────────────────────────

EGFR_CRITICAL    = 45.0
EGFR_WARN        = 60.0
ALBUMIN_LOW      = 3.5
CHARLSON_HIGH    = 4
CHARLSON_MED     = 2
METFORMIN_EGFR   = 45.0

CARS_WEIGHTS: dict[str, float] = {
    "egfr":     0.20,
    "albumin":  0.10,
    "charlson": 0.15,
    "pim":      0.25,
    "ddi":      0.20,
    "fall":     0.10,
}

SEVERITY_ORDER = {
    RiskLevel.CRITICAL: 3,
    RiskLevel.HIGH:     2,
    RiskLevel.MODERATE: 1,
    RiskLevel.LOW:      0,
}


# ── Yardımcı ─────────────────────────────────────────────────

def _level_from_score(score: float) -> RiskLevel:
    if score >= 70: return RiskLevel.CRITICAL
    if score >= 50: return RiskLevel.HIGH
    if score >= 30: return RiskLevel.MODERATE
    return RiskLevel.LOW

def get_severity_color(level: RiskLevel | str) -> str:
    return {
        RiskLevel.CRITICAL: "#ef5350",
        RiskLevel.HIGH:     "#ffa726",
        RiskLevel.MODERATE: "#ffee58",
        RiskLevel.LOW:      "#66bb6a",
    }.get(RiskLevel(level), "#90caf9")

def get_badge_html(level: RiskLevel | str) -> str:
    css = {
        RiskLevel.CRITICAL: "badge-critical",
        RiskLevel.HIGH:     "badge-high",
        RiskLevel.MODERATE: "badge-moderate",
        RiskLevel.LOW:      "badge-low",
    }
    lv = RiskLevel(level)
    return f'<span class="{css.get(lv, "badge-low")}">{lv.value}</span>'


# ── PIM Tespiti ───────────────────────────────────────────────

def detect_pim(patient: Patient) -> list[dict]:
    """
    Hastanın ilaç listesini PIM kural veritabanıyla karşılaştırır.
    Beers 2023 ve STOPP/START v3 kriterlerini uygular.
    """
    hits: list[dict] = []
    for drug in patient.aktif_ilaclar:
        for rule in PIM_RULES_DB:
            if not drug.atc.startswith(rule.atc_prefix):
                continue
            # Metformin eGFR ≥ 45 → PIM değil
            if rule.atc_prefix == "A10BA" and patient.egfr >= METFORMIN_EGFR:
                logger.debug(
                    "Metformin PIM atlandı: eGFR=%.1f ≥ %.1f",
                    patient.egfr, METFORMIN_EGFR
                )
                continue
            logger.warning(
                "PIM tespit: %s — %s (şiddet: %s)",
                drug.isim, rule.kategori, rule.siddet
            )
            hits.append({"ilac": drug.isim, "atc": drug.atc, **rule.model_dump()})
    return hits


# ── DDI Tespiti ───────────────────────────────────────────────

def detect_ddi(patient: Patient) -> list[dict]:
    """
    Hastanın ilaç kombinasyonlarını DDI veritabanıyla karşılaştırır.
    """
    atc_list = [d.atc for d in patient.aktif_ilaclar]
    hits: list[dict] = []
    for rule in DDI_RULES_DB:
        has_1 = any(a.startswith(rule.ilac_1_atc[:7]) for a in atc_list)
        has_2 = any(a.startswith(rule.ilac_2_atc[:7]) for a in atc_list)
        if not (has_1 and has_2):
            continue
        logger.warning(
            "DDI tespit: %s × %s (şiddet: %s)",
            rule.ilac_1_adi, rule.ilac_2_adi, rule.siddet
        )
        hits.append(rule.model_dump())
    return hits


# ── Düşme Riski (PDFI™) ───────────────────────────────────────

def calculate_fall_risk(patient: Patient) -> dict:
    """
    PDFI™: Morse + ilaç sınıfı + renal + Charlson bileşenli düşme riski.

    Döndürür:
        skor      : float  — 0–100
        seviye    : RiskLevel
        bilesenler: dict[str, float]
    """
    morse_c    = min(patient.morse_fall / 125, 1.0) * 30
    crit_cnt   = sum(
        1 for d in patient.aktif_ilaclar
        if d.fall_risk_class == FallRiskClass.CRITICAL
    )
    high_cnt   = sum(
        1 for d in patient.aktif_ilaclar
        if d.fall_risk_class == FallRiskClass.HIGH
    )
    drug_c     = min(crit_cnt * 12 + high_cnt * 6, 35)
    renal_c    = max(0, (60 - patient.egfr) / 60) * 15
    charlson_c = min(patient.charlson_index / 10, 1.0) * 20
    score      = min(round(morse_c + drug_c + renal_c + charlson_c, 1), 100.0)
    level      = _level_from_score(score)

    logger.debug("PDFI skoru: %.1f (%s) — hasta %d",
                 score, level, patient.hasta_id)
    return {
        "skor":   score,
        "seviye": level,
        "bilesenler": {
            "Morse Skalası Katkısı":        round(morse_c,    1),
            "İlaç Risk Katkısı":            round(drug_c,     1),
            "Renal Fonksiyon Katkısı":      round(renal_c,    1),
            "Charlson Komorbidite Katkısı": round(charlson_c, 1),
        },
    }


# ── CARS™ Kompozit Risk Skoru ─────────────────────────────────

def calculate_cars_score(
    patient:   Patient,
    pim_hits:  list[dict],
    ddi_hits:  list[dict],
    fall_risk: dict,
) -> dict:
    """
    CARS™ — Konfounders-Aware Risk Skoru.

    R = Σ (w_i × x_i)  → normalize 0–100

    Ağırlıklar (CARS_WEIGHTS):
        egfr=0.20, albumin=0.10, charlson=0.15,
        pim=0.25,  ddi=0.20,     fall=0.10
    """
    x_egfr = (
        1.0 if patient.egfr < EGFR_CRITICAL else
        0.5 if patient.egfr < EGFR_WARN    else
        0.0
    )
    x_albumin  = 1.0 if patient.albumin < ALBUMIN_LOW else 0.0
    x_charlson = (
        1.0 if patient.charlson_index >= CHARLSON_HIGH else
        0.5 if patient.charlson_index >= CHARLSON_MED  else
        0.0
    )
    x_pim  = min(len(pim_hits) / 3.0, 1.0)
    x_ddi  = min(len(ddi_hits) / 2.0, 1.0)
    x_fall = fall_risk["skor"] / 100.0

    w = CARS_WEIGHTS
    raw = (
        w["egfr"]     * x_egfr     +
        w["albumin"]  * x_albumin  +
        w["charlson"] * x_charlson +
        w["pim"]      * x_pim      +
        w["ddi"]      * x_ddi      +
        w["fall"]     * x_fall
    )
    score = min(round(raw * 100, 1), 100.0)
    level = _level_from_score(score)

    components = {
        "eGFR Konfounderi":            round(w["egfr"]     * x_egfr     * 100, 1),
        "Albumin Konfounderi":         round(w["albumin"]  * x_albumin  * 100, 1),
        "Charlson Konfounderi":        round(w["charlson"] * x_charlson * 100, 1),
        "PIM Yükü":                    round(w["pim"]      * x_pim      * 100, 1),
        "DDI Yükü":                    round(w["ddi"]      * x_ddi      * 100, 1),
        "Düşme Risk Yükü":             round(w["fall"]     * x_fall     * 100, 1),
    }
    logger.debug("CARS skoru: %.1f (%s) — hasta %d",
                 score, level, patient.hasta_id)
    return {"skor": score, "seviye": level, "bilesenler": components}


# ── Dinamik Klinik Rapor ──────────────────────────────────────

def build_clinical_report(
    patient:   Patient,
    pim_hits:  list[dict],
    ddi_hits:  list[dict],
    fall_risk: dict,
    cars:      dict,
) -> str:
    """
    HTML formatında klinik öneri raporu döndürür.
    Saf Python — Streamlit bağımlılığı yok.
    """
    critical_ddis  = [d for d in ddi_hits if d["siddet"] == RiskLevel.CRITICAL]
    critical_pims  = [p for p in pim_hits if p["siddet"] == RiskLevel.CRITICAL]
    egfr_warn      = patient.egfr < EGFR_CRITICAL
    albumin_warn   = patient.albumin < ALBUMIN_LOW
    color          = get_severity_color(cars["seviye"])
    fall_color     = get_severity_color(fall_risk["seviye"])
    sections: list[str] = []

    # 1 — Yönetici Özeti
    critical_note = ""
    if critical_ddis or critical_pims:
        critical_note = (
            f"<br><br>⚠️ <strong>KRİTİK NOT:</strong> "
            f"{len(critical_ddis)} KRİTİK DDI ve {len(critical_pims)} KRİTİK PIM "
            f"tespit edilmiştir. Acil eczacı ve hekim değerlendirmesi gereklidir."
        )
    sections.append(f"""
<h5>📋 YÖNETİCİ ÖZETİ</h5>
<p>
<strong>{patient.ad_soyad}</strong> ({patient.yas} yaş, {patient.cinsiyet}) için
CARS™ algoritması <strong style="color:{color}">{cars['skor']}/100</strong>
kompozit risk skoru ile
<strong style="color:{color}">{cars['seviye'].value}</strong> risk sınıfı
belirledi. {len(patient.aktif_ilaclar)} aktif ilaç incelendi;
{len(pim_hits)} PIM ve {len(ddi_hits)} DDI saptandı.{critical_note}
</p>""")

    # 2 — Konfounders
    conf_items: list[str] = []
    if egfr_warn:
        conf_items.append(
            f"eGFR <strong>{patient.egfr} ml/dk/1.73m²</strong> "
            f"— renal doz ayarlaması zorunlu"
        )
    if albumin_warn:
        conf_items.append(
            f"Albumin <strong>{patient.albumin} g/dL</strong> "
            f"— hipoalbuminemi; protein bağlama kapasitesi azalmış"
        )
    if patient.charlson_index >= CHARLSON_HIGH:
        conf_items.append(
            f"Charlson İndeksi <strong>{patient.charlson_index}</strong> "
            f"— yüksek komorbidite yükü"
        )
    if conf_items:
        li_html = "".join(f"<li>{t}</li>" for t in conf_items)
        sections.append(f"""
<h5>🧬 KLİNİK KONFOUNDERLER</h5>
<ul style="color:#b0bec5">{li_html}</ul>""")

    # 3 — Kritik Müdahaleler
    if critical_pims or critical_ddis:
        items: list[str] = []
        for p in critical_pims:
            items.append(
                f"<li><strong>[PIM-KRİTİK]</strong> {p['ilac']}: {p['oneri']}</li>"
            )
        for d in critical_ddis:
            items.append(
                f"<li><strong>[DDI-KRİTİK]</strong> "
                f"{d['ilac_1_adi']} × {d['ilac_2_adi']}: {d['yonetim']}</li>"
            )
        sections.append(f"""
<h5>🚨 ÖNCELİKLİ MÜDAHALELER</h5>
<ul style="color:#ef9a9a">{''.join(items)}</ul>""")

    # 4 — Düşme Riski
    has_critical_drug = any(
        d.fall_risk_class == FallRiskClass.CRITICAL
        for d in patient.aktif_ilaclar
    )
    fall_note = (
        "KRİTİK sınıfta düşme riski taşıyan ilaç mevcut. "
        "Fizik tedavi ve düşme önleme protokolü başlatılması önerilir."
        if has_critical_drug
        else "Düşme riski mevcut; periyodik izlem önerilir."
    )
    sections.append(f"""
<h5>🚶 DÜŞME RİSKİ DEĞERLENDİRMESİ (PDFI™)</h5>
<p>
Morse skoru <strong>{patient.morse_fall}/125</strong> + ilaç profili →
PDFI™ <strong style="color:{fall_color}">{fall_risk['skor']}/100
({fall_risk['seviye'].value})</strong>. {fall_note}
</p>""")

    # 5 — İzlem Önerileri
    monitor: list[str] = []
    if egfr_warn:
        monitor.append(
            "<li>eGFR + kreatinin: <strong>2 haftada bir</strong></li>"
        )
    else:
        monitor.append("<li>eGFR izlemi: 3 ayda bir rutin</li>")
    if any("B01AA" in d.atc for d in patient.aktif_ilaclar):
        monitor.append(
            "<li>INR takibi: <strong>Haftalık</strong> "
            "(warfarin + aspirin kombinasyonu)</li>"
        )
    if any("C01AA" in d.atc for d in patient.aktif_ilaclar):
        monitor.append(
            "<li>Digoksin serum düzeyi: <strong>14 günde bir</strong></li>"
        )
    monitor += [
        "<li>Kapsamlı ilaç gözden geçirmesi: "
        "<strong>3 ayda bir</strong> eczacı liderliğinde</li>",
        "<li>Geriatri konsültasyonu: <strong>6 ayda bir</strong></li>",
    ]
    sections.append(f"""
<h5>📅 ÖNERİLEN İZLEM PROTOKOLÜ</h5>
<ul style="color:#b0bec5">{''.join(monitor)}</ul>""")

    return "".join(sections)


# ── Kohort Analizi ────────────────────────────────────────────

def build_cohort_summary(patients: list[Patient]) -> list[dict]:
    """
    Tüm hastalar için CARS™ + PDFI™ + PIM/DDI sayılarını hesaplar.
    UI katmanı için hazır dict listesi döndürür.
    """
    rows: list[dict] = []
    for p in patients:
        pim  = detect_pim(p)
        ddi  = detect_ddi(p)
        fall = calculate_fall_risk(p)
        cars = calculate_cars_score(p, pim, ddi, fall)
        rows.append({
            "Hasta":        f"{p.hasta_id}·{p.ad_soyad}",
            "hasta_id":     p.hasta_id,
            "Yaş":          p.yas,
            "CARS™ Skoru":  cars["skor"],
            "PDFI™ Skoru":  fall["skor"],
            "PIM Sayısı":   len(pim),
            "DDI Sayısı":   len(ddi),
            "Risk Seviyesi":cars["seviye"].value,
        })
    return rows
