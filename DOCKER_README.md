# Institution Resolver v3 - Docker Hızlı Başlangıç Kılavuzu

Bu proje, kurum adı eşleme sistemini (Elasticsearch + Ollama LLM + FastAPI & CLI) sıfır ortam kurulumuyla tek komutta çalıştırmanızı sağlar.

---

## 📋 Ön Gereksinimler

- Bilgisayarınızda **Docker** ve **Docker Compose** kurulu olmalıdır (Docker Desktop veya Docker Engine).
- Minimum **4 GB - 8 GB boş RAM** (Elasticsearch 2GB + PyTorch Embedding + Ollama için).
- Proje klasöründe `data/processed/` altında kanonik verilerin (`parent_canonical.jsonl`, `subunit_canonical.jsonl`, `embeddings.npz`) bulunduğundan emin olun.

---

## 🚀 1. Tek Komutla Başlatma

Projenin ana dizininde terminali açın ve şu komutu çalıştırın:

```bash
docker compose up -d --build
```

### ⏳ İlk Başlatmada Ne Olur? (Otomatik Kurulum)
Sistem ilk kez ayağa kalkarken arka planda:
1. **Elasticsearch** (Port: `9200`) ve **Ollama** (Port: `11434`) servislerini başlatır.
2. Elasticsearch'ün hazır olmasını bekler.
3. Elasticsearch'te kurum indeksi (`institutions_v1`) olmadığını tespit ederse, `data/processed/` altındaki tüm kurum verilerini ve **e5 embedding vektörlerini otomatik olarak indeksler** (bu işlem ilk seferde 1-2 dakika sürebilir).
4. Ollama LLM modelini (`gemma4:e4b`) otomatik indirir.
5. Web API sunucusunu (Port: `8000`) hazır hale getirir.

Logları anlık izlemek için:
```bash
docker compose logs -f api
```

---

## 🌐 2. Web Arayüzü ve API Kullanımı

Servisler ayağa kalktıktan sonra tarayıcınızdan şu adreslere erişebilirsiniz:

- **Web Arayüzü:** [http://localhost:8000](http://localhost:8000)  
  *(Tek kutu arama ve CSV yükleyerek toplu eşleme yapabilirsiniz)*
- **REST API Dokümantasyonu (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Sağlık Kontrolü:** [http://localhost:8000/health](http://localhost:8000/health)

---

## 💻 3. Terminalden CLI Kullanımı

Container çalışırken terminalinizden projenin CLI komutlarını doğrudan koşturabilirsiniz:

### Tekli Kurum Sorgusu:
```bash
# Sadece aday havuzu ve skorları
docker compose exec api inres3 match "gazi üniversitesi makine mühendisliği"

# Deterministik gate kararı
docker compose exec api inres3 gate "boğaziçi bilgisayar"

# Tam boru hattı (Gate + LLM Hakem nihai karar)
docker compose exec api inres3 decide "hacettepe tıp fakültesi"
```

### Toplu (Batch) Eşleme:
```bash
# CSV dosyasından toplu çözümleme
docker compose exec api inres3 batch data/jobs/ornek.csv --query-col raw_name --out output/sonuc.csv
```

---

## 🧪 4. Testleri Çalıştırma

Tüm birim testlerini container içinde koşturmak için:

```bash
docker compose exec api pytest
```

Canlı Elasticsearch ve Ollama entegrasyon testlerini koşturmak için:
```bash
docker compose exec api pytest -m integration
```

---

## 🛠 5. Geliştirme (Canlı Kod Güncelleme)

`src/`, `config/`, `tests/` klasörleri container'a canlı bağlıdır (volume mount). 
IDE'nizde (VS Code, PyCharm vb.) kodda veya ayarlarda yapacağınız değişiklikler **container'ı yeniden build etmenize gerek kalmadan anında geçerli olur**.

---

## 🛑 6. Servisleri Durdurma

Servisleri durdurmak için:
```bash
docker compose down
```

*Not: Veritabanı ve modeller Docker volume'lerinde (`esdata`, `ollama_data`, `hf_cache`) saklandığı için sonraki `docker compose up` çalıştırmalarınızda sistem saniyeler içinde anında açılacaktır.*
