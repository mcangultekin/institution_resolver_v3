"""Karar eslemesi: verdict + sinyaller -> nihai etiket.

Etiketler: auto_match / review / ambiguous / no_match (no_match birinci sinif).

- MATCH + deterministik kanit + dogrulayicilar temiz -> auto_match
- MATCH (kanit zayif) -> review (top-1 onerisiyle)
- AMBIGUOUS -> ambiguous ; NOT_INSTITUTION / NONE -> no_match
- Dogrulayici ihlali -> asla yukseltme, review'a indir

v2'nin esik ormani + calibrate_score BURADA YOK (LLM katmani onu geregsiz kildi).
"""
