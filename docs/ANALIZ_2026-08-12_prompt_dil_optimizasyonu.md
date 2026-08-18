# LLM Prompt Analizi: Dil Optimizasyonu (Türkçe vs İngilizce)

## 1. Mevcut Durum — Prompt Anatomisi

Projede LLM'e giden **tek prompt** var: [`prompt.py`](file:///Users/mscn/Desktop/institution_resolver_v3/src/institution_resolver_v3/judge/prompt.py) içindeki `build_prompt()`.

### Prompt Bileşimi (ölçülen, [optimizasyon raporu](file:///Users/mscn/Desktop/institution_resolver_v3/docs/RAPOR_2026-08-07_optimizasyon.md) §2):

| Bileşen | Pay | Dil |
|---|---|---|
| **Sabit talimat bloğu** | **%56** (~1.600 token) | 🔴 Tamamen Türkçe |
| Parent adayları | %18 | Türkçe etiketler + Türkçe/İngilizce veri |
| Subunit adayları | %17,5 | Türkçe etiketler + Türkçe/İngilizce veri |
| Sorgu + hipotezler | %8,5 | Karışık (kullanıcı verisi) |

### Darboğaz Kanıtı (aynı rapor):

- Toplam sürenin **%62'si LLM**
- LLM süresinin **%85'i prompt işleme** (prompt_eval), %13 üretim (eval)
- Donanım tavanı: **232 token/s** (Apple M4, gemma4:e4b)
- **Tek kaldıraç: gönderilen token sayısı**

---

## 2. Analiz: Türkçe Prompt Neden Daha Pahalı?

### 2.1 Token Sayısı Farkı

Gemma tokenizer'ı (SentencePiece tabanlı) **İngilizce-ağırlıklı** eğitilmiştir. Türkçe metin tokenize edildiğinde:

- Türkçe'ye özgü karakterler (`ş`, `ğ`, `ı`, `ö`, `ü`, `ç`, `İ`) genellikle **multi-byte** ve tokenizer bunları tanımadığı için **daha fazla token'a böler**
- Türkçe'nin ek yapısı (bağlaçlar, çekim ekleri) İngilizce'ye kıyasla **daha uzun kelimeler** üretir: `"eşleştirilecek"` vs `"to match"`, `"değiştirilmedi"` vs `"unmodified"`
- Aynı anlam İngilizce'de daha az token'la ifade edilir

**Somut örnek — sabit talimat bloğunun ilk cümlesi:**

| Dil | Metin | Tahmini token |
|---|---|---|
| TR | `Görev: serbest metin bir kurum ifadesini KATALOG'daki doğru kayıtla eşleştir.` | ~25-30 |
| EN | `Task: match a free-text institution mention to the correct catalog record.` | ~14-16 |

→ Aynı anlam, **~%40-50 daha az token** İngilizce'de.

### 2.2 Model Performansı

Gemma 4 (E2B/E4B) **İngilizce-baskın** bir model:
- Eğitim verisinin büyük çoğunluğu İngilizce
- İngilizce talimatları daha iyi anlar, daha az "düşünme" gerektirir
- Türkçe talimatlar modelin "çeviri" yapmasını gerektiriyor — gizli maliyet

### 2.3 Aday Etiketleri (Prompt İçi)

