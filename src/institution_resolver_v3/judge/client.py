"""LLM cagri katmani - F4 hakem (bkz. docs/DURUM.md).

Neden Ollama, neden Anthropic DEGIL: bu katmanda Claude/Anthropic KULLANILMIYOR
(kullanici karari, maliyet - proje canliya alinacak gercek bir sirket sistemi).
Gemma 4 E2B/E4B yerelde, quantize (GGUF), Ollama uzerinden calisiyor; iki
boyut da denenip sonuca gore secilecek (`judge.model` config'ten).

`LlmClient` (Protocol) sayesinde judge.py belirli bir saglayiciya baglanmaz -
testlerde sahte bir client enjekte edilir (gercek Ollama/ag gerekmez), ileride
baska bir backend'e gecmek (baska bir yerel model, baska bir API) sadece yeni
bir client sinifi yazmak demek olur.

`generate()` HAM METIN doner - JSON parse/dogrulama burada YAPILMAZ (judge.py'nin
isi, bkz. o modulun docstring'i: "doğrulayıcı" adimi client'tan bagimsiz kalmali).

Baglanti yeniden-kullanimi (2026-07-24, canli olcum - bkz. docs/DENEY_2026-07-24_*
performans notu): `httpx.post(...)` (tek-atis convenience fonksiyonu) HER
cagrida yeni bir istemci/baglanti kuruyor - ayni prompt/model icin bu, gercek
Ollama uretim suresinin (`eval_duration`) neredeyse KATI kadar (~5-8s) gizli
maliyet ekliyordu (wall time vs Ollama'nin kendi rapor ettigi `total_duration`
arasindaki fark olcumle 0.01s'ye dustu). `OllamaClient` bu yuzden kalici bir
`httpx.Client` tutar (instance-scoped, ayni nesne birden fazla `generate()`
cagrisinda paylasilir - CLI/batch kullaniminda dogal olarak boyle kullanilir)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import httpx

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0


class LlmError(RuntimeError):
    """Ollama cagrisi basarisiz oldu (baglanti, zaman asimi, HTTP hatasi)."""


class LlmClient(Protocol):
    def generate(self, prompt: str, *, temperature: float = 0.0) -> str: ...


@dataclass
class OllamaClient:
    """`model`: Ollama'ya cekilmis tag, ör. 'gemma4:e2b' / 'gemma4:e4b'.

    Not: `hf.co/google/gemma-4-E2B-it-...-gguf` gibi DOGRUDAN HuggingFace-import
    denendi, Ollama 0.32.3'te "gemma4" mimarisi icin 400 hatasi verdi (canli
    dogrulandi, 2026-07-24) - Ollama'nin KENDI kutuphanesindeki curated tag
    ('gemma4:e2b'/'gemma4:e4b') calisiyor, o kullanilmali.
    """

    model: str
    host: str = DEFAULT_HOST
    timeout: float = DEFAULT_TIMEOUT
    _client: httpx.Client | None = field(default=None, repr=False, compare=False)

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "OllamaClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def generate(self, prompt: str, *, temperature: float = 0.0) -> str:
        """Tek-atis (stream=False) cagri; `format: json` ile Ollama'nin kendisi
        gecerli JSON uretmeye zorlanir (semaya UYUM degil - o judge.py'de
        pydantic ile dogrulanir, bkz. modul docstring'i)."""
        try:
            resp = self._http().post(
                f"{self.host}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": temperature},
                },
            )
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise LlmError(f"Ollama cagrisi basarisiz ({self.model}): {exc}") from exc
        return resp.json()["response"]
