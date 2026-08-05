"""Sorgu-tarafi on isleme + qualifier cikarimi.

Belge-tarafi normalizasyon ES turkish analyzer'in isidir; bu modul degil.

Icerik (v2'den tasindi, test-kilitli):
- query_pipeline.py : turkish_lower (I/i tuzagi), locale_aware_lower (icerik-bazli),
                      strip_turkish_accents, gorunmez-karakter/noktalama temizligi,
                      normalize() (base + base_no_accent), expand_query_text()
- abbreviations.py  : veri-dogrulanmis kisaltma sozlugu (uni.->universitesi, PR.->PROGRAMI)
- qualifiers.py     : tezli/tezsiz/(YL)/(DR)/(IO)/derece cikarimi + celiski kurali
"""
