# MojeKino pre Home Assistant

Integrácia pre Home Assistant, ktorá z programu kina urobí kalendár, plagát
najbližšieho filmu a zoznam predstavení pre dashboard. Funguje s webmi kín
postavenými na systéme **MojeKino** od spoločnosti Ticketware, ktorý používa
množstvo slovenských (a niektoré české) kín.

*[English summary below.](#english)*

## Ktoré kiná sú podporované

Integrácia nemá pevný zoznam kín. Funguje s každým webom na systéme
MojeKino, ktorý spoznáte podľa:

- adries stránok v tvare `/klient-241/kino-60/...`,
- odkazov na nákup vstupeniek na `system.cinemaware.eu`,
- textu *„… – program a vstupenky online“* v názve stránky.

Overené s:

| Kino | Web |
|---|---|
| Kino Akademik, Banská Štiavnica | [kino.banskastiavnica.sk](https://www.kino.banskastiavnica.sk/) |
| Kino Lumière, Bratislava (vrátane sál K1–K4) | [kino-lumiere.sk](https://www.kino-lumiere.sk/) |
| Kino Mier, Senec | [kinosenec.sk](https://www.kinosenec.sk/) |

Nefunguje s:

- **novšími webmi Ticketware na platforme Vercel** (napr. kino.michalovce.sk,
  kinostupava.sk). Bez skutočného prehliadača odpovedajú len chybou 429.
- **webmi divadiel a kultúrnych domov** so šablónou „kultura“ (napr.
  kultura.puchov.sk). Nastavenie ohlási, že rozloženie nie je podporované.

Ak ste integráciu vyskúšali s ďalším kinom, dajte vedieť v
[issues](https://github.com/pauci/ha-mojekino/issues), doplním ho do zoznamu.

## Čo získate

Každé kino je jedno zariadenie s tromi entitami (názvy pre kino *Kino
Akademik*, v anglickom Home Assistante je obrázok `..._next_film`):

| Entita | Čo to je |
|---|---|
| `calendar.kino_akademik` | Všetky nadchádzajúce predstavenia ako udalosti. Obrázok entity je plagát najbližšieho filmu. |
| `image.kino_akademik_dalsi_film` | Plagát filmu, ktorý sa práve hrá alebo sa bude hrať najbližšie |
| `sensor.kino_akademik_program` | Počet nadchádzajúcich predstavení, zoznam je v atribúte `screenings` |

Každá udalosť v kalendári má:

- **názov**, začiatok a koniec (podľa dĺžky filmu),
- **miesto**: kino a sála s adresou,
- **popis**: pôvodný názov, formát / jazyk / vekovú prístupnosť, cenu, odkaz
  na vstupenky, stránku filmu a obsah.

Entita s plagátom má atribúty `film`, `start_time`, `film_url`, `ticket_url`,
`tags` (napr. `2D`, `ČT`, `15`) a `tag_titles` (čo jednotlivé označenia
znamenajú, tak ako to vysvetľuje web kina, napr. *České titulky*).

Každá položka zoznamu `screenings` má `title`, `start`, `end`, `location`,
`tags`, `tag_titles`, `price`, `currency`, `poster`, `thumbnail`,
`film_url` a `ticket_url`. Zoznam je určený pre karty Markdown a neukladá sa
do databázy (recorder).

Program sa obnovuje každé 3 hodiny. „Najbližší film“ sa posunie hneď, ako
predstavenie skončí.

Program si tak môžete zobraziť na dashboarde, spýtať sa Assista, čo dávajú
tento týždeň v kine, alebo vytvoriť automatizácie, napríklad upozornenie na
nový film v programe.

### Príklad pre dashboard

Home Assistant zobrazuje popis udalostí v kalendári ako obyčajný text, takže
odkazy v ňom nie sú klikateľné. Program s plagátmi a klikateľnými odkazmi
zobrazíte kartou Markdown:

```jinja
{%- set dni = ['Po','Ut','St','Št','Pi','So','Ne'] %}
{%- set ns = namespace(den='') %}
{%- set zoznam = state_attr('sensor.kino_akademik_program', 'screenings') or [] %}
{%- if zoznam %}
<table role="presentation">
{%- for s in zoznam %}
{%- set t = as_datetime(s.start) | as_local %}
{%- set den = dni[t.weekday()] ~ ' ' ~ t.day ~ '. ' ~ t.month ~ '.' %}
{%- if den != ns.den %}
{%- if ns.den %}
<tr><td colspan="2">&nbsp;</td></tr>
{%- endif %}{% set ns.den = den %}
<tr><td colspan="2"><b>{{ den }}</b></td></tr>
{%- endif %}
<tr><td width="48"><a href="{{ s.film_url }}"><img src="{{ s.thumbnail or s.poster }}" width="40" alt=""></a></td><td><a href="{{ s.ticket_url }}">{{ t.strftime('%H:%M') }} 🎟️</a> <b><a href="{{ s.film_url }}">{{ s.title }}</a></b><br><small>{% for code in s.tags %}<abbr title="{{ s.tag_titles[loop.index0] }}">{{ code }}</abbr>{% if not loop.last %} · {% endif %}{% endfor %}</small></td></tr>
{%- endfor %}
</table>
{%- else %}
Momentálne nie je naplánované žiadne predstavenie.
{%- endif %}
```

Vďaka `role="presentation"` Home Assistant vykreslí tabuľku bez okrajov.
Plagát najbližšieho filmu zobrazíte kartou *Obrázok entity* (picture-entity)
s entitou `image.kino_akademik_dalsi_film`.

## Inštalácia

### HACS

1. V HACS pridajte `https://github.com/pauci/ha-mojekino` ako vlastný
   repozitár (typ *Integrácia*).
2. Nainštalujte **MojeKino** a reštartujte Home Assistant.

### Ručne

Skopírujte priečinok `custom_components/mojekino` do
`config/custom_components` a reštartujte Home Assistant.

## Nastavenie

**Nastavenia → Zariadenia a služby → Pridať integráciu → MojeKino** a zadajte
web kina. Každé kino pridajte zvlášť.

Integrácia číta zoznamy filmov z programu na webe a k tomu všetky odkazy na
filmy na stránke, ktorú zadáte. Ak niektoré filmy chýbajú, zmeňte v ponuke
integrácie (⋮ → prekonfigurovanie) adresu na stránku s programom kina.

## Ako to funguje

Oficiálne API neexistuje. Integrácia číta:

1. zoznamy filmov z `/ajax/ajax_program_kina_rozsireny.php` (tú istú
   požiadavku robí web kina vo vašom prehliadači),
2. stránku každého filmu, ktorá obsahuje jeho predstavenia ako
   [schema.org udalosti](https://schema.org/Event) (JSON-LD) s presným
   začiatkom a koncom.

Pri každej aktualizácii urobí jednu požiadavku na každý film (najviac 4
naraz). Plagáty sa načítavajú priamo z úložiska obrázkov Ticketware
(`storage.cinemaware.eu`), pre zoznam v menšej verzii (~7 kB).

Predstavenia po začiatku zo stránok filmov zmiznú, preto si ich kalendár
ponechá ešte 7 dní (do reštartu Home Assistantu).

## Obmedzenia

- Každé kino má web nastavený trochu inak. Ak filmy kina nie sú v programe
  ani na zadanej stránke, integrácia ich nenájde.
- Ak Ticketware zmení šablónu webu, integrácia môže prestať fungovať, kým ju
  neupravím.
- Označenia (2D, jazyk, vek) sú za film, nie za jednotlivé predstavenie.

Projekt nie je prepojený so spoločnosťou Ticketware SE ani so žiadnym kinom.

---

## English

**MojeKino** turns the program of a cinema whose website runs on
Ticketware's MojeKino system (common in Slovakia, some in Czechia) into
Home Assistant entities: a calendar of all screenings, an image entity with
the next film's poster, and a program sensor whose `screenings` attribute
(not recorded) feeds Markdown cards with posters and clickable film and
ticket links.

You can recognise supported sites by page URLs like
`/klient-241/kino-60/...` and ticket links to `system.cinemaware.eu`.
Tested with Kino Akademik (Banská Štiavnica), Kino Lumière (Bratislava) and
Kino Mier (Senec). Newer Ticketware sites hosted on Vercel, and the
theatre/culture-house template, are not supported.

Install through HACS as a custom repository
(`https://github.com/pauci/ha-mojekino`, type *Integration*), restart, then
add **MojeKino** under *Settings → Devices & services* and enter the
cinema's website. The program refreshes every 3 hours. There is no
official API: the integration reads the site's program module and each film
page's schema.org JSON-LD events.

Not affiliated with Ticketware SE or any cinema.
