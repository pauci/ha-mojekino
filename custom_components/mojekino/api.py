"""Client for cinema websites built on Ticketware's MojeKino platform.

The sites share one template (``mojekino_v2r``). Two parts of it are used:

* ``/ajax/ajax_program_kina_rozsireny.php`` returns the program module's film
  lists (one per tab) as HTML inside JSON.
* Each film page carries its upcoming screenings as schema.org ``Event``
  objects in JSON-LD, with full start/end times, venue, price and ticket link.

This module does not depend on Home Assistant.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import aiohttp

_LOGGER = logging.getLogger(__name__)

PROGRAM_PATH = "/ajax/ajax_program_kina_rozsireny.php"
PAGE_SIZE = 100
MAX_PAGES = 10
MAX_PARALLEL = 4
DEFAULT_DURATION = timedelta(hours=2)
TIMEOUT = aiohttp.ClientTimeout(total=30)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HomeAssistant-mojekino)",
    "Accept-Language": "sk,cs;q=0.8,en;q=0.5",
}

_FILM_HREF = re.compile(r"/klient-\d+/kino-\d+/stranka-\d+/film-(\d+)")
_LD_JSON = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I
)
_TAG = re.compile(r"<[^>]+>")


class MojeKinoError(Exception):
    """Base error."""


class MojeKinoConnectionError(MojeKinoError):
    """The website could not be reached or returned an error."""


class MojeKinoNotSupportedError(MojeKinoError):
    """The page is not a MojeKino cinema website."""


@dataclass(frozen=True, slots=True)
class Cinema:
    """A cinema website."""

    base_url: str
    """Scheme and host, e.g. ``https://www.kino.banskastiavnica.sk``."""
    client_id: int
    cinema_id: int
    name: str
    language: str = "sk"
    program_id: int | None = None
    """``data-smid`` of the program module, if the site has one."""

    @property
    def home_url(self) -> str:
        return f"{self.base_url}/klient-{self.client_id}/kino-{self.cinema_id}"


@dataclass(frozen=True, slots=True)
class Film:
    """A film (or other event) in the program."""

    id: int
    url: str
    title: str = ""
    original_title: str = ""
    poster: str = ""
    thumbnail: str = ""
    tags: tuple[str, ...] = ()
    """Badges such as format, language and age rating, e.g. ``("2D", "ČT", "15")``."""
    tag_titles: tuple[str, ...] = ()
    """What each badge means, e.g. ``("2D", "České titulky", "nevhodné ...")``."""


