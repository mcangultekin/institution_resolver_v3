"""Gate katmani - LLM'siz deterministik triyaj.

Asama 1 (su an): girdiyi (resolve sonucunu) guven-tabanli bir kovaya atar -
tek cevap + hakemle ayni dilde verdict (auto_match/review/ambiguous/no_match).
Ayrinti + skorlama gerekcesi: `gate.gate` modul docstring'i.

Sonraki asamalar (henuz tasarlanmadi): "review" kovasindan hakem/LLM'e devir,
esiklerin gold setiyle kalibrasyonu.
"""

from institution_resolver_v3.gate.gate import (
    GateDecision,
    GateResult,
    gate,
    score_candidate,
)

__all__ = ["GateDecision", "GateResult", "gate", "score_candidate"]
