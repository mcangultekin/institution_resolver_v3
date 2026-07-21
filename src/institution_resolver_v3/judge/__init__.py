"""LLM karar katmani: gri bandin nihai hakemi.

Tek cagri hem girdiyi parcalar (institution / unit / qualifier) hem karar verir.
Girdi: sorgu + parent top-5 + subunit top-10 (aday basina kompakt sinyal kirilimi).
Cikti: kisitli JSON (verdict = MATCH|NONE|AMBIGUOUS|NOT_APPLICABLE + id + reason).

Icerik:
- prompt.py     : kurallar (id yalniz listeden; qualifier celiskisi; parent-tutarlilik;
                  kisa-akronim -> AMBIGUOUS; kurum-degil -> NOT_INSTITUTION; ceviri esdegerligi)
- client.py     : LLM cagrisi + normalize-sorgu anahtarli cache + batch async
- validators.py : 3 kod-tarafi dogrulayici (halusinasyon id / qualifier / parent-tutarlilik)

Yetki asimetrisi (Ayrim 3, karar bekliyor): LLM serbestce DUSURUR; auto_match'e
terfi ancak deterministik kanitla birlikte. Dogrulayici ihlali -> her zaman review.
"""
