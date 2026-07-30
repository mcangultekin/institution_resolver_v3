"""TEK index mapping + Turkce analyzer konfigurasyonu.

v2'nin iki-index IDF zehirlenmesi (parent'ta nadir "fakultesi" suni-yuksek IDF
alip "ankara tip fakultesi"yi hastaneye goturuyordu) burada TEK korpus + sorgu
aninda `record_type` filtresiyle cozulur.

Analyzer'lar (belge-tarafi folding'i ES yapar; biz onden agresif normalize etmeyiz):
- turkish_analyzer : Turkce-dogru kucuk harf (I/i) + Turkce stopword
- ascii_analyzer   : + asciifolding (Turkce karaktersiz yazan kullanici)
- edge_analyzer    : + edge_ngram (onek/kismi eslesme)

dense_vector (768) F3 icin REZERVE; F1 lexical-only, populate edilmez.
"""

from __future__ import annotations

from typing import Any

EMBEDDING_DIM = 768


def build_index_settings() -> dict[str, Any]:
    return {
        "index": {
            "number_of_shards": 1,      # tek node dev; determinizm icin tek shard
            "number_of_replicas": 0,
        },
        "analysis": {
            "filter": {
                "turkish_lowercase": {"type": "lowercase", "language": "turkish"},
                "turkish_stop": {"type": "stop", "stopwords": "_turkish_"},
                "edge_ngram_filter": {"type": "edge_ngram", "min_gram": 2, "max_gram": 20},
            },
            "analyzer": {
                "turkish_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["apostrophe", "turkish_lowercase", "turkish_stop"],
                },
                "ascii_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["apostrophe", "turkish_lowercase", "asciifolding"],
                },
                "edge_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["apostrophe", "turkish_lowercase", "asciifolding", "edge_ngram_filter"],
                },
                # edge_ngram SADECE index tarafinda; sorgu tarafi ascii ile aranir
                "edge_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["apostrophe", "turkish_lowercase", "asciifolding"],
                },
            },
        },
    }


def _text_field() -> dict[str, Any]:
    """turkish ana alan + ascii/edge alt alanlari + keyword (tam eslesme)."""
    return {
        "type": "text",
        "analyzer": "turkish_analyzer",
        "fields": {
            "ascii": {"type": "text", "analyzer": "ascii_analyzer"},
            "edge": {
                "type": "text",
                "analyzer": "edge_analyzer",
                "search_analyzer": "edge_search_analyzer",
            },
            "keyword": {"type": "keyword", "ignore_above": 512},
        },
    }


def build_mapping() -> dict[str, Any]:
    return {
        "properties": {
            "id": {"type": "keyword"},
            "record_type": {"type": "keyword"},       # parent | subunit  (sorgu filtresi)
            "parent_id": {"type": "keyword"},
            "merged_ids": {"type": "keyword"},
            "name": _text_field(),
            "normalized_name": {"type": "keyword"},    # agresif-normalize, tam-eslesme kanali
            "aliases_text": {
                "type": "text",
                "analyzer": "turkish_analyzer",
                "fields": {"ascii": {"type": "text", "analyzer": "ascii_analyzer"}},
            },
            # Alias'larin AYRI liste hali - ARAMAYA KAPALI. Aramayi SUBUNIT'te
            # `aliases_text`, PARENT'ta nested `alias_variants` yapar (2026-07-30:
            # parent artik `aliases_text`i ARAMIYOR, asagi bkz.). Bu liste
            # decompose'un sinir skorunu her alias'a karsi TEK TEK (uzunluk-duyarli
            # fuzz.ratio) hesaplayabilmesi icin _source'ta tutulur.
            # Birlesik aliases_text'e karsi partial_ratio KULLANILMAZ: tek kelimelik
            # jenerik pencere ("üniversitesi") her birlesik metinde 100 bulur - yeni
            # bir cekim-merkezi dogurur (bkz. docs/DENEY_2026-07-23_parent_dogrulama.md).
            "aliases": {"type": "keyword", "index": False, "doc_values": False},
            # PARENT aramasinin TEK kanali (2026-07-29 eklendi, 2026-07-30'da
            # `name`/`aliases_text` cikarilinca tek kanal oldu). Her alias AYRI
            # bir nested belge -> her yazim KENDI alan-uzunlugu normuyla puanlanir.
            # Neden birlesik `aliases_text` yetmiyordu: BM25'in alan-uzunlugu
            # normu tek metne bakar, dolayisiyla 6 alias'li kurum 1 alias'li
            # kurumdan sistematik olarak dusuk puan aliyordu - kendi alias'iyla
            # aranan kurum havuza HIC giremeyebiliyordu. Nested + `score_mode:max`
            # ile kurumu EN IYI yazimi temsil eder, alias sayisi ceza olmaktan
            # cikar. Kanonik ad da bu havuzun bir uyesi (kayitlarin %100'unde
            # alias listesinde) - kanonik/alias ayrimi YOK, gerekce ve olcumler
            # search.py `_alias_variants_clause` docstring'inde.
            # SADECE PARENT belgelerinde uretilir (document.py); subunit kapsam
            # disi ve `aliases_text` ile aranmaya devam eder - o yuzden
            # `aliases_text` HER IKI record_type'ta doldurulmaya devam eder
            # (parent'lardan kaldirilirsa subunit'in BM25 alan istatistikleri,
            # dolayisiyla skorlari kayar).
            "alias_variants": {
                "type": "nested",
                "properties": {
                    "value": {
                        "type": "text",
                        "analyzer": "turkish_analyzer",
                        "fields": {"ascii": {"type": "text", "analyzer": "ascii_analyzer"}},
                    }
                },
            },
            "parent_name": _text_field(),              # subunit'e denormalize (parent enjeksiyonu)
            "kind_label_raw": {"type": "keyword"},
            "unit_type": {"type": "keyword"},
            "program_type": {"type": "keyword"},
            "is_interdisciplinary": {"type": "boolean"},
            "is_evening": {"type": "boolean"},
            "is_ror_child": {"type": "boolean"},
            "country": {"type": "keyword"},
            "city": {"type": "keyword"},
            "canonical_ref": {"type": "keyword"},
            "active_override": {"type": "boolean"},
            "embedding": {                             # F3'te dolar
                "type": "dense_vector",
                "dims": EMBEDDING_DIM,
                "index": True,
                "similarity": "cosine",
            },
        }
    }


def build_index_body() -> dict[str, Any]:
    return {"settings": build_index_settings(), "mappings": build_mapping()}
