"""Elasticsearch: tek index mapping, indexer, hibrit sorgu.

Icerik:
- client.py   : ES baglantisi (config'ten host/index)
- mappings.py : TEK index "institutions_v1" + alias; turkish + ascii + edge_ngram
                alt alanlari + dense_vector(768). record_type alani ile parent/subunit
                ayni korpusta (tek-korpus IDF; v2'nin iki-index IDF zehirlenmesi cozulur)
- indexer.py  : bulk yukleme + force-merge(1 segment) [determinizm gun-1]
- search.py   : hibrit sorgu (BM25 multi_match + fuzzy + akronim | kNN -> RRF havuzlama);
                her adaya HAM bm25 (havuz-max normalize) + cosine iliştirilir

Aday uretimi tamamen ES'in isidir; retrieval mantigi asagi katmanlara sizmaz.
"""