[`prompt.py`](file:///Users/mscn/Desktop/institution_resolver_v3/src/institution_resolver_v3/judge/prompt.py#L36-L66) satırlarındaki formatlama fonksiyonları Türkçe etiketler kullanıyor:

```python
# Mevcut (Türkçe)
"tam_eşleşme=EVET"
"ülke=TR şehir=İstanbul"
"bm25=0.843  token_benzerlik=92.0  nitelik_çelişkisi=hayır"

# İngilizce alternatif
"exact_match=YES"
"country=TR city=Istanbul"
"bm25=0.843  token_sim=92.0  qualifier_conflict=no"
```

Bu etiketler her aday satırında **tekrarlanıyor** (5-10 parent + 5-10 subunit = 10-20 tekrar). Her bir Türkçe etiketteki extra token'lar çarpanla büyüyor.

---

## 3. Tahmini Kazanç

### 3.1 Token Tasarrufu

| Bileşen | Mevcut (TR) | İngilizce | Tasarruf |
|---|---|---|---|
| Sabit talimat (~%56) | ~1.600 token | ~960-1.100 token | **%30-40** |
| Aday etiketleri (~%35,5) | ~1.000 token | ~700-800 token | **%20-30** |
| **Toplam prompt** | ~2.800 token | ~1.900-2.200 token | **%20-32** |

### 3.2 Süre Kazancı

Prompt işleme sürenin %85'i ve prompt %20-32 kısalırsa:
- LLM süresi: **%17-27 azalma**
- Uçtan uca (LLM %62): **%10-17 azalma**
- 500 sorgu benchmark'ında (medyan 24,4s LLM): **~4-6.5 saniye/sorgu**

### 3.3 Doğruluk Etkisi

> [!IMPORTANT]
> Bu en kritik soru. Token/süre kazancı kesin görünüyor ama **doğruluk değişir mi?**

Olası **pozitif** etkiler:
- Model İngilizce talimatları daha iyi anlayabilir → daha az sema-dışı cevap
- Optimizasyon raporunda (§4.3): "kısa ve odaklı prompt'ta model daha emin" → B10'da %55 kısaltma kalibrasyonu İYİLEŞTİRDİ

Olası **negatif** etkiler:
- Aday verileri Türkçe (kurum adları: `HACETTEPE ÜNİVERSİTESİ`, `GERİATRİ BİLİM DALI`)
- İngilizce talimat + Türkçe veri karışımı modeli karıştırabilir
- Bazı kurallar Türkçe bağlam gerektiriyor (ör. nitelik çelişkisi)

---

## 4. Önerilen Test Planı

> [!WARNING]
> Hiçbir kodu değiştirmeden önce onayın gerekli.

### Adım 1: Token Sayısı Karşılaştırması (risk yok, salt ölçüm)
- Mevcut Türkçe prompt'u ve İngilizce çevirisini Gemma tokenizer ile tokenize et
- Gerçek token farkını ölç (tahmin değil, kesin sayı)
- Bir script yazıp 10-20 gerçek sorgu için iki dildeki prompt'ları oluşturup token sayısını karşılaştır

### Adım 2: A/B Testi (3 kademe — kademeli risk)

**Kademe A — Sadece etiketler İngilizce:**
- `tam_eşleşme` → `exact_match`, `ülke` → `country`, `nitelik_çelişkisi` → `qualifier_conflict` vb.
- En düşük risk: talimat kuralları Türkçe kalır, sadece yapısal etiketler değişir
- Tahmini tasarruf: ~%5-10

**Kademe B — Talimat bloğu İngilizce, etiketler İngilizce:**
- Tüm sabit talimat bloğu + etiketler İngilizce
- Schema örneği İngilizce
- Tahmini tasarruf: ~%25-35

**Kademe C — Her şey İngilizce (schema dahil):**
- `_SCHEMA_EXAMPLE` İngilizce
- JSON alan adları (`unit_phrase` zaten İngilizce, `verdict` zaten İngilizce)
- Tahmini tasarruf: ~%30-40

### Adım 3: Doğruluk Ölçümü
- Her kademe için **aynı 50+ sorgu seti** ile koşum
- Mevcut (Türkçe) sonuçlarla karşılaştırma: verdict uyumu, matched_id uyumu
- Regresyon analizi: hangi sorgularda karar değişti, değişim doğru mu yanlış mı

---

## 5. Ek Optimizasyon Fırsatları (Dil Dışı)

Prompt incelemesinde gördüğüm başka optimizasyon fırsatları:

### 5.1 Prompt Kısaltma (dil bağımsız)
Raporun kendisi söylüyor (§7, madde 9):
> *"1.600 token'lık sabit talimat bloğu tek tek olaylardan birikmiş; hiçbir kural 'token'ını hak ediyor mu' diye ölçülmemiş."*

Bazı talimatlar **gereksiz uzun** veya **tekrarlı**:
- `HİPOTEZ NOTU` bloğu (satır 92-99): 8 satır, ~200 token — daha kısa yazılabilir
- `TAM_EŞLEŞME NOTU` bloğu (satır 101-111): 11 satır, ~250 token — özü 2-3 cümle
- `KARAR KURALLARI` (satır 113-153): 40 satır, ~800 token — bazıları birleştirilebilir

### 5.2 Schema Örneği
[`_SCHEMA_EXAMPLE`](file:///Users/mscn/Desktop/institution_resolver_v3/src/institution_resolver_v3/judge/prompt.py#L29-L33) zaten constrained generation (`format_schema`) ile zorunlu tutuluyor — prompt'taki schema **örneği** gerçekten gerekli mi? Schema engine zaten çıktıyı zorluyorsa, prompt'taki örnek sadece "model şemayı daha iyi anlasın" diye. Test edilmeli.

---

## 6. Open Questions

> [!IMPORTANT]
> **Q1:** Token sayısını gerçek Gemma tokenizer ile ölçmek için bir script yazayım mı? (Kod değişikliği YOK, sadece ölçüm scripti)

> [!IMPORTANT]
> **Q2:** İngilizce prompt taslağı (Kademe B — tam talimat bloğu) hazırlayayım mı? (Sadece taslak, uygulamaya geçmeden önce incelemeniz için)

> [!IMPORTANT]
> **Q3:** Ölçüm karşılaştırmasını hangi sorgu setiyle yapalım? Mevcut `benchmark_500_sample.csv`'den bir alt küme mi, yoksa bilinen zor vakaları mı (Ege, Gazi, Tehran, Pecs gibi)?

> [!IMPORTANT]
> **Q4:** Kademe A (sadece etiketler) ile Kademe B (tam İngilizce) arasında hangisini önce deneyelim?
