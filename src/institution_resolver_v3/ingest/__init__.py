"""Ham CSV -> kanonik kayit + korpus profili (offline).

Icerik:
- raw_loader.py   : data/raw/*.csv -> duz dict listesi (salt okuma, is mantigi YOK)
- canonicalize.py : P1-P8 donusumleri (aktif filtre, klon-merge, qualifier soyma,
                    kind_label ayristirma, zincirli-ad, ...) saf fonksiyonlar
- profile.py      : transform_report.json (her adimin once/sonra sayilari)

Kaynak dogrusu: docs/V3_VERI_PLANI.md. Ham CSV salt-okunurdur; tum duzeltmeler
kod + raporda gorunur, elle CSV duzenleme yok.
"""
