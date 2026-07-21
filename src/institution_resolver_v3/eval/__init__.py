"""Degerlendirme: gercek set birincil, sentetik ikincil (v2'nin tersi).

Icerik:
- recall.py  : gercek sette recall@k olcumu (Ayrim 0 - darbogaz retrieval mi karar mi?
               KARAR katmanini optimize etmeden ONCE olculur)
- metrics.py : grup-farkindalikli metrikler (expected_id in merged_ids -> dogru);
               auto_match kesinligi, parent dogrulugu, KURUM_DEGIL yakalama,
               LLM'siz cozulen oran + $/1000 satir; bootstrap CI

Kabul dilimi hakem-modelinden BAGIMSIZ etiketlenir (Ayrim 6).
"""
