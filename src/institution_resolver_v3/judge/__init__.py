"""LLM karar katmani (F4) - gri bandin nihai hakemi.

resolve() aday havuzunu + sinyalleri hakeme (Gemma 4, yerel/Ollama - Claude
KULLANILMIYOR, bkz. docs/DURUM.md maliyet karari) HAM METIN olarak sunar,
tek cagriyla PARENT ve SUBUNIT icin AYRI karar alir.

Icerik:
- client.py     : Ollama HTTP cagrisi (LlmClient Protocol - saglayicidan bagimsiz)
- candidates.py : ResolveResult -> hakem-hazir aday (country/city/kind_label/parent_name)
- prompt.py     : ham-metin prompt kurucu (on-yapilandirma yok, kosinus-bandi uyarisi)
- schema.py     : JudgeResult (ParentDecision + opsiyonel SubunitDecision)
- judge.py      : orkestrasyon + dogrulayici (JSON parse, sema, id-halusinasyonu)

verdict degerleri: auto_match / review / ambiguous / no_match (DURUM.md ile
birebir - eski "MATCH/NONE/AMBIGUOUS/NOT_APPLICABLE" taslagi burada terk
edildi, tutarlilik icin).

Yetki asimetrisi (docs/DURUM.md "Acik kararlar" - HALA KARARLASTIRILMADI):
LLM auto_match'e serbestce terfi edebilir mi, yoksa sadece deterministik
kanitla mi yukselir? Bu modul VARSAYIM YAPMAZ - ham JudgeResult'i dondurur,
karari decide/ katmani (henuz yazilmadi) verecek.
"""
