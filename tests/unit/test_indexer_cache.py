"""_compute_embeddings disk-cache + id-esleme testleri - model/ES gerektirmez,
encode_texts MOCKLANIR (bkz. embedding/encoder.py).

Kapsam:
- Cache gecerliligi id listesi KADAR embed metnine de bagli olmali (E4 -
  parent adi degisince, id ayni kalsa da subunit embed metni degisir; eski
  kod bunu yakalamiyordu, bayat vektor sessizce donuyordu).
- Vektor<->belge eslemesi POZISYONA degil, composite id'ye (`record_type:id`)
  bagli olmali (E5 - iki ayri fonksiyon ayni sirayi varsayiyordu; parent ve
  subunit id uzaylari 55.431 kayitta CAKISIYOR, pozisyonel eslesme kirilgan)."""

from __future__ import annotations

import inspect

import numpy as np

from institution_resolver_v3.elastic import indexer as indexer_mod


def _fake_encode(calls: list[list[str]]):
    def _encode(texts, **kw):
        calls.append(list(texts))
        return np.array([[float(len(t))] for t in texts])

    return _encode


def test_cache_reused_when_ids_and_text_identical(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("institution_resolver_v3.embedding.encoder.encode_texts", _fake_encode(calls))
    records = [{"id": "1", "record_type": "parent", "name": "GAZI UNIVERSITESI", "aliases": []}]
    cache = tmp_path / "embeddings.npz"

    v1_keys, v1_vecs = indexer_mod._compute_embeddings(records, {}, cache_path=cache)
    v2_keys, v2_vecs = indexer_mod._compute_embeddings(records, {}, cache_path=cache)

    assert len(calls) == 1, "ikinci cagri cache'ten gelmeli, encode tekrar cagrilmamali"
    assert v1_keys == v2_keys
    assert np.array_equal(v1_vecs, v2_vecs)


def test_cache_invalidated_when_text_changes_with_same_ids(tmp_path, monkeypatch):
    """Kritik bulgu (E4): parent adi duzeltilince (id SABIT) embed metni
    degisir. Cache bunu yakalamali - eski (bayat) vektoru sessizce donmemeli."""
    calls: list[list[str]] = []
    monkeypatch.setattr("institution_resolver_v3.embedding.encoder.encode_texts", _fake_encode(calls))
    cache = tmp_path / "embeddings.npz"

    v1_records = [{"id": "1", "record_type": "parent", "name": "GAZI UNIVERSITESI", "aliases": []}]
    indexer_mod._compute_embeddings(v1_records, {}, cache_path=cache)
    assert len(calls) == 1

    # ayni id="1", ad duzeltildi (yazim hatasi fix) - id UZAYI degismedi
    v2_records = [{"id": "1", "record_type": "parent", "name": "GAZİ ÜNİVERSİTESİ", "aliases": []}]
    indexer_mod._compute_embeddings(v2_records, {}, cache_path=cache)

    assert len(calls) == 2, "id ayni ama metin degisti - yeniden encode edilmeliydi (bayat vektor donulmemeli)"


def test_old_cache_format_without_hash_is_treated_as_stale(tmp_path, monkeypatch):
    """Gecis uyumlulugu: text_hash eklenmeden ONCE yazilmis eski .npz
    dosyalari crash etmemeli, guvenli tarafta kalip yeniden hesaplanmali."""
    calls: list[list[str]] = []
    monkeypatch.setattr("institution_resolver_v3.embedding.encoder.encode_texts", _fake_encode(calls))
    cache = tmp_path / "embeddings.npz"
    records = [{"id": "1", "record_type": "parent", "name": "GAZI UNIVERSITESI", "aliases": []}]

    np.savez(cache, ids=np.array(["1"], dtype=object), vecs=np.array([[99.0]]))  # eski format, text_hash yok

    keys, vecs = indexer_mod._compute_embeddings(records, {}, cache_path=cache)

    assert len(calls) == 1, "eski formatli cache guvenilmemeli, yeniden hesaplanmali"
    assert vecs[keys.index("parent:1")].tolist() != [99.0], "eski (bayat) cache degeri donulmemeliydi"


def test_compute_embeddings_returns_vectors_keyed_by_composite_id(tmp_path, monkeypatch):
    """E5: parent ve subunit id uzaylari cakisabilir (ayni '7'). Sonuc
    `(keys, vecs)` olmali, `keys[i]` `record_type:id` formatinda - pozisyon/sira
    onemsiz, satir kimlige gore bulunur."""
    calls: list[list[str]] = []
    monkeypatch.setattr("institution_resolver_v3.embedding.encoder.encode_texts", _fake_encode(calls))
    records = [
        {"id": "7", "record_type": "parent", "name": "AAAAAAAAAA", "aliases": []},
        {"id": "7", "record_type": "subunit", "parent_id": "7", "name": "BB", "aliases": []},
    ]

    keys, vecs = indexer_mod._compute_embeddings(records, {"7": "AAAAAAAAAA"}, cache_path=tmp_path / "e.npz")

    assert set(keys) == {"parent:7", "subunit:7"}
    i_parent, i_subunit = keys.index("parent:7"), keys.index("subunit:7")
    assert vecs[i_parent].tolist() != vecs[i_subunit].tolist()  # farkli metinler -> farkli (sahte) vektorler


def test_actions_matches_embeddings_by_composite_key_not_position():
    """E5: `_actions` `embeddings[i]` (pozisyon) DEGIL, kimlige (composite key)
    gore satir bulmali. Parent ve subunit'in AYNI raw id'yi (7) tasidigi -
    projede gercekten olan - kritik senaryo."""
    parents = [{"id": "7", "record_type": "parent", "name": "A"}]
    subunits = [{"id": "7", "record_type": "subunit", "parent_id": "7", "name": "B"}]
    # keys sirasi bilerek 'ters': ilk key subunit, ikinci parent
    embeddings = (["subunit:7", "parent:7"], np.array([[9.0], [1.0]]))

    docs = list(indexer_mod._actions(parents, subunits, "idx", embeddings))

    parent_doc = next(d for d in docs if d["_id"] == "parent:7")
    subunit_doc = next(d for d in docs if d["_id"] == "subunit:7")
    assert parent_doc["_source"]["embedding"] == [1.0]
    assert subunit_doc["_source"]["embedding"] == [9.0]


def test_index_data_default_does_not_recreate():
    """E6: `index_data` veri YUKLEMEK icin cagriliyor, index SILMEK icin
    degil. Varsayilan `recreate=False` olmali - aksi halde yanlislikla
    tekrar cagirmak uretim index'ini ucurur."""
    sig = inspect.signature(indexer_mod.index_data)
    assert sig.parameters["recreate"].default is False
