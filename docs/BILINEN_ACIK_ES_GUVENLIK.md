# Bilinen açık: Elasticsearch kimlik doğrulaması kapalı (2026-08-18)

**Durum:** `docker/docker-compose.yml`'de `xpack.security.enabled=false` — ES 9200
portuna kimlik doğrulamasız erişiliyor. Compose dosyasının kendi yorumu bunu
zaten işaretliyor: *"gelistirme icin; uretimde acilmali"*.

**Neden şimdi açılmadı:** Gerçek anlamda kapatmak (`xpack.security.enabled=true`)
tek satırlık bir değişiklik değil — ES 8.x tek-node kurulumda otomatik
TLS+self-signed sertifika kurulumunu tetikliyor, bu da beraberinde getiriyor:
- `elastic/client.py`'deki `Elasticsearch(host)` çağrısına `basic_auth`/`api_key`
  ve sertifika güveni (`ca_certs` veya `verify_certs=False`) eklenmesi
- `docker-compose.yml`'deki healthcheck'in `http://` yerine `https://` +
  `--cacert` kullanması
- `config/default.yaml` / `config/docker.yaml`'a kimlik bilgisi alanları

Bu ortamda ES container'ı çalışmadığı için hiçbir adımı doğrulayamadım —
test edilmemiş bir "düzeltme" ile prod'u kırma riski almamak için bu işi
burada bırakıyorum.

**Prod'a geçmeden önce yapılması gereken:**
1. `docker-compose.yml`: `xpack.security.enabled=true`, `ELASTIC_PASSWORD` env
   değişkeni tanımla.
2. `elastic/client.py`: `Elasticsearch(host, basic_auth=(user, password), ...)`
   desteği ekle (config'ten okunacak `username`/`password` alanlarıyla).
3. Healthcheck'i ve `curl` çağrılarını `https://` + sertifika güvenine göre
   güncelle.
4. Gerçek bir Docker ortamında uçtan uca test et (bu repo'nun geliştirme
   ortamında ES çalışmıyor, doğrulama yapılamadı).

İlgili analiz: 2026-08-18 oturumunda API/Docker durumu incelenirken bulundu
(bkz. bu oturumun konuşma geçmişi — ayrıca `/batch/inventory` endpoint'i ve
`data/inventory` Docker volume'ü eksikliği de aynı analizde bulunup giderildi).
