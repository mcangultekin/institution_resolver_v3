"""Iskelet dumani: paket ve tasinan moduller import edilebiliyor mu."""

from __future__ import annotations


def test_package_imports() -> None:
    import institution_resolver_v3 as pkg

    assert pkg.__version__ == "0.1.0"


def test_models_schema() -> None:
    from institution_resolver_v3.models import ParentCanonical, SubunitCanonical

    p = ParentCanonical(id="1", name="GAZI UNIVERSITESI", normalized_name="gazi universitesi")
    assert p.record_type == "parent"

    s = SubunitCanonical(
        id="10",
        merged_ids=["10"],
        parent_id="1",
        name="MAKINE MUHENDISLIGI BOLUMU",
        normalized_name="makine muhendisligi bolumu",
        raw_normalized_name="makine muhendisligi bolumu",
    )
    assert s.record_type == "subunit"


def test_turkish_fold() -> None:
    from institution_resolver_v3.normalize.text_eski import fold_turkish

    # I/i tuzagi: "TIP" ile "tip" ayni ASCII-fold'a duser ama Python .lower()
    # bozuk bilesik uretmez.
    assert fold_turkish("GAZİ  ÜNİVERSİTESİ") == "gazi universitesi"
