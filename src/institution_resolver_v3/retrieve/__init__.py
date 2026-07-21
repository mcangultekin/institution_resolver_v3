"""Aday montaji + sinyal hesabi (ES ile LLM/gate arasindaki ince katman).

LLM'in agirlik ormanini KURMAZ (v2 dersi). Sinyaller iki mutevazi ise yarar:
1. Deterministik kapinin (gate/) basit kurallari,
2. LLM baglamina kanit olarak yazilmak (aday basina 3-4 sayi).

Sinyaller: bm25_norm (havuz-max), knn_cosine, token_set_ratio (aksan-toleransli),
lexical_floor (partial_ratio tabanli), qualifier_conflict (bool), parent_match (bool).

parent-first cascade: parent guvenli cozuldugunde subunit havuzu term:{parent_id}
ile filtrelenir; belirsizse filtresiz fallback.
"""
