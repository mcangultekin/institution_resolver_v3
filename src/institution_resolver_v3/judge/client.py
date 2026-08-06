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

import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_TIMEOUT = 120.0

# Ollama'nin istek-basi varsayilan baglam penceresi ~2048 token ve asan prompt
# SESSIZCE bastan kirpiliyor (canli olcum 2026-07-24: 18-adayli gercek prompt
# ~10.5k karakterken model sadece 2051 token gordu - sorgu + hipotezler +
# listenin BASI, yani 1. siradaki dogru cevap dahil, modele HIC ULASMADI;
# "Ege" ornegindeki iki hakem hatasinin da kok nedeni bu). 8-adayli kirpilmis
# prompt bile ~2.8k token tuttugu icin num_ctx ACIKCA gonderilmeli.
DEFAULT_NUM_CTX = 8192


class LlmError(RuntimeError):
    """Ollama cagrisi basarisiz oldu (baglanti, zaman asimi, HTTP hatasi)."""


class LlmClient(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        format_schema: dict | None = None,
    ) -> str: ...


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
    num_ctx: int = DEFAULT_NUM_CTX
    # C2 (2026-08-06): GECICI tasima hatalarinda yeniden dene. 500-sorgu
    # kosusunda 40 hatanin 10'u "[Errno 111] Connection refused"du - Ollama
    # anlik mesguldu/yeniden yukluyordu, satir kalici hata olarak yazilip
    # atlandi. Olcek notu: %2 kayip, 500K kayitlik uretim kosusunda ~10.000
    # satir demek ve `--resume` bunlari KURTARMIYOR (hata satiri da yazilmis
    # sayilir). Yalniz gecici sinif yeniden denenir - bkz. generate().
    max_retries: int = 2          # toplam 3 deneme
    retry_backoff: float = 0.5    # 0.5s, 1.0s (ustel)
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

    def generate(
        self,
        prompt: str,
        *,
        temperature: float = 0.0,
        format_schema: dict | None = None,
    ) -> str:
        """Tek-atis (stream=False) cagri.

        `format_schema` verilirse Ollama'nin kisitli-uretim (structured output)
        ozelligi kullanilir: cikti, verilen JSON semasina UYMAK ZORUNDA kalir -
        enum'lu alanlarda model listede olmayan bir deger FIZIKSEL OLARAK
        uretemez (canli dogrulandi 2026-07-24: prompt'ta "Z9 sec" denmesine
        ragmen enum {A1,B2} disina cikamadi). Verilmezse eski davranis:
        `format: "json"` sadece "gecerli JSON olsun" der, icerigi kisitlamaz."""
        govde = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": format_schema if format_schema is not None else "json",
            "options": {"temperature": temperature, "num_ctx": self.num_ctx},
        }
        # C2: GECICI hatalarda yeniden dene, KALICI olanlarda DENEME.
        #   yeniden denenir : httpx.TransportError (connect refused/reset, timeout,
        #                     okuma hatasi) + HTTP 5xx  -> Ollama mesgul/yeniden
        #                     yukluyor; ayni istek birazdan calisabilir.
        #   DENENMEZ        : HTTP 4xx (yanlis model tag'i, bozuk sema) - istek
        #                     ne kadar tekrarlanirsa tekrarlansin ayni hatayi
        #                     verir; tekrar sadece zaman yakar ve gercek sorunu
        #                     gizler. `temperature=0` oldugu icin yeniden deneme
        #                     determinizmi bozmaz.
        son: Exception | None = None
        for deneme in range(self.max_retries + 1):
            try:
                resp = self._http().post(f"{self.host}/api/generate", json=govde)
                resp.raise_for_status()
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code < 500 or deneme == self.max_retries:
                    raise LlmError(
                        f"Ollama cagrisi basarisiz ({self.model}): {exc}"
                    ) from exc
                son = exc
            except httpx.TransportError as exc:
                if deneme == self.max_retries:
                    raise LlmError(
                        f"Ollama cagrisi basarisiz ({self.model}, "
                        f"{self.max_retries + 1} deneme): {exc}"
                    ) from exc
                son = exc
            except httpx.HTTPError as exc:      # kalan httpx hatalari: tekrar YOK
                raise LlmError(f"Ollama cagrisi basarisiz ({self.model}): {exc}") from exc
            time.sleep(self.retry_backoff * (2**deneme))
        else:  # pragma: no cover - dongu ya break ya raise ile biter
            raise LlmError(f"Ollama cagrisi basarisiz ({self.model}): {son}")
        data = resp.json()
        # Kirpilma korumasi: Ollama pencereyi asan prompt'u HATASIZ keser; modelin
        # gordugu token sayisi pencereye dayandiysa prompt'un basi buyuk ihtimalle
        # atilmistir - yarim prompt'la alinan karar guvenilmez, sessiz gecilmez.
        seen = data.get("prompt_eval_count")
        if seen is not None and seen >= self.num_ctx:
            raise LlmError(
                f"Prompt, baglam penceresine sigmadi ve Ollama tarafindan sessizce "
                f"kirpildi (model {seen} token gordu, num_ctx={self.num_ctx}) - "
                f"aday listesini kucultun ya da num_ctx'i buyutun."
            )
        return data["response"]
