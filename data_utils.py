# ============================================================
# data_utils.py — Mock Veri Katmanı & Pydantic Modelleri
# ============================================================

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator, Field


# ── Enums ────────────────────────────────────────────────────

class FallRiskClass(str, Enum):
    CRITICAL = "KRİTİK"
    HIGH     = "YÜKSEK"
    MODERATE = "ORTA"
    LOW      = "DÜŞÜK"

class RiskLevel(str, Enum):
    CRITICAL = "KRİTİK"
    HIGH     = "YÜKSEK"
    MODERATE = "ORTA"
    LOW      = "DÜŞÜK"


# ── Pydantic Modelleri ────────────────────────────────────────

class Medication(BaseModel):
    atc:             str
    isim:            str
    doz:             str
    frekans:         str
    fall_risk_class: FallRiskClass

class Patient(BaseModel):
    hasta_id:           int
    ad_soyad:           str
    yas:                int   = Field(..., ge=0,   le=120)
    cinsiyet:           str
    kilo_kg:            float = Field(..., gt=0)
    egfr:               float = Field(..., ge=0,   le=200)
    albumin:            float = Field(..., ge=0)
    charlson_index:     int   = Field(..., ge=0,   le=37)
    morse_fall:         int   = Field(..., ge=0,   le=125)
    kronik_hastaliklar: list[str]
    alerjiler:          list[str]
    aktif_ilaclar:      list[Medication]

    @field_validator("egfr")
    @classmethod
    def egfr_range(cls, v: float) -> float:
        if v < 0 or v > 200:
            raise ValueError("eGFR 0–200 aralığında olmalıdır.")
        return v

class PIMRule(BaseModel):
    atc_prefix:    str
    kural_kaynagi: str
    kategori:      str
    siddet:        RiskLevel
    gerekce:       str
    oneri:         str
    kaynak_url:    str

class DDIRule(BaseModel):
    ilac_1_atc:   str
    ilac_2_atc:   str
    ilac_1_adi:   str
    ilac_2_adi:   str
    mekanizma:    str
    klinik_sonuc: str
    siddet:       RiskLevel
    yonetim:      str
    kanit_duzeyi: str

class StockItem(BaseModel):
    ilac_adi:        str
    atc:             str
    mevcut_stok:     int
    min_stok:        int
    aylik_tuketim:   int
    birim_fiyat:     float
    son_siparis:     str
    kritik:          bool = False

class WorkflowItem(BaseModel):
    is_id:     str
    baslik:    str
    durum:     str          # "Bekliyor" | "İşlemde" | "Tamamlandı"
    oncelik:   str          # "Yüksek" | "Orta" | "Düşük"
    hasta_adi: Optional[str] = None
    aciklama:  str          = ""


# ── Hasta Mock Verisi ─────────────────────────────────────────

