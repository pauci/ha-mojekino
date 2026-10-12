"""Tests for the Home Assistant side of the MojeKino integration."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

import pytest
from conftest import load
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_NAME, CONF_URL, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.mojekino.const import (
    CONF_BASE_URL,
    CONF_CINEMA_ID,
    CONF_CLIENT_ID,
    CONF_LANGUAGE,
    CONF_PROGRAM_ID,
    DOMAIN,
)

BASE = "https://www.kino.banskastiavnica.sk"
PROGRAM = BASE + "/ajax/ajax_program_kina_rozsireny.php"
FILM = BASE + "/klient-241/kino-60/stranka-1126/film-{}"
CALENDAR = "calendar.kino_akademik"
DATA = {
    CONF_URL: BASE + "/",
    CONF_NAME: "Kino Akademik",
    CONF_BASE_URL: BASE,
    CONF_CLIENT_ID: 241,
    CONF_CINEMA_ID: 60,
    CONF_LANGUAGE: "sk",
    CONF_PROGRAM_ID: 24779,
}

PREMIERY = {
    "stav": "ok",
    "iTotalDisplayRecords": "2",
    "tabs": "",
    "html": (
        '<div class="subbox" data-film="840462"><h1>'
        '<a href="/klient-241/kino-60/stranka-1126/film-840462">TANGO PRE 3</a>'
        "</h1></div>"
        '<div class="subbox" data-film="111"><h1>'
        '<a href="/klient-241/kino-60/stranka-1126/film-111">Nový film</a>'
        "</h1></div>"
    ),
}
EMPTY = {"stav": "ok", "iTotalDisplayRecords": "0", "tabs": "", "html": ""}


def mock_site(
    aioclient_mock: AiohttpClientMocker, film_page: str | None = None
) -> None:
    """Mock the Kino Akademik website."""
    aioclient_mock.get(BASE + "/", text=load("bs_home.html"))
    # Specific tabs first: the mocker matches query parameters as a subset.
    aioclient_mock.get(PROGRAM, params={"sTab": "premiery"}, json=PREMIERY)
    aioclient_mock.get(PROGRAM, params={"sTab": "pripravujeme"}, json=EMPTY)
    aioclient_mock.get(PROGRAM, text=load("bs_program.json"))
    aioclient_mock.get(
        FILM.format(840462), text=film_page or load("bs_film_840462.html")
    )
    aioclient_mock.get(FILM.format(999999), status=404)
    aioclient_mock.get(re.compile(r"/film-\d+$"), text="<html></html>")


async def setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Kino Akademik", unique_id="241-60", data=DATA
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture(autouse=True)
async def prague_time(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("Europe/Prague")
    freezer.move_to(datetime(2026, 10, 14, 10, 0, tzinfo=UTC))


async def test_config_flow(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_site(aioclient_mock)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "www.kino.banskastiavnica.sk/"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Kino Akademik"
    assert result["data"] == DATA
    assert result["result"].unique_id == "241-60"

    # The same cinema can't be added twice.
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE + "/"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


KULTURA = {
    "stav": "ok",
    "iTotalDisplayRecords": "18",
    "tabs": "",
    "html": '<div class="media"><h2 class="media-heading">'
    '<a href="/event/828736/fragile-peter-lipa">FRAGILE</a></h2></div>',
}


async def test_config_flow_unsupported_layout(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(BASE + "/", text=load("bs_home.html"))
    aioclient_mock.get(PROGRAM, json=KULTURA)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: BASE + "/"}
    )
    assert result["errors"] == {"base": "not_supported"}


@pytest.mark.parametrize(
    ("response", "error"),
    [
        ({"text": "<html><body>Hello</body></html>"}, "not_supported"),
        ({"status": 500}, "cannot_connect"),
    ],
)
async def test_config_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict,
    error: str,
) -> None:
    aioclient_mock.get("https://example.sk/", **response)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "https://example.sk/"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_calendar(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    mock_site(aioclient_mock)
    entry = await setup_entry(hass)
    assert entry.state is ConfigEntryState.LOADED

    # All three program tabs were read.
    tabs = [
        call[1].query.get("sTab")
        for call in aioclient_mock.mock_calls
        if call[1].path.endswith(".php")
    ]
    assert tabs == [None, "premiery", "pripravujeme"]

    state = hass.states.get(CALENDAR)
    assert state.state == STATE_OFF
    assert state.attributes["message"] == "TANGO PRE 3"
    assert state.attributes["start_time"] == "2026-10-15 18:30:00"
    assert state.attributes["location"] == (
        "Kino Akademik, Námestie sv.Trojice č.1, Banská Štiavnica"
    )

    result = await hass.services.async_call(
        CALENDAR_DOMAIN,
        "get_events",
        {
            "entity_id": CALENDAR,
            "start_date_time": "2026-10-01T00:00:00",
            "end_date_time": "2026-11-01T00:00:00",
        },
        blocking=True,
        return_response=True,
    )
    events = result[CALENDAR]["events"]
    assert [(e["summary"], e["start"], e["end"]) for e in events] == [
        ("TANGO PRE 3", "2026-10-15T18:30:00+02:00", "2026-10-15T20:51:00+02:00"),
        ("TANGO PRE 3", "2026-10-30T18:30:00+01:00", "2026-10-30T20:51:00+01:00"),
    ]
    description = events[0]["description"].splitlines()
    assert description[0] == "Tango pro 3"
    assert description[1] == "2D · ČV · 12 · 6 €"
    assert description[2].startswith("https://system.cinemaware.eu/wstep1.php?id=")
    assert description[3] == FILM.format(840462)
    assert description[-2:] == ["Krátky popis filmu.", "Druhý odsek."]


async def test_started_screening_is_kept(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_site(aioclient_mock)
    entry = await setup_entry(hass)

    # During the first screening the film page lists only the second one.
    freezer.move_to(datetime(2026, 10, 15, 17, 0, tzinfo=UTC))
    page = load("bs_film_840462.html")
    events = json.loads(re.search(r'json">(.*)</script>', page, re.S).group(1))
    page = page.replace(
        json.dumps(events, ensure_ascii=False),
        json.dumps(events[1:], ensure_ascii=False),
    )
    aioclient_mock.clear_requests()
    mock_site(aioclient_mock, film_page=page)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert len(entry.runtime_data.data) == 2
    state = hass.states.get(CALENDAR)
    assert state.state == STATE_ON
    assert state.attributes["start_time"] == "2026-10-15 18:30:00"


async def test_setup_retries_when_site_is_down(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.get(PROGRAM, status=503)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="241-60", data=DATA)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_poster_and_program(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    mock_site(aioclient_mock)
    await setup_entry(hass)
    poster = (
        "https://storage.cinemaware.eu/katalogy/images/0/3/"
        "03d569be-b661-11f1-9bbd-9e966f951e90.jpg"
    )

    state = hass.states.get(CALENDAR)
    assert state.attributes["entity_picture"] == poster

    image = hass.states.get("image.kino_akademik_next_film")
    assert image.attributes["film"] == "TANGO PRE 3"
    assert image.attributes["start_time"] == "2026-10-15T18:30:00+02:00"
    assert image.attributes["film_url"] == FILM.format(840462)
    assert image.attributes["ticket_url"].startswith("https://system.cinemaware.eu/")

    program = hass.states.get("sensor.kino_akademik_program")
    assert program.state == "2"
    first, second = program.attributes["screenings"]
    assert first["title"] == "TANGO PRE 3"
    assert first["start"] == "2026-10-15T18:30:00+02:00"
    assert first["poster"] == poster
    assert first["thumbnail"] == poster.replace("/03d5", "/nahlad_03d5")
    assert first["film_url"] == FILM.format(840462)
    assert first["tags"] == ["2D", "ČV", "12"]
    assert first["tag_titles"][1] == "Česká verzia"
    assert image.attributes["tag_titles"][1] == "Česká verzia"
    assert second["start"] == "2026-10-30T18:30:00+01:00"

    # When the first screening ends, everything moves on without a poll.
    freezer.move_to(datetime(2026, 10, 15, 18, 52, tzinfo=UTC))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(CALENDAR).attributes["start_time"] == "2026-10-30 18:30:00"
    assert hass.states.get("sensor.kino_akademik_program").state == "1"
    image = hass.states.get("image.kino_akademik_next_film")
    assert image.attributes["start_time"] == "2026-10-30T18:30:00+01:00"
