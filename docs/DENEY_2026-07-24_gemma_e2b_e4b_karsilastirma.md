# DENEY 2026-07-24 — Gemma 4 E2B vs E4B karşılaştırması (F4 hakem katmanı)

Amaç: F4 hakem katmanında hangi Gemma 4 boyutunun (E2B ~5.1B / E4B ~8B) kullanılacağına karar vermek için `isimler_tekrarsız.csv` (v2 inbox) içinden seed=42 ile 5 kategoriye (kurum+birim / sadece kurum / kurum ortada / Türkçe / İngilizce) göre stratifiye 50 sorgu çekildi, aynı `resolve()` aday havuzu ile her iki modele de soruldu. Backend: Ollama (yerel, Apple M4/16GB), curated tag'ler `gemma4:e2b` / `gemma4:e4b` (HF'ten doğrudan import 400 hatası verdi, bkz. `judge/client.py` docstring'i).

## Özet

| | E2B (7.2GB) | E4B (9.6GB) |
|---|---|---|
| Geçerli çıktı (şema-uyumlu) | 44/50 | 38/50 |
| parent=auto_match | 43 | 36 |
| parent=review | 0 | 1 |
| parent=no_match | 1 | 1 |
| ort. çağrı süresi | 25.2s | 37.2s (%48 daha yavaş) |
| Kalan hata türü | 4 halüsinasyon-id, 1 yanlış-nesting, 1 eksik-id | 10 "verdict var, matched_id unutulmuş", 2 verdict alanına literal "null" |

**Şema düzeltmesi notu:** ilk turda E4B 24/50, E2B 6/50 hata veriyordu. Kök neden bulundu: E4B rakam-dizgesi id'leri ("101") JSON *sayı* olarak dönüyordu, E2B/E4B ikisi de bazen "eşleşme yok"u JSON `null` yerine literal `"null"` dizgesiyle ifade ediyordu — ikisi de MODEL hatası değil, bizim şema katılığımızdı. `judge/schema.py`'e `field_validator` eklenip (int→str coerce, "null"/"none" string→None) 30 hatalı hücre yeniden denendi: E4B 24→12'ye düştü. Yukarıdaki tablo DÜZELTME SONRASI hali.

## Anlaşma oranı ve kalite gözlemi

İkisi de geçerli çıktı verdiğinde parent kararı (verdict+id) **29/34 (%85)** örtüşüyor. Ama 5 anlaşmazlıktan biri öğretici — ham sayılarla ölçülemeyen bir kalite farkı gösteriyor:

