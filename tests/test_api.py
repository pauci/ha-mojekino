"""Tests for the HA-independent parsers."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from conftest import load

from api import (
    MojeKinoNotSupportedError,
    parse_cinema,
    parse_film_links,
    parse_films,
    parse_screenings,
    parse_tabs,
    thumbnail_url,
)

BASE = "https://www.kino.banskastiavnica.sk"
CEST = timezone(timedelta(hours=2))
CET = timezone(timedelta(hours=1))


def test_parse_cinema() -> None:
    cinema = parse_cinema(load("bs_home.html"), BASE + "/klient-241/kino-60")
    assert cinema.base_url == BASE
    assert cinema.client_id == 241
    assert cinema.cinema_id == 60
    assert cinema.name == "Kino Akademik"
    assert cinema.language == "sk"
    assert cinema.program_id == 24779
    assert cinema.home_url == BASE + "/klient-241/kino-60"


def test_parse_cinema_rejects_other_sites() -> None:
    with pytest.raises(MojeKinoNotSupportedError):
        parse_cinema("<html><body class='x'>Hello</body></html>", "https://a.sk/")


def test_parse_program() -> None:
    data = json.loads(load("bs_program.json"))
    assert parse_tabs(data["tabs"]) == [
        ("hrame", "758"),
        ("premiery", "759"),
        ("pripravujeme", "760"),
    ]
    films = parse_films(data["html"], BASE)
    assert [f.id for f in films] == [840497, 840462, 840483]
    tango = films[1]
    assert tango.title == "TANGO PRE 3"
    assert tango.original_title == "Tango pro 3"
    assert tango.url == BASE + "/klient-241/kino-60/stranka-1126/film-840462"
    assert tango.tags == ("2D", "ČV", "12")
    assert tango.tag_titles == (
        "2D",
        "Česká verzia",
        "nevhodné pre vekovú skupinu maloletých do 12 rokov",
    )
    assert tango.poster.startswith("https://storage.cinemaware.eu/")
    assert tango.thumbnail == thumbnail_url(tango.poster)


def test_parse_film_links() -> None:
    films = parse_film_links(load("bs_home.html"), BASE)
    assert [(f.id, f.url) for f in films] == [
        (840462, BASE + "/klient-241/kino-60/stranka-1126/film-840462"),
        (999999, BASE + "/klient-241/kino-60/stranka-1126/film-999999"),
    ]


def test_parse_screenings() -> None:
    screenings = parse_screenings(load("bs_film_840462.html"), 840462)
    assert len(screenings) == 2
    first, second = screenings
    assert first.title == "TANGO PRE 3"
    assert first.start == datetime(2026, 10, 15, 18, 30, tzinfo=CEST)
    assert first.end == datetime(2026, 10, 15, 20, 51, tzinfo=CEST)
    # After the switch to winter time.
    assert second.start == datetime(2026, 10, 30, 18, 30, tzinfo=CET)
    assert first.location == "Kino Akademik, Námestie sv.Trojice č.1, Banská Štiavnica"
    assert first.price == 6
    assert first.currency == "EUR"
    assert first.ticket_url.startswith("https://system.cinemaware.eu/wstep1.php?id=")
    assert first.uid == first.ticket_url.split("id=")[1]
    assert first.synopsis == "Krátky popis filmu.\nDruhý odsek."


def test_parse_screenings_other_cinema() -> None:
    screenings = parse_screenings(load("lumiere_film.html"), 841743)
    assert [s.title for s in screenings] == [
        "Zomrieť a žiť | diskusia s tvorcami filmu",
        "Zomrieť a žiť | novinka",
    ]
    assert screenings[0].location == "Kino Lumiere (K1), Špitálska 4, Bratislava"


def test_parse_screenings_fallbacks() -> None:
    page = (
        '<script type="application/ld+json">'
        '{"@type": "Event", "name": "Film", "startDate": "2026-11-01T18:00:00+01:00"}'
        "</script>"
        '<script type="application/ld+json">{not json}</script>'
        '<script type="application/ld+json">'
        '{"@type": "Event", "name": "No time zone", "startDate": "2026-11-01T18:00:00"}'
        "</script>"
    )
    (screening,) = parse_screenings(page, 5)
    assert screening.end - screening.start == timedelta(hours=2)
    assert screening.uid == "5-2026-11-01T18:00:00+01:00"
    assert screening.price is None


def test_thumbnail_url() -> None:
    base = "https://storage.cinemaware.eu/katalogy/images/0/3/"
    assert thumbnail_url(base + "abc.jpg") == base + "nahlad_abc.jpg"
    assert thumbnail_url(base + "nahlad_abc.jpg") == base + "nahlad_abc.jpg"
    assert thumbnail_url("https://example.sk/a.jpg") == "https://example.sk/a.jpg"
    assert thumbnail_url("") == ""
