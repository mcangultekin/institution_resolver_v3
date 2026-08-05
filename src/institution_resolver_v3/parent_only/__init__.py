"""Parent-only mod: girdiden YALNIZ kurum (parent) kaydini cozer.

NEDEN AYRI BIR PAKET (2026-08-04, kullanici karari)
---------------------------------------------------
Mevcut parent+subunit sistemi AYNEN KALIR - bu paket onun bir varyanti degil,
YANINDA duran ikinci bir moddur. Kural: bu paket mevcut modulleri IMPORT EDER,
mevcut modullerin hicbiri bu paketi tanimaz. Bagimlilik TEK YONLU (yeni -> eski),
bu yuzden burada ne yapilirsa yapilsin ana sistemin davranisi degisemez.

Girdi formati DEGISMEZ: sorgu yine kirli ve serbest metindir ("kurum + birim"
ya da yalniz kurum). Degisen tek sey CIKTI: subunit hic aranmaz, hic dondurulmez.

NEDEN "MEVCUT SISTEM EKSI SUBUNIT" DEGIL
----------------------------------------
Kod okumasiyla dogrulandi: parent karari ALT katmanlarda zaten subunit'ten
BAGIMSIZ (`resolve._parent_union` subunit aramasindan once ve ondan bagimsiz
calisir; `gate._decide_pool` yalniz parent havuzuna bakar). Subunit'in parent
cevabina karistigi tek yer UST yari:
  - `decide._needs_llm`: parent auto_match OLSA BILE subunit auto degilse
    sorgunun TAMAMI hakeme gider ve hakem parent'i EZEBILIR.
  - `judge()`: tek cagrida ikisine birden karar verir, subunit aday listesi
    baglamdadir.
Yani mevcut boru hattini calistirip ciktidan subunit'i silmek AYNI parent
cevabini vermez - bu paket bu yuzden kendi hakem/yonlendirme katmanini tasir.

OLCUMLER (2026-08-04, canli ES + gemma4:e4b, benchmark_500_sample)
------------------------------------------------------------------
  resolve suresi         0.49 s -> 0.27 s/sorgu   (subunit aramasi yok)
  kosinus geri-doldurma  0.36 s -> 0.27 s/sorgu   (%24; N=150'de 150/150 AYNI karar)
  LLM'e dusen satir      %55.8  -> %38.3          (N=120; yonlendirme kuralindan)
  hakem prompt'u         8184   -> 2384 karakter  (%71 kucuk)
  hakem cagrisi          ~62 s  -> ~18 s          (N=6, ayni makine/model)
  uctan uca (hibrit)     ~35 s  -> ~7 s / satir

Kosinus GERI-DOLDURMA yapilmaz: kNN listesine GIREN adaylar kosinusu ES skorundan
almaya devam eder (bedava), ama listeye GIRMEYENLER icin `_default_cosine_fn`in
yaptigi sorgu-basina ~7 mget cagrisi atlanir. Bu deger ne gate karara katar (bkz.
gate.py docstring "bm25_norm ve kosinus SIRALAMAYA/KARARA GIRMEZ") ne de prompt
gosterir (2026-07-27'de cikarildi) - yani hicbir kararin girdisi olmayan bir is
yapiliyordu. Vektorler kNN RETRIEVAL'da KALIR (capraz-dil recall'un kaynagi orasi;
kNN'i atmak N=150'de 3 karari degistirdi, EKLENMEDI).

decompose KALIR: girdi kirli oldugu icin kurum sinirini bulmak hala gerekli.
Atmak %75 hizlandiriyordu ama N=100'de 13 karari bozdu (auto 62 -> 56, kaybedilenler
DOGRU cevaplardi) - denendi ve REDDEDILDI.

SPAN SINIRI (varsayilan: SINIRSIZ)
----------------------------------
`decompose` sorgunun her ardisik kelime penceresini dener (n kelime -> n(n+1)/2
pencere); parent-only surenin ~%57'si burada gecer. `max_span` ile uzun pencereler
atlanabilir. Varsayilan None (= bugunku davranis) cunku uctan uca tabloda bu kalem
gorunmuyor: hibrit modda 40 ms kazanc, 7 saniyenin yaninda %0.5. YALNIZ gate-only
modda anlamli (438K satirda ~33 saat -> ~28 saat).
Veriden secim icin: parent ad varyantlarinin (virgul-segmentleri dahil, decompose'un
skorladigi bicimde) %95.5'i <=8, %98'i <=10, %99.5'i <=16 token. Sorgular ise
ortalama 7.6, en fazla 26 kelime - yani sinir ancak sorgudan KISAYSA devreye girer
(cap=8 sorgularin %42'sinde, cap=16 yalnizca %2'sinde). 168 token'lik kuyruk gercek
ad degil, virgulle birlesmis cok-adli kayit defekti (bkz. docs/DURUM.md).

UC MOD
------
  gate    - LLM YOK. ~0.27 s/sorgu, sorgularin ~%61'i auto_match.
  hybrid  - gate auto_match vermezse hakeme devreder (~%38 satir).
  llm     - her satir hakeme gider; gate yine hesaplanir (denetim icin).

"HANGI PARENT" IKILEMI - OZEL KURAL YOK (olculdu 2026-08-04)
------------------------------------------------------------
"X Universitesi Tip Fakultesi Hastanesi" gibi sorgularda hem semsiye kurum hem
bilesik-adli AYRI parent kaydi havuza girebilir. 500 sorguda olculdu: bu ikilem
8 sorguda (%1.6) olusuyor ve 8/8'inde gate zaten `ambiguous` diyor (parent'taki
katil coklu-exact kurali, `any_rival_blocks_auto=True`) - yani sessizce yanlis
seviyeye auto_match VERILMIYOR, karar hakeme/insana devrediliyor. Ozel bir kural
eklenmedi; gate'in mevcut davranisi korundu.
"""
