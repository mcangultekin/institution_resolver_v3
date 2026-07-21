"""Typer CLI. Entry point: institution_resolver_v3.cli.main:app (inres3).

Komutlar (fazlar ilerledikce dolar):
- build-data : raw -> processed kanonik + transform_report (deterministik)
- setup-es   : ES mapping + turkish analyzer olustur
- index      : ingest -> embed -> bulk index -> force-merge
- match      : tek sorgu coz (parent + subunit + karar + gerekce JSON)
- batch      : CSV toplu (resume/memoization/CSV-injection korumasi)
- recall     : gercek sette recall@k olc (F2)
- label-set  : LLM on-etiket + insan onayi (gercek etiketli set)
- evaluate   : gercek/sentetik set uzerinde metrikler
"""