> Sorgu: *"MPG Makine Prodüksiyon Grubu Makine İmalat San. Ve Tic. A.Ş"* (bir ŞİRKET adı, kataloğumuzda olmaması gereken bir şey)
> - **E2B:** `auto_match` → yanlış bir tekstil şirketine zorla eşleştirdi (aşırı-güvenli yanlış-pozitif — DURUM.md'nin endişe ettiği "pahalı yanlış auto_match" riski tam burada gerçekleşti)
> - **E4B:** `no_match` → "bu bir şirket/departman adı, katalog akademik kurumlar içeriyor" gerekçesiyle doğru reddetti

**Sonuç:** E2B daha hızlı ve şema-uyumu daha yüksek (küçük model daha "itaatkâr" formatlı çıktı üretiyor), ama en az bir açık örnekte E4B'nin muhakemesi daha isabetli. Sadece hız/format uyumuna bakıp E2B'yi seçmek riskli olabilir — **henüz nihai karar verilmedi**, daha fazla örnek/ground-truth karşılaştırması önerilir.

## Tüm 50 sorgu (ham sonuç)

| # | kategori | sorgu | E2B (parent/id \| subunit) | E4B (parent/id \| subunit) |
|---|---|---|---|---|
| 0 | both | Sakarya Üniversitesi,  İktisadi ve İdari Bilimler Fakültesi,  Kamu ... | auto_match/12 \| sub=auto_match/142403 | auto_match/12 \| sub=auto_match/142403 |
| 1 | both | Süleyman Demirel Üniversitesi, İİBF, Ticaret Hukuku Anabilim Dalı Ö... | auto_match/206 \| sub=auto_match/145928 | auto_match/206 \| sub=auto_match/146026 |
| 2 | both | Baskent University, Faculty of Medicine, Physical Medicine and Reha... | auto_match/191 \| sub=auto_match/95368 | auto_match/54701 \| sub=auto_match/95412 |
| 3 | both | Adana Alparslan Türkeş Science and Technology University, Faculty o... | auto_match/221 \| sub=auto_match/80172 | auto_match/221 \| sub=auto_match/80150 |
| 4 | both | Solhan sağlık hizmetleri meslek yüksekokulu | auto_match/143 \| sub=no_match/- | auto_match/377 \| sub=no_match/- |
| 5 | both | Yrd. Doç. Dr., Kırıkkale Üniversitesi İİBF Siyaset Bilimi ve Kamu Y... | auto_match/152 \| sub=auto_match/128822 | auto_match/152 \| sub=auto_match/128822 |
| 6 | both | Eskişehir Technical University, Faculty of sport Science | auto_match/362 \| sub=auto_match/65407 | auto_match/362 \| sub=auto_match/65407 |
| 7 | both | Istanbul University, Institute of Social Sciences/Faculty of Econom... | auto_match/66 \| sub=auto_match/121907 | auto_match/66 \| sub=review/121907 |
| 8 | both | Çankırı karatekin Üniversitesi İslami İlimler Fakültesi | auto_match/107 \| sub=auto_match/100723 | auto_match/107 \| sub=auto_match/100723 |
| 9 | both | Gazi Üniversitesi Endüstri Mühendisliği Bölümü | HATA: hakem parent icin havuzda olmayan id dondurdu: '152111' | auto_match/101 \| sub=auto_match/152111 |
| 10 | inst_only | Kartal Doctor Lütfi Kırdar Training and Research Hospital | auto_match/73966 \| sub=auto_match/49028 | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 11 | inst_only | Hürriyet İlokulu | auto_match/94417 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 12 | inst_only | Physiotherapy and Rehabilitation Application and Research Center, H... | auto_match/293 \| sub=auto_match/152844 | auto_match/293 \| sub=auto_match/152844 |
| 13 | inst_only | Federal University Of Agriculture,Abeokuta | auto_match/89918 \| sub=no_match/- | auto_match/89918 \| sub=no_match/- |
| 14 | inst_only | Federal university dutsinma, katsina state, nigeria | auto_match/25892 \| sub=no_match/- | auto_match/25892 \| sub=no_match/- |
| 15 | inst_only | Mizan-Tepi university | auto_match/60495 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 16 | inst_only | KUTAHYA HEALTH SCIENCE UNIVERSTY EVLIYA CELEBI EDUCATION RESEARCH H... | auto_match/357 \| sub=no_match/- | auto_match/357 \| sub=review/60790 |
| 17 | inst_only | Medstar Antalya Hastanesi, İç Hastalıkları, Tıbbi Onkoloji | auto_match/23271 \| sub=auto_match/66637 | review/23271 \| sub=auto_match/66637 |
| 18 | inst_only | Georgetown University, School of Foreign Service | auto_match/104832 \| sub=no_match/- | auto_match/104832 \| sub=no_match/- |
| 19 | inst_only | Imam Al-kadhum College (IKC),Iraq | auto_match/24377 \| sub=no_match/- | auto_match/65601 \| sub=no_match/- |
| 20 | mid | Isparta Uygulamalı Bilimler Üniversitesi Keçiborlu Meslek Yüksekoku... | auto_match/204 \| sub=auto_match/65875 | auto_match/204 \| sub=auto_match/65877 |
| 21 | mid | ResearchCenter for Biotechnology - Indonesian Institute of Sciences | auto_match/91880 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 22 | mid | Necmettin Erbakan Üniversitesi Diş Hekimliği Fakültesi, Ağız, Diş v... | auto_match/213 \| sub=auto_match/157963 | auto_match/213 \| sub=review/157950 |
| 23 | mid | Kadirli State Hospital, Department of Neurology,  Osmaniye,Turkey | HATA: hakem subunit icin havuzda olmayan id dondurdu: '101200' | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 24 | mid | Gazi Yaşargil Eğitim ve Araştırma Hastanesi, Patoloji Kliniği, Diya... | auto_match/62262 \| sub=auto_match/151910 | auto_match/62262 \| sub=auto_match/49024 |
| 25 | mid | Ondokuz Mayıs Üniv. Bafra Meslek Yüksekokulu-Samsun | auto_match/192 \| sub=auto_match/138099 | auto_match/192 \| sub=auto_match/138098 |
| 26 | mid | Ankara Hacı Bayram Veli Üniversitesi - Ankara | auto_match/301 \| sub=no_match/- | auto_match/301 \| sub=no_match/- |
| 27 | mid | TÜBİTAK Ulusal Metroloji Enstitüsü, Gebze, Kocaeli | auto_match/53723 \| sub=auto_match/42176 | auto_match/53723 \| sub=no_match/- |
| 28 | mid | AKI'S POONA COLLEGE OF ARTS SCIENCE AND COMMERCE PUNE | auto_match/77612 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 2 validation errors for JudgeResult |
| 29 | mid | BULENT ECEVIT UNIVERSITY, FACULTY OF SCIENCE AND LETTERS, DEPARTMEN... | auto_match/80 \| sub=auto_match/76794 | auto_match/80 \| sub=auto_match/76794 |
| 30 | tr | ESKİŞEHİR OSMANGAZİ UNİVERSİTY, SCHOOL OF MEDICINE, DEPARTMENT OF S... | auto_match/30 \| sub=auto_match/108639 | auto_match/30 \| sub=auto_match/108814 |
| 31 | tr | TC MİLLİ EĞİTİM BAKANLIĞI KIRŞEHİR | auto_match/10740 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 32 | tr | ESKİŞEHİR OSMANGAZİ ÜNİVERSİTESİ, MÜHENDİSLİK-MİMARLIK FAKÜLTESİ, M... | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult | auto_match/30 \| sub=auto_match/108795 |
| 33 | tr | MPG Makine Prodüksiyon Grubu Makine İmalat San. Ve Tic. A.Ş | auto_match/92108 \| sub=no_match/- | no_match/- \| sub=no_match/- |
| 34 | tr | BALIKESİR üNİVERSİTESİ | auto_match/53 \| sub=no_match/- | auto_match/53 \| sub=— |
| 35 | tr | BARTIN ÜNİVERSİTESİ, EDEBİYAT FAKÜLTESİ, TÜRK DİLİ VE EDEBİYATI BÖL... | auto_match/243 \| sub=auto_match/94799 | auto_match/243 \| sub=auto_match/94794 |
| 36 | tr | KASTAMONU ÜNİVERSİTESİ, ORMAN FAKÜLTESİ, ORMAN ENDÜSTRİSİ MÜHENDİSL... | auto_match/138 \| sub=auto_match/127886 | auto_match/138 \| sub=auto_match/127886 |
| 37 | tr | Şehit Ahmet Eyce Mesleki ve Teknik lisesi, | no_match/- \| sub=— | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 38 | tr | ATATÜRK ÜNİVERSİTESİ, FEN FAKÜLTESİ, ASTRONOMİ VE ASTROFİZİK BÖLÜMÜ | auto_match/299 \| sub=auto_match/91650 | auto_match/299 \| sub=auto_match/91650 |
| 39 | tr | Kırşehir Aile ve Sosyal Politikalar İl Müdürlüğü | auto_match/73966 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 40 | en | Provincial Directorate of National Education | auto_match/45734 \| sub=no_match/- | auto_match/45734 \| sub=no_match/- |
| 41 | en | dow international dental college | auto_match/24675 \| sub=no_match/- | HATA: hakem ciktisi semaya uymuyor: 2 validation errors for JudgeResult |
| 42 | en | HALDIA INSTITUTE OF DENTAL SCIENCE AND RESEARCH | HATA: hakem parent icin havuzda olmayan id dondurdu: '174663' | auto_match/36760 \| sub=no_match/- |
| 43 | en | University of Quebec in Outaouais, Photonics Research Center | auto_match/18582 \| sub=no_match/- | auto_match/18582 \| sub=auto_match/166915 |
| 44 | en | Cairo University, Faculty of Engineering | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult | auto_match/66607 \| sub=no_match/- |
| 45 | en | CUKUROVA UNIVERSITY, FACULTY OF DENTISTRY, DENTISTRY PR. | auto_match/196 \| sub=auto_match/101772 | auto_match/196 \| sub=auto_match/101772 |
| 46 | en | BEZMI ALEM FOUNDATION UNIVERSITY, SCHOOL OF MEDICINE, DEPARTMENT OF... | auto_match/122 \| sub=auto_match/154320 | auto_match/122 \| sub=auto_match/154320 |
| 47 | en | Department of Textile and Garment Engineering, Hawassa University I... | HATA: hakem subunit icin havuzda olmayan id dondurdu: '62214' | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 48 | en | Dayanand Medical College and Hospital | auto_match/3542 \| sub=— | HATA: hakem ciktisi semaya uymuyor: 1 validation error for JudgeResult |
| 49 | en | Department of Physical Medicine and Rehabilitation, Gazi University... | auto_match/101 \| sub=auto_match/152102 | auto_match/101 \| sub=review/152142 |

Ham veri (tam reasoning metinleri dahil): `/private/tmp/claude-501/.../scratchpad/results_50.jsonl` (oturuma özel, kalıcı değil) — bu rapor kalıcı özet.
