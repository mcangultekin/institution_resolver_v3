"""Kanonik cikti semasi (bkz. V3_VERI_PLANI.md Bolum 1).

`extra="forbid"`: REVIEW K-serisi dersi - sessizce yutulan alan olmasin.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

UnitType = Literal[
    "anabilim_dali",
    "bolum",
    "ror_child",
    "bilim_dali",
    "uygar_merkezi",
    "fakulte",
    "myo",
    "anasanat_dali",
    "enstitu",
    "sanat_dali",
    "yuksekokul",
    "rektorluk",
]

ProgramType = Literal[
    "lisans",
    "onlisans",
    "tezli_yl",
    "tezsiz_yl",
    "doktora",
    "sanatta_yeterlik",
]


class Alias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    locale: str | None = None
    source: str | None = None


class Qualifiers(BaseModel):
    """Sorgu/aday nitelik cikarimi (v2 normalize/qualifiers.py'den tasindi).

    Cikarim mantigi normalize katmaninda yasar. Belge tarafinda v3 kanonik
    semasi zaten yapilandirilmis alanlar tasir (program_type, is_evening);
    bu model asil SORGU tarafinda ("tezli", "doktora" gibi) + celiski
    kontrolunde kullanilir.
    """

    degree: str | None = None
    thesis: bool | None = None
    language: str | None = None
    modality: str | None = None
    extra: list[str] = []


class ParentCanonical(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    normalized_name: str
    country: str | None = None
    city: str | None = None
    canonical_ref: str | None = None
    aliases: list[Alias] = []
    active_override: bool = False
    record_type: Literal["parent"] = "parent"


class SubunitCanonical(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    merged_ids: list[str]
    parent_id: str
    name: str
    normalized_name: str
    raw_normalized_name: str
    kind_label_raw: str | None = None

    unit_type: UnitType | None = None
    program_type: ProgramType | None = None
    is_interdisciplinary: bool = False
    is_evening: bool = False
    is_ror_child: bool = False

    hierarchy_context: list[str] = []
    aliases: list[Alias] = []
    record_type: Literal["subunit"] = "subunit"