@dataclass(frozen=True, slots=True)
class Screening:
    """One screening of a film."""

    uid: str
    film_id: int
    title: str
    start: datetime
    end: datetime
    location: str = ""
    ticket_url: str = ""
    price: float | None = None
    currency: str = ""
    image: str = ""
    """Poster URL."""
    synopsis: str = field(default="", compare=False)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _html_to_text(value: str) -> str:
    """Turn a (possibly double-escaped) HTML fragment into plain text."""
    text = html.unescape(value)
    text = re.sub(r"</p>|<br\s*/?>", "\n", text, flags=re.I)
    text = html.unescape(_TAG.sub("", text))
    lines = (_clean(line) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


class _CinemaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.body: dict[str, str] = {}
        self.program_id: str | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "body" and not self.body:
            self.body = a
        elif a.get("id") == "program_kina_tabs" and "data-smid" in a:
            self.program_id = a["data-smid"]
        elif tag == "title" and not self.title:
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


def parse_cinema(page: str, url: str) -> Cinema:
    """Read the cinema's identifiers from any of its pages."""
    parser = _CinemaParser()
    parser.feed(page)
    body = parser.body
    try:
        client_id = int(body["data-klient"])
        cinema_id = int(body["data-kino"])
    except (KeyError, ValueError) as err:
        raise MojeKinoNotSupportedError("Cinema identifiers not found") from err

    parts = urlsplit(url)
    name = re.split(r"\s+[\u2013|-]\s+", _clean(parser.title), maxsplit=1)[0]
    language = body.get("data-jazyk_primarny", "sk")[:2] or "sk"
    return Cinema(
        base_url=f"{parts.scheme}://{parts.netloc}",
        client_id=client_id,
        cinema_id=cinema_id,
        name=name or parts.netloc,
        language=language,
        program_id=int(parser.program_id) if parser.program_id else None,
    )


def parse_tabs(fragment: str) -> list[tuple[str, str]]:
    """Return the program module's tabs as ``(tab, tab_id)`` pairs."""
    return re.findall(r'data-tab="([^"]+)"\s+data-tab-id="([^"]*)"', fragment)


class _FilmListParser(HTMLParser):
    """Parses the program module's ``div.subbox`` film entries."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.films: list[Film] = []
        self._current: dict[str, Any] | None = None
        self._capture: str | None = None
        self._text = ""
        self._tag_title = ""

    def _finish(self) -> None:
        if self._current and self._current.get("url"):
            c = self._current
            self.films.append(
                Film(
                    id=c["id"],
                    url=c["url"],
                    title=_clean(c.get("title", "")),
                    original_title=c.get("original_title", ""),
                    poster=c.get("poster", ""),
                    thumbnail=c.get("thumbnail", ""),
                    tags=tuple(t for t, _ in c["tags"]),
                    tag_titles=tuple(title or t for t, title in c["tags"]),
                )
            )
        self._current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        classes = a.get("class", "").split()
        if tag == "div" and "subbox" in classes and a.get("data-film", "").isdigit():
            self._finish()
            self._current = {"id": int(a["data-film"]), "tags": []}
            return
        c = self._current
        if c is None:
            return
        if tag == "a" and "fancybox" in classes:
            c.setdefault("poster", urljoin(self.base_url, a.get("href", "")))
            c.setdefault("original_title", _clean(a.get("title", "")))
        elif tag == "img" and "thumbnail" not in c and a.get("src"):
            c["thumbnail"] = urljoin(self.base_url, a["src"])
        elif tag == "a" and self._capture == "h1" and "url" not in c:
            c["url"] = urljoin(self.base_url, a.get("href", ""))
            self._text = ""
        elif tag == "h1" and "title" not in c:
            self._capture = "h1"
        elif tag == "span" and "btn" in classes and "price" not in classes:
            self._capture = "tag"
            self._tag_title = _clean(a.get("title", ""))
            self._text = ""

    def handle_endtag(self, tag: str) -> None:
        c = self._current
        if c is None or self._capture is None:
            return
        if self._capture == "h1" and tag in ("a", "h1"):
            if "url" in c and "title" not in c:
                c["title"] = self._text
            self._capture = None
        elif self._capture == "tag" and tag == "span":
            if text := _clean(self._text):
                c["tags"].append((text, self._tag_title))
            self._capture = None

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._text += data

    def close(self) -> None:
        super().close()
        self._finish()


def parse_films(fragment: str, base_url: str) -> list[Film]:
    """Parse the film entries of a program module response."""
    parser = _FilmListParser(base_url)
    parser.feed(fragment)
    parser.close()
    return parser.films


def parse_film_links(page: str, base_url: str) -> list[Film]:
    """Find links to film pages anywhere on a page."""
    films: dict[int, Film] = {}
    for match in re.finditer(r'href="([^"]+)"', page):
        href = html.unescape(match.group(1))
        if (m := _FILM_HREF.search(href)) and (film_id := int(m.group(1))) not in films:
            films[film_id] = Film(id=film_id, url=urljoin(base_url, m.group(0)))
    return list(films.values())


def _ld_events(page: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in _LD_JSON.findall(page):
        try:
            data = json.loads(block)
        except ValueError:
            _LOGGER.debug("Skipping invalid JSON-LD block")
            continue
        items = data if isinstance(data, list) else [data]
        if isinstance(data, dict) and isinstance(data.get("@graph"), list):
            items = data["@graph"]
        events.extend(
            item
            for item in items
            if isinstance(item, dict)
            and item.get("@type") in ("Event", "ScreeningEvent")
        )
    return events


def _location(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    parts = [value.get("name", "")]
    address = value.get("address")
    if isinstance(address, dict):
        parts += [address.get("streetAddress", ""), address.get("addressLocality", "")]
    elif isinstance(address, str):
        parts.append(address)
    return ", ".join(_clean(p) for p in parts if isinstance(p, str) and p.strip())


def thumbnail_url(poster: str) -> str:
    """Small version of a poster on Ticketware's image storage.

    The storage keeps a ``nahlad_`` (preview) copy of each catalogue image,
    about a tenth of the size. Other URLs are returned unchanged.
    """
    parts = urlsplit(poster)
    if parts.netloc != "storage.cinemaware.eu" or "/" not in parts.path:
        return poster
    folder, name = parts.path.rsplit("/", 1)
    if name.startswith("nahlad_"):
        return poster
    return parts._replace(path=f"{folder}/nahlad_{name}").geturl()


def _image(value: Any) -> str:
    """The first image URL of a schema.org ``image`` value (the poster)."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("url", "")
    return value if isinstance(value, str) else ""


def parse_screenings(page: str, film_id: int) -> list[Screening]:
    """Parse the screenings from a film page's JSON-LD."""
    screenings: dict[str, Screening] = {}
    for event in _ld_events(page):
        try:
            start = datetime.fromisoformat(event["startDate"])
        except KeyError, TypeError, ValueError:
            continue
        if start.tzinfo is None:
            continue
        try:
            end = datetime.fromisoformat(event["endDate"])
        except KeyError, TypeError, ValueError:
            end = start
        if end.tzinfo is None or end <= start:
            end = start + DEFAULT_DURATION

        offers = event.get("offers")
        if isinstance(offers, list):
            offers = offers[0] if offers else None
        offers = offers if isinstance(offers, dict) else {}
        ticket_url = offers.get("url", "") if isinstance(offers.get("url"), str) else ""
        try:
            price = float(offers["price"])
        except KeyError, TypeError, ValueError:
            price = None

        ticket_id = parse_qs(urlsplit(ticket_url).query).get("id", [""])[0]
        uid = ticket_id or f"{film_id}-{start.isoformat()}"
        screenings[uid] = Screening(
            uid=uid,
            film_id=film_id,
            title=_clean(html.unescape(str(event.get("name", "")))),
            start=start,
            end=end,
            location=_location(event.get("location")),
            ticket_url=ticket_url,
            price=price,
            currency=str(offers.get("priceCurrency", "")),
            image=_image(event.get("image")),
            synopsis=_html_to_text(str(event.get("description", ""))),
        )
    return sorted(screenings.values(), key=lambda s: s.start)


class MojeKinoClient:
    """Reads the program of one cinema."""

    def __init__(
        self, session: aiohttp.ClientSession, cinema: Cinema, page_url: str = ""
    ) -> None:
        self._session = session
        self.cinema = cinema
        self.page_url = page_url or cinema.home_url
        """Page whose film links are also included (the URL the user gave)."""
        self._semaphore = asyncio.Semaphore(MAX_PARALLEL)

    @staticmethod
    async def _get(
        session: aiohttp.ClientSession, url: str, params: dict[str, Any] | None = None
    ) -> aiohttp.ClientResponse:
        try:
            resp = await session.get(
                url, params=params, headers=HEADERS, timeout=TIMEOUT
            )
            resp.raise_for_status()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MojeKinoConnectionError(f"{url}: {err}") from err
        return resp

    @classmethod
    async def _get_text(
        cls, session: aiohttp.ClientSession, url: str
    ) -> tuple[str, str]:
        """Return a page's text and its final URL (after redirects)."""
        resp = await cls._get(session, url)
        try:
            return await resp.text(), str(resp.url)
        except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as err:
            raise MojeKinoConnectionError(f"{url}: {err}") from err

    @classmethod
    async def discover(cls, session: aiohttp.ClientSession, url: str) -> Cinema:
        """Identify the cinema behind a URL of any of its pages."""
        page, final_url = await cls._get_text(session, url)
        cinema = parse_cinema(page, final_url)
        if cinema.program_id is None:
            # The program module is usually on the cinema's home page.
            try:
                home, _ = await cls._get_text(session, cinema.home_url)
                program_id = parse_cinema(home, cinema.home_url).program_id
            except MojeKinoError:
                program_id = None
            if program_id is not None:
                cinema = Cinema(
                    base_url=cinema.base_url,
                    client_id=cinema.client_id,
                    cinema_id=cinema.cinema_id,
                    name=cinema.name,
                    language=cinema.language,
                    program_id=program_id,
                )
        return cinema

    async def _program_page(self, page: int, tab: str = "", tab_id: str = "") -> dict:
        c = self.cinema
        params: dict[str, Any] = {
            "strana": page,
            "pocet_na_strane": PAGE_SIZE,
            "klient": c.client_id,
            "kino": c.cinema_id,
            "jazyk": c.language,
            "smid": c.program_id,
        }
        if tab:
            params |= {"sTab": tab, "sTabID": tab_id}
        resp = await self._get(self._session, c.base_url + PROGRAM_PATH, params)
        try:
            data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MojeKinoConnectionError(f"Invalid program response: {err}") from err
        if not isinstance(data, dict) or data.get("stav") != "ok":
            raise MojeKinoConnectionError("Program request was not accepted")
        return data

    async def _program_tab(self, tab: str = "", tab_id: str = "") -> tuple[dict, list]:
        """Fetch all pages of one tab; return the first response and its films."""
        first = await self._program_page(1, tab, tab_id)
        films = parse_films(first.get("html", ""), self.cinema.base_url)
        try:
            total = int(first.get("iTotalDisplayRecords", 0))
        except TypeError, ValueError:
            total = 0
        page = 1
        while len(films) < total and page < MAX_PAGES:
            page += 1
            more = parse_films(
                (await self._program_page(page, tab, tab_id)).get("html", ""),
                self.cinema.base_url,
            )
            if not more:
                break
            films += more
        return first, films

    async def get_films(self) -> list[Film]:
        """List the films in the program module and on the configured page."""
        films: dict[int, Film] = {}
        if self.cinema.program_id is not None:
            first, listed = await self._program_tab()
            tabs = parse_tabs(first.get("tabs", ""))
            for film in listed:
                films.setdefault(film.id, film)
            # The first response is the default tab; fetch the others too.
            for tab, tab_id in tabs[1:]:
                _, listed = await self._program_tab(tab, tab_id)
                for film in listed:
                    films.setdefault(film.id, film)

        if self.page_url:
            try:
                page, _ = await self._get_text(self._session, self.page_url)
            except MojeKinoConnectionError:
                if self.cinema.program_id is None:
                    raise
                _LOGGER.debug("Could not read %s", self.page_url, exc_info=True)
            else:
                for film in parse_film_links(page, self.cinema.base_url):
                    films.setdefault(film.id, film)
        return list(films.values())

    async def get_screenings(self, film: Film) -> list[Screening]:
        """Read a film's upcoming screenings from its page."""
        async with self._semaphore:
            page, _ = await self._get_text(self._session, film.url)
        return parse_screenings(page, film.id)
