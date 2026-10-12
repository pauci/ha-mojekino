# MojeKino for Home Assistant

A Home Assistant integration that turns the program of a cinema into a
calendar. It works with cinema websites built on Ticketware's **MojeKino**
system, used by many Slovak (and some Czech) cinemas. You can recognise them
by URLs like `/klient-241/kino-60/...` and ticket links to
`system.cinemaware.eu`.

Tested with:

- [Kino Akademik, Banská Štiavnica](https://www.kino.banskastiavnica.sk/)
- [Kino Lumière, Bratislava](https://www.kino-lumiere.sk/)

## What you get

Each cinema becomes a device with three entities (names below are for a
cinema called *Kino Akademik*):

| Entity | What it is |
|---|---|
| `calendar.kino_akademik` | Every upcoming screening as an event. Its picture is the poster of the next film. |
| `image.kino_akademik_next_film` | Poster of the film screening now or next |
| `sensor.kino_akademik_program` | Number of upcoming screenings, with the list in the `screenings` attribute |

Each calendar event has:

- **Title**, start and end time (end from the film's running time)
- **Location**: cinema and hall, with address
- **Description**: original title, format / language / age rating, price,
  ticket link, film page and synopsis

The poster entity has `film`, `start_time`, `film_url`, `ticket_url`,
`tags` (e.g. `2D`, `ČT`, `15`) and `tag_titles` (what each tag means, as
the cinema's website explains it) attributes.

Each item of the program sensor's `screenings` list has `title`, `start`,
`end`, `location`, `tags`, `tag_titles`, `price`, `currency`, `poster`,
`thumbnail`, `film_url` and `ticket_url`. The list is meant for Markdown
cards and is not stored in the recorder.

So you can show the program on a dashboard, ask Assist what's on at the
cinema this week, or build automations, e.g. a notification when a new film
appears or a reminder on screening days.

The program is refreshed every 3 hours, and the "next film" moves on as
soon as a screening ends.

### Dashboard example

Home Assistant shows calendar event descriptions as plain text, so links in
them are not clickable. For a program with posters and clickable links, use
a Markdown card:

```jinja
{%- set ns = namespace(day='') %}
{%- set items = state_attr('sensor.kino_akademik_program', 'screenings') or [] %}
{%- if items %}
<table role="presentation">
{%- for s in items %}
{%- set t = as_datetime(s.start) | as_local %}
{%- set day = t.strftime('%a %d. %m.') %}
{%- if day != ns.day %}
{%- if ns.day %}
<tr><td colspan="2">&nbsp;</td></tr>
{%- endif %}{% set ns.day = day %}
<tr><td colspan="2"><b>{{ day }}</b></td></tr>
{%- endif %}
<tr><td width="48"><a href="{{ s.film_url }}"><img src="{{ s.thumbnail or s.poster }}" width="40" alt=""></a></td><td><a href="{{ s.ticket_url }}">{{ t.strftime('%H:%M') }} 🎟️</a> <b><a href="{{ s.film_url }}">{{ s.title }}</a></b><br><small>{% for code in s.tags %}<abbr title="{{ s.tag_titles[loop.index0] }}">{{ code }}</abbr>{% if not loop.last %} · {% endif %}{% endfor %}</small></td></tr>
{%- endfor %}
</table>
{%- else %}
No screenings planned.
{%- endif %}
```

`role="presentation"` makes Home Assistant draw the table without borders.

## Installation

### HACS

1. In HACS, add `https://github.com/pauci/ha-mojekino` as a custom repository
   (type *Integration*).
2. Install **MojeKino** and restart Home Assistant.

### Manual

Copy `custom_components/mojekino` into your `config/custom_components`
folder and restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → MojeKino**, then enter
the cinema's website. Add each cinema separately.

The integration reads the film lists of the site's program module, plus all
film links on the page you enter. If some films are missing, use the
reconfigure option to switch to the cinema's program page.

## How it works

There is no official API. The integration reads:

1. the program module's film lists from
   `/ajax/ajax_program_kina_rozsireny.php` (the same request the website
   makes in your browser), and
2. each film's page, which lists its screenings as
   [schema.org events](https://schema.org/Event) (JSON-LD) with exact start
   and end times.

It makes one request per film on each refresh (at most 4 at a time).
Screenings drop off the film pages once they start, so the calendar keeps
them for another 7 days (until Home Assistant restarts).

## Limitations

- Each cinema configures its website differently. If a cinema's films are
  not in its program module or on the page you enter, they won't appear.
- If Ticketware changes the website template, the integration may stop
  working until it is updated.

This project is not affiliated with Ticketware SE or any cinema.
