"""Embed-metni insasi + kodlama (multilingual-e5-base, dim 768).

Icerik:
- text_builder.py  : embed metni = "passage: {parent_name} - {hierarchy_context...}
                     - {tum alias'lar}". Tum-alias + parent-adi enjeksiyonu kanitli kazanim.
- encoder.py       : batch kodlama + cache (kanonik kayitlar icin)
- query_encoder.py : sorgu tarafi tekil kodlama ("query: ..." on eki)
"""
