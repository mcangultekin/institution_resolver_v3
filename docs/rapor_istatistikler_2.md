# RAPOR — Envanter: ilk (ham) ve son (`summary.csv`) istatistikler (2026-08-19)

## Özet

Elimizdeki 8,9 milyon satırlık ham veride her satırın hangi kuruma ait
olduğu bilgisi (parent) satırların yarısında, o kurumun hangi alt biriminden
(fakülte, hastane vb.) geldiği bilgisi ise satırların ancak beşte birinde
zaten yazılıydı. Geri kalanı boştu.

Bu boşlukları kapatmak için önce otomatik bir eşleştirme (gate+yapay zeka
hakemi) çalıştırdık, sonra da aynı kurumun adı veride başka bir yerde zaten
doluysa oradan kopyalayarak tamamladık. Sonunda kurum bilgisi hiçbir satırda
boş kalmadı; satırların **%92'sinde** kurum güvenle bir katalog kaydına
bağlandı, kalan **%8'i** ise (isim çok belirsiz/eksik olduğu için) hâlâ
çözülemedi. Alt birim tarafında iyileşme daha sınırlı oldu — bu beklenen bir
şey, çünkü bir kurumdan bahsedilirken çoğu zaman zaten belirli bir alt birim
söz konusu değil.

Bu sürecin adım adım nasıl işlediğine dair ayrıntılı rapor:
`docs/RAPOR_2026-08-19_envanter_boru_hatti_asama_istatistikleri.md`.
Bu dosya sadece başlangıç ve bitiş noktasını karşılaştırır.

Toplam satır her iki uçta da aynı: **8.920.512**.

---

## İLK HÂL — ham veri (`data/inventory/raw.csv` / `normalized.csv`)

Benzersiz `normalized_name`: **335.076**

### Parent

| | satır | oran |
|---|---:|---:|
| dolu | 4.596.039 | %51,5 |
| boş | 4.324.473 | %48,5 |

### Subunit

| | satır | oran |
|---|---:|---:|
| dolu | 1.687.783 | %18,9 |
| boş | 7.232.729 | %81,1 |

---

## SON HÂL — nihai özet (`data/inventory/summary.csv`)

### Parent (`parent_match`)

| | satır | oran |
|---|---:|---:|
| `match` | 8.185.464 | %91,8 |
| `review` | 307.647 | %3,4 |
| `no_match` | 327.864 | %3,7 |
| `judge_error` | 99.537 | %1,1 |

### Subunit (`subunit_match`)

| | satır | oran |
|---|---:|---:|
| `yok` (subunit yok, normal) | 5.410.872 | %60,7 |
| `match` | 388.947 | %4,4 |
| `review` | 2.293.739 | %25,7 |
| `no_match` | 727.417 | %8,2 |
| `judge_error` | 99.537 | %1,1 |

### Kaynak (`kaynak` — katalog referans tipi)

| | satır | oran |
|---|---:|---:|
| `yok` (YÖK) | 7.465.503 | %83,7 |
| `ror` | 719.961 | %8,1 |
| boş | 735.048 | %8,2 |

---