PATIENTS_DB: list[Patient] = [
    Patient(
        hasta_id=1001, ad_soyad="Mehmet Y.", yas=78,
        cinsiyet="E", kilo_kg=72.0, egfr=38.0, albumin=3.2,
        charlson_index=5, morse_fall=55,
        kronik_hastaliklar=["Kronik Böbrek Hastalığı Evre 3b",
                            "Tip 2 DM", "Hipertansiyon"],
        alerjiler=["Penisilin", "Sulfonamid"],
        aktif_ilaclar=[
            Medication(atc="N05BA01", isim="Diazepam 5mg",
                       doz="5mg",   frekans="2x1",
                       fall_risk_class=FallRiskClass.CRITICAL),
            Medication(atc="C09AA02", isim="Enalapril 10mg",
                       doz="10mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
            Medication(atc="B01AC06", isim="Aspirin 100mg",
                       doz="100mg", frekans="1x1",
                       fall_risk_class=FallRiskClass.LOW),
            Medication(atc="A10BA02", isim="Metformin 1000mg",
                       doz="1000mg",frekans="2x1",
                       fall_risk_class=FallRiskClass.MODERATE),
            Medication(atc="C03CA01", isim="Furosemid 40mg",
                       doz="40mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.HIGH),
            Medication(atc="N06AB06", isim="Sertralin 50mg",
                       doz="50mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
        ]
    ),
    Patient(
        hasta_id=1002, ad_soyad="Fatma K.", yas=84,
        cinsiyet="K", kilo_kg=58.0, egfr=22.0, albumin=2.9,
        charlson_index=7, morse_fall=75,
        kronik_hastaliklar=["Kronik Böbrek Hastalığı Evre 4",
                            "Kalp Yetmezliği (EF<%40)", "AF", "Osteoporoz"],
        alerjiler=["NSAID"],
        aktif_ilaclar=[
            Medication(atc="B01AA03", isim="Warfarin 5mg",
                       doz="5mg",   frekans="1x1",
                       fall_risk_class=FallRiskClass.CRITICAL),
            Medication(atc="C01AA05", isim="Digoksin 0.25mg",
                       doz="0.25mg",frekans="1x1",
                       fall_risk_class=FallRiskClass.CRITICAL),
            Medication(atc="N05AH03", isim="Ketiyapin 25mg",
                       doz="25mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.CRITICAL),
            Medication(atc="C03CA01", isim="Furosemid 80mg",
                       doz="80mg",  frekans="2x1",
                       fall_risk_class=FallRiskClass.HIGH),
            Medication(atc="M05BA04", isim="Alendronat 70mg",
                       doz="70mg",  frekans="haftada 1x",
                       fall_risk_class=FallRiskClass.LOW),
        ]
    ),
    Patient(
        hasta_id=1003, ad_soyad="Ali R.", yas=71,
        cinsiyet="E", kilo_kg=85.0, egfr=61.0, albumin=3.8,
        charlson_index=3, morse_fall=30,
        kronik_hastaliklar=["Hipertansiyon", "Dislipidemi"],
        alerjiler=[],
        aktif_ilaclar=[
            Medication(atc="C10AA01", isim="Simvastatin 40mg",
                       doz="40mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.LOW),
            Medication(atc="C09AA05", isim="Ramipril 5mg",
                       doz="5mg",   frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
            Medication(atc="C08CA01", isim="Amlodipin 10mg",
                       doz="10mg",  frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
        ]
    ),
    Patient(
        hasta_id=1004, ad_soyad="Hatice Ö.", yas=79,
        cinsiyet="K", kilo_kg=63.0, egfr=45.0, albumin=3.5,
        charlson_index=4, morse_fall=50,
        kronik_hastaliklar=["Tip 2 DM", "Hipertansiyon", "Anemi"],
        alerjiler=["Kodein"],
        aktif_ilaclar=[
            Medication(atc="A10BA02", isim="Metformin 500mg",
                       doz="500mg", frekans="3x1",
                       fall_risk_class=FallRiskClass.LOW),
            Medication(atc="N05CD08", isim="Midazolam 7.5mg",
                       doz="7.5mg", frekans="1x1",
                       fall_risk_class=FallRiskClass.CRITICAL),
            Medication(atc="C07AB07", isim="Bisoprolol 5mg",
                       doz="5mg",   frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
            Medication(atc="B03BA01", isim="Siyanokobalamin",
                       doz="1000mcg",frekans="haftada 1x",
                       fall_risk_class=FallRiskClass.LOW),
            Medication(atc="N02BE01", isim="Parasetamol 500mg",
                       doz="500mg", frekans="3x1",
                       fall_risk_class=FallRiskClass.LOW),
        ]
    ),
    Patient(
        hasta_id=1005, ad_soyad="Hüseyin T.", yas=67,
        cinsiyet="E", kilo_kg=90.0, egfr=72.0, albumin=4.0,
        charlson_index=2, morse_fall=20,
        kronik_hastaliklar=["Tip 2 DM"],
        alerjiler=[],
        aktif_ilaclar=[
            Medication(atc="A10BB01", isim="Glibenklamid 5mg",
                       doz="5mg",   frekans="1x1",
                       fall_risk_class=FallRiskClass.MODERATE),
            Medication(atc="A10BA02", isim="Metformin 1000mg",
                       doz="1000mg",frekans="2x1",
                       fall_risk_class=FallRiskClass.LOW),
        ]
    ),
]


# ── PIM Kural Veritabanı ──────────────────────────────────────

PIM_RULES_DB: list[PIMRule] = [
    PIMRule(
        atc_prefix="N05BA",
        kural_kaynagi="Beers 2023 — Kategori A",
        kategori="Benzodiazepin (Kısa Etkili)",
        siddet=RiskLevel.CRITICAL,
        gerekce="65 yaş üzeri hastalarda BDZ kullanımı; BT, "
                "motoraksiyel blok ve düşme-ilişkili yaralanma riskini artırır.",
        oneri="Non-farmakolojik uyku hijyeni protokolü başlatın. "
              "Zorunluysa düşük doz melatonin veya non-BDZ hipnotik değerlendirin.",
        kaynak_url="AGS Beers Criteria 2023 Update"
    ),
    PIMRule(
        atc_prefix="N05CD",
        kural_kaynagi="Beers 2023 — Kategori A",
        kategori="Benzodiazepin (Uzun Etkili)",
        siddet=RiskLevel.CRITICAL,
        gerekce="Uzun etkili BDZ'ler yaşlılarda birikim riski nedeniyle "
                "akut konfüzyon, düşme ve hipnotik bağımlılığa yol açar.",
        oneri="Kademeli doz azaltma (her 2 haftada %25 düşüş) protokolü başlatın. "
              "Psikiyatri konsültasyonu önerilir.",
        kaynak_url="AGS Beers Criteria 2023 Update"
    ),
    PIMRule(
        atc_prefix="N05AH",
        kural_kaynagi="STOPP v3 — Kriter B8",
        kategori="Atipik Antipsikotik",
        siddet=RiskLevel.HIGH,
        gerekce="Demans/deliryum dışı endikasyonda antipsikotik; QT uzaması, "
                "metabolik sendrom ve ekstrapiramidal yan etki riski taşır.",
        oneri="Psikiyatrik endikasyonu yeniden değerlendirin. "
              "Mümkünse kademeli kesim planı yapın.",
        kaynak_url="STOPP/START v3 — 2023"
    ),
    PIMRule(
        atc_prefix="C01AA",
        kural_kaynagi="Beers 2023 — Kategori B",
        kategori="Kardiyak Glikozid",
        siddet=RiskLevel.HIGH,
        gerekce="Digoksin düşük renal klirens kapasitesinde birikim riski taşır; "
                "toksik aralık dar (0.5–0.9 ng/mL).",
        oneri="eGFR < 30 ise kesinlikle kaçının. eGFR 30–60 arası günlük doz "
              "0.125 mg'ı geçmemeli. Digoksin düzeyi monitorize edilmeli.",
        kaynak_url="AGS Beers Criteria 2023 Update"
    ),
    PIMRule(
        atc_prefix="A10BA",
        kural_kaynagi="STOPP v3 — Kriter J1",
        kategori="Biguanid",
        siddet=RiskLevel.MODERATE,
        gerekce="Metformin eGFR < 30 ml/dk'da laktik asidoz riski nedeniyle "
                "kontrendikedir. eGFR 30–45 arası doz azaltımı gereklidir.",
        oneri="eGFR değerine göre doz titrasyonu yapın. eGFR < 30 ise kesin olarak kesin.",
        kaynak_url="STOPP/START v3 — 2023"
    ),
]


# ── DDI Kural Veritabanı ──────────────────────────────────────

DDI_RULES_DB: list[DDIRule] = [
    DDIRule(
        ilac_1_atc="B01AA03", ilac_2_atc="B01AC06",
        ilac_1_adi="Warfarin",  ilac_2_adi="Aspirin",
        mekanizma="Farmakodinamik sinerjizm — çift antitromboter etki",
        klinik_sonuc="Major kanama riski 3–4 kat artış. "
                     "GİS kanaması, intrakraniyal kanama.",
        siddet=RiskLevel.CRITICAL,
        yonetim="Kombinasyondan kaçının. Zorunluysa PPI ekleyin ve "
                "INR haftalık izleyin.",
        kanit_duzeyi="A"
    ),
    DDIRule(
        ilac_1_atc="C09AA02", ilac_2_atc="C03CA01",
        ilac_1_adi="Enalapril", ilac_2_adi="Furosemid",
        mekanizma="Farmakodinamik — ilk doz hipotansiyon riski",
        klinik_sonuc="Akut hipotansiyon, prerenal AKI, düşme riski artışı.",
        siddet=RiskLevel.HIGH,
        yonetim="ACE inhibitörü başlangıç dozu düşük tutun. "
                "Elektrolit ve kreatinin monitorizasyonu.",
        kanit_duzeyi="B"
    ),
    DDIRule(
        ilac_1_atc="N05BA01", ilac_2_atc="N06AB06",
        ilac_1_adi="Diazepam", ilac_2_adi="Sertralin",
        mekanizma="SSS depresyonu potansiyalizasyonu + CYP3A4 inhibisyonu",
        klinik_sonuc="Artmış sedasyon, psikomotor yavaşlama, "
                     "düşme ve solunum depresyonu riski.",
        siddet=RiskLevel.HIGH,
        yonetim="Diazepam dozunu %50 azaltın veya alternatif "
                "anksiyolitik değerlendirin.",
        kanit_duzeyi="B"
    ),
    DDIRule(
        ilac_1_atc="C01AA05", ilac_2_atc="C03CA01",
        ilac_1_adi="Digoksin", ilac_2_adi="Furosemid",
        mekanizma="Furosemid kaynaklı hipokalemi → digoksin toksisitesi",
        klinik_sonuc="Digoksin toksisitesi (bradikardi, AV blok, "
                     "ventriküler aritmiler).",
        siddet=RiskLevel.CRITICAL,
        yonetim="Potasyum 4.0–5.0 mEq/L aralığında tutun. "
                "Digoksin düzeyini haftalık izleyin.",
        kanit_duzeyi="A"
    ),
    DDIRule(
        ilac_1_atc="N05AH03", ilac_2_atc="N05CD08",
        ilac_1_adi="Ketiyapin", ilac_2_adi="Midazolam",
        mekanizma="Çift SSS depresyonu + QT uzaması sinerjizmi",
        klinik_sonuc="Aşırı sedasyon, solunum depresyonu, "
                     "torsade de pointes riski.",
        siddet=RiskLevel.CRITICAL,
        yonetim="Kombinasyondan kesinlikle kaçının. "
                "Her iki ilacı tek tek yeniden değerlendirin.",
        kanit_duzeyi="A"
    ),
]


# ── Stok Mock Verisi ──────────────────────────────────────────

STOCK_DB: list[StockItem] = [
    StockItem(ilac_adi="Metformin 1000mg", atc="A10BA02",
              mevcut_stok=450, min_stok=100, aylik_tuketim=200,
              birim_fiyat=12.50, son_siparis="2025-04-15", kritik=False),
    StockItem(ilac_adi="Warfarin 5mg",    atc="B01AA03",
              mevcut_stok=38,  min_stok=50,  aylik_tuketim=60,
              birim_fiyat=28.90, son_siparis="2025-03-28", kritik=True),
    StockItem(ilac_adi="Furosemid 40mg",  atc="C03CA01",
              mevcut_stok=210, min_stok=80,  aylik_tuketim=150,
              birim_fiyat=8.75, son_siparis="2025-04-20", kritik=False),
    StockItem(ilac_adi="Diazepam 5mg",    atc="N05BA01",
              mevcut_stok=22,  min_stok=30,  aylik_tuketim=45,
              birim_fiyat=15.40, son_siparis="2025-03-10", kritik=True),
    StockItem(ilac_adi="Digoksin 0.25mg", atc="C01AA05",
              mevcut_stok=95,  min_stok=40,  aylik_tuketim=55,
              birim_fiyat=22.30, son_siparis="2025-04-05", kritik=False),
    StockItem(ilac_adi="Amlodipin 10mg",  atc="C08CA01",
              mevcut_stok=320, min_stok=100, aylik_tuketim=180,
              birim_fiyat=9.80, son_siparis="2025-04-18", kritik=False),
    StockItem(ilac_adi="Sertralin 50mg",  atc="N06AB06",
              mevcut_stok=15,  min_stok=40,  aylik_tuketim=70,
              birim_fiyat=31.20, son_siparis="2025-02-28", kritik=True),
]


# ── İş Akışı Mock Verisi ──────────────────────────────────────

WORKFLOW_DB: list[WorkflowItem] = [
    WorkflowItem(is_id="WF-001", baslik="Warfarin INR Kontrolü",
                 durum="Bekliyor",   oncelik="Yüksek",
                 hasta_adi="Fatma K.",
                 aciklama="INR değeri kritik eşiğin üzerinde. Hekim bildirimi gerekli."),
    WorkflowItem(is_id="WF-002", baslik="Metformin Doz Revizyonu",
                 durum="İşlemde",    oncelik="Orta",
                 hasta_adi="Mehmet Y.",
                 aciklama="eGFR düşüşü nedeniyle doz azaltma protokolü başlatıldı."),
    WorkflowItem(is_id="WF-003", baslik="Stok Kritik Uyarısı — Sertralin",
                 durum="Bekliyor",   oncelik="Yüksek",
                 hasta_adi=None,
                 aciklama="Mevcut stok minimum seviyenin altına düştü."),
    WorkflowItem(is_id="WF-004", baslik="Diazepam PIM Bildirimi",
                 durum="Tamamlandı", oncelik="Yüksek",
                 hasta_adi="Mehmet Y.",
                 aciklama="Beers Kriterleri uyarısı hekim ile paylaşıldı."),
    WorkflowItem(is_id="WF-005", baslik="Aylık İlaç Mutabakatı",
                 durum="İşlemde",    oncelik="Düşük",
                 hasta_adi=None,
                 aciklama="Mayıs 2025 periyodik ilaç gözden geçirme raporu."),
]


# ── Yardımcı Erişim Fonksiyonları ────────────────────────────

def get_patient(patient_id: int) -> Patient | None:
    return next((p for p in PATIENTS_DB if p.hasta_id == patient_id), None)

def get_patient_options() -> dict[str, int]:
    return {
        f"{p.hasta_id} — {p.ad_soyad} ({p.yas} yaş)": p.hasta_id
        for p in PATIENTS_DB
    }
