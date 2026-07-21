"""Institution Resolver v3.

Serbest metin kurum ifadesini kanonik parent + subunit kayitlarina cozer.
Aday uretimi Elasticsearch'te; nihai karar bir LLM hakem katmaninda.

Mimari akis (bkz. docs/V3_BASLANGIC_REHBERI.md):

    normalize -> ingest/canonicalize (offline)
    embedding -> elastic (index, offline)

    SORGU:
    normalize -> elastic.search (parent + subunit havuzlari, ham skorlar)
              -> retrieve.signals (aday basina sinyaller)
              -> gate (deterministik: kolay vakalar LLM'siz biter)
              -> judge (LLM: kalan gri bant, tek cagri parse+karar)
              -> decide (verdict -> auto_match / review / ambiguous / no_match)

Katman ayrimi kuraldir: retrieval yalniz ES'te; gate/judge/decide birbirine
sizmaz. v2 kodundan import EDILMEZ (kanitli parcalar buraya kopyalanir).
"""

__version__ = "0.1.0"
