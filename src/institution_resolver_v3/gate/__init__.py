"""Deterministik kapi: LLM'e gitmeyen kolay vakalar (maliyet + gecikme).

Amac: trafigin bir kismini LLM'siz bitirmek. Kurallar (docs/V3_BASLANGIC §4):
- Cop kapisi   : lexical_floor cok dusuk -> no_match (meslek unvani/adres/e-posta)
- Acik-ara     : token_set_ratio ~1 + bm25_norm=1 + marj yeterli + qualifier temiz
                 + kisa-akronim degil -> auto_match adayi
- Bos havuz    : iki havuz da 0 -> no_match

ONEMLI (Ayrim 4): esikler LLM davranisi GORULDUKTEN sonra, gercek etiketli sette
bir kez ayarlanir. Gate bir maliyet optimizasyonudur, kalite mekanizmasi degil.
"""
