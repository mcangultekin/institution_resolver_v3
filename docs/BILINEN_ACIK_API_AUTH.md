# Bilinen açık: API'de kimlik doğrulama / rate-limit / CORS yok (2026-08-18)

**Durum:** `api/app.py`'de hiçbir auth middleware'i, rate-limit'i veya CORS
ayarı yok. `/batch/*` endpoint'leri sınırsız CSV upload kabul ediyor (dosya
boyutu limiti de görülmedi).

**Neden şimdi eklenmedi:** API şu an iç kullanım için tasarlanmış gibi
duruyor — `docker/docker-compose.yml`'de aynı Docker ağı içinde ES/Ollama'yla
birlikte çalışıyor, dışarıya açık bir port/domain yok. Bu haliyle auth
katmanı gereksiz karmaşıklık olurdu.

**Servis dışarıya (internet veya farklı bir ağdan erişilebilir şekilde)
açılmadan önce eklenmesi gerekenler:**
1. Basit bir bariyer için: `X-API-Key` header kontrolü (env değişkeninden
   okunan sabit anahtar) — minimum, hızlı bir çözüm.
2. Gerçek çok-kullanıcılı bir servis olacaksa: JWT/OAuth gibi bir auth
   sistemi + `slowapi` gibi bir rate-limit katmanı + CORS ayarı (hangi
   origin'lere izin verileceği netleşmeden CORS'u genel açmamak gerekir).
3. `/batch/*` endpoint'lerine dosya boyutu limiti eklenmeli (şu an
   `_save_upload` sınırsız okuyor, `api/routers/batch.py`).

**Ne zaman gündeme gelmeli:** API dışarıya açılmadan (yeni bir deploy
hedefi, farklı bir ağdan erişim, halka açık bir uç nokta) önce.
