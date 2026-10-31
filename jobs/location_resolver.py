"""
Resolve job locations, including the Georgia (country) vs Georgia (U.S. state) clash.

The word "Georgia" is not a country by itself. A location is the country of Georgia
only with a country signal (Georgian city, "Georgia, Country", საქართველო, a Georgian
job board, or an explicit country field). It is the U.S. state with a state signal
(City, GA / City, Georgia, "Georgia (USA)", a known Georgia-state city). Anything
else stays unresolved so it is not filed under the country.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from django.db.models import Q

GEORGIA_COUNTRY = "country"
GEORGIA_US_STATE = "us_state"
GEORGIA_AMBIGUOUS = "ambiguous"

# Boards that publish jobs in the country of Georgia, plus employer posts where
# the submitted country field is the user's selection.
LOCAL_GEORGIA_PLATFORMS = frozenset({"jobs.ge", "hr.ge", "myjobs.ge", "jobs.ss.ge"})
TRUSTED_GEORGIA_COUNTRY_PLATFORMS = LOCAL_GEORGIA_PLATFORMS | frozenset({"employer"})

_US_STATE_CODES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
}

_US_STATE_NAMES = {name.lower(): name for name in _US_STATE_CODES.values()}
_US_STATE_NAMES["washington dc"] = "District of Columbia"
_US_STATE_NAMES["washington d.c"] = "District of Columbia"
_US_STATE_NAMES["d.c"] = "District of Columbia"

_CA_PROVINCE_CODES = {
    "AB": "Alberta",
    "BC": "British Columbia",
    "MB": "Manitoba",
    "NB": "New Brunswick",
    "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia",
    "NT": "Northwest Territories",
    "NU": "Nunavut",
    "ON": "Ontario",
    "PE": "Prince Edward Island",
    "QC": "Quebec",
    "SK": "Saskatchewan",
    "YT": "Yukon",
}

# Canonical English name → aliases (Latin and Georgian).
_GEORGIAN_CITY_ALIASES: dict[str, tuple[str, ...]] = {
    "Tbilisi": ("tbilisi", "თბილისი"),
    "Batumi": ("batumi", "ბათუმი"),
    "Rustavi": ("rustavi", "რუსთავი"),
    "Zugdidi": ("zugdidi", "ზუგდიდი"),
    "Poti": ("poti", "ფოთი"),
    "Gori": ("gori", "გორი"),
    "Telavi": ("telavi", "თელავი"),
    "Ozurgeti": ("ozurgeti", "ოზურგეთი"),
    "Zestafoni": ("zestafoni", "zestaponi", "ზესტაფონი"),
    "Kobuleti": ("kobuleti", "ქობულეთი"),
    "Borjomi": ("borjomi", "ბორჯომი"),
    "Akhaltsikhe": ("akhaltsikhe", "ახალციხე"),
    "Mtskheta": ("mtskheta", "მცხეთა"),
    "Senaki": ("senaki", "სენაკი"),
    "Samtredia": ("samtredia", "სამტრედია"),
    "Khashuri": ("khashuri", "ხაშური"),
    "Marneuli": ("marneuli", "მარნეული"),
    "Gardabani": ("gardabani", "გარდაბანი"),
    "Chiatura": ("chiatura", "ჭიათურა"),
    "Tskaltubo": ("tskaltubo", "tsqaltubo", "წყალტუბო"),
    "Kutaisi": ("kutaisi", "ქუთაისი"),
    "Ambrolauri": ("ambrolauri", "ამბროლაური"),
    "Sighnaghi": ("sighnaghi", "signagi", "სიღნაღი"),
    "Mestia": ("mestia", "მესტია"),
    "Stepantsminda": ("stepantsminda", "kazbegi", "სტეფანწმინდა"),
    "Sokhumi": ("sokhumi", "sukhumi", "სოხუმი"),
    "Tskhinvali": ("tskhinvali", "ცხინვალი"),
}

_GEORGIAN_ALIAS_TO_CITY: list[tuple[str, str]] = []
for _canonical, _aliases in _GEORGIAN_CITY_ALIASES.items():
    for _alias in _aliases:
        _GEORGIAN_ALIAS_TO_CITY.append((_alias, _canonical))
_GEORGIAN_ALIAS_TO_CITY.sort(key=lambda item: len(item[0]), reverse=True)

GEORGIAN_CITY_NAMES = frozenset(_GEORGIAN_CITY_ALIASES)

# Cities that, together with a stored country of "Georgia", are the U.S. state
# (the full ", Georgia" suffix was stripped by the old parser).
_US_GEORGIA_CITIES = {
    "Atlanta": "Atlanta",
    "Savannah": "Savannah",
    "Augusta": "Augusta",
    "Columbus": "Columbus",
    "Macon": "Macon",
    "Athens": "Athens",
    "Sandy Springs": "Sandy Springs",
    "Roswell": "Roswell",
    "Albany": "Albany",
    "Marietta": "Marietta",
    "Valdosta": "Valdosta",
    "Warner Robins": "Warner Robins",
    "Johns Creek": "Johns Creek",
    "Alpharetta": "Alpharetta",
    "Peachtree City": "Peachtree City",
    "Rome": "Rome",
    "Gainesville": "Gainesville",
    "Smyrna": "Smyrna",
    "Dunwoody": "Dunwoody",
    "Brookhaven": "Brookhaven",
    "Peachtree Corners": "Peachtree Corners",
    "Newnan": "Newnan",
    "Milton": "Milton",
    "Woodstock": "Woodstock",
    "Kennesaw": "Kennesaw",
    "Lawrenceville": "Lawrenceville",
    "Duluth": "Duluth",
    "Decatur": "Decatur",
    "Statesboro": "Statesboro",
    "Dalton": "Dalton",
    "Carrollton": "Carrollton",
    "Brunswick": "Brunswick",
    "Pooler": "Pooler",
    "Suwanee": "Suwanee",
    "Cumming": "Cumming",
    "Douglasville": "Douglasville",
    "Stockbridge": "Stockbridge",
    "Griffin": "Griffin",
    "Fayetteville": "Fayetteville",
    "Conyers": "Conyers",
    "Acworth": "Acworth",
    "Cartersville": "Cartersville",
    "Buford": "Buford",
    "Snellville": "Snellville",
    "Norcross": "Norcross",
    "Hinesville": "Hinesville",
}
_US_GEORGIA_CITY_BY_LOWER = {name.lower(): name for name in _US_GEORGIA_CITIES}

_COUNTRY_TOKENS = {
    "usa": "USA",
    "us": "USA",
    "u.s": "USA",
    "u.s.a": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "uk": "United Kingdom",
    "u.k": "United Kingdom",
    "united kingdom": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "scotland": "United Kingdom",
    "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    "germany": "Germany",
    "deutschland": "Germany",
    "france": "France",
    "netherlands": "Netherlands",
    "holland": "Netherlands",
    "canada": "Canada",
    "australia": "Australia",
    "ireland": "Ireland",
    "spain": "Spain",
    "spaña": "Spain",
    "poland": "Poland",
}

_UK_NATIONS = frozenset({"england", "scotland", "wales", "northern ireland"})
_NON_PLACES = frozenset(
    {
        "remote",
        "hybrid",
        "onsite",
        "on-site",
        "on site",
        "worldwide",
        "anywhere",
        "global",
        "distributed",
        "wfh",
    }
)

_GEORGIA_COUNTRY_RE = re.compile(
    r"(?i)(?:"
    r"republic\s+of\s+georgia|"
    r"country\s+of\s+georgia|"
    r"georgia\s*,\s*country\b|"
    r"georgia\s*\(\s*country\s*\)|"
    r"georgia\s+country\b|"
    r"საქართველო"
    r")"
)
_GEORGIA_US_RE = re.compile(
    r"(?i)(?:"
    r"\bgeorgia\s*[\(\[]\s*(?:usa|u\.s\.a?\.?|us|united\s+states)\s*[\)\]]|"
    r"\bgeorgia\s*,\s*(?:usa|u\.s\.a?\.?|us|united\s+states(?:\s+of\s+america)?|ga)\b|"
    r"\b(?:usa|u\.s\.a?\.?|united\s+states)\s*,\s*georgia\b|"
    r"\bstate\s+of\s+georgia\b|"
    r"\b(?:north|south|metro|west)\s+georgia\b"
    r")"
)
_USA_RE = re.compile(
    r"(?i)\b(?:usa|u\.s\.a?\.?|united\s+states(?:\s+of\s+america)?)\b|\bus\b"
)
_US_CONTEXT_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:atlanta|savannah|augusta|macon|marietta|roswell|alpharetta|sandy\s+springs)\b|"
    r"\bathens\s*,\s*(?:ga|georgia)\b|"
    r"\bstate\s+of\s+georgia\b|"
    r"\bgeorgia\s*,\s*(?:usa|us|ga)\b|"
    r",\s*ga\b"
    r")"
)
_COUNTRY_CONTEXT_RE = re.compile(
    r"(?i)(?:"
    r"\b(?:tbilisi|batumi|kutaisi|rustavi|zugdidi|poti|telavi|kobuleti)\b|"
    r"თბილისი|ბათუმი|ქუთაისი|საქართველო|"
    r"republic\s+of\s+georgia|country\s+of\s+georgia"
    r")"
)

_COUNTRY_SELECTOR = frozenset(
    {
        "georgia",
        "ge",
        "georgia (country)",
        "georgia, country",
        "georgia country",
        "country of georgia",
        "republic of georgia",
        "საქართველო",
    }
)
_US_SELECTOR = frozenset(
    {
        "georgia (usa)",
        "georgia (us)",
        "georgia (u.s)",
        "georgia (u.s.a)",
        "georgia, usa",
        "georgia, us",
        "georgia, u.s",
        "georgia, u.s.a",
        "georgia, united states",
        "georgia, united states of america",
        "georgia, ga",
        "georgia (state)",
        "georgia (us state)",
        "georgia, state",
        "us state of georgia",
        "georgia usa",
        "georgia us",
        "state of georgia",
    }
)


@dataclass(frozen=True)
class LocationResolution:
    city: str | None
    country: str | None
    region: str | None
    country_authoritative: bool
    georgia: str | None


def _clip(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip(" ,-/")
    if not text:
        return None
    return text[:200]


def _norm_token(value: str) -> str:
    text = (value or "").strip().lower().replace(".", "")
    return re.sub(r"\s+", " ", text)


def classify_georgia_selector(value: str | None, *, allow_country_code: bool = True) -> str | None:
    """
    Map a search value to 'country', 'us_state', or None.

    Bare "Georgia" is the country selector (U.S. state jobs are still excluded).
    "Georgia (USA)" and the other state labels select the U.S. state.
    """
    token = _norm_token(value or "")
    if not token:
        return None
    if token == "ge" and not allow_country_code:
        return None
    if token in _US_SELECTOR:
        return GEORGIA_US_STATE
    if token in _COUNTRY_SELECTOR:
        return GEORGIA_COUNTRY
    return None


def _country_from_token(token: str) -> str | None:
    return _COUNTRY_TOKENS.get(_norm_token(token))


def _is_usa_token(token: str) -> bool:
    return _country_from_token(token) == "USA"


def _is_georgia_word(token: str) -> bool:
    return _norm_token(token) == "georgia"


def _state_from_token(token: str) -> str | None:
    norm = _norm_token(token)
    if norm in _US_STATE_NAMES:
        return _US_STATE_NAMES[norm]
    code = norm.upper()
    if len(code) == 2 and code in _US_STATE_CODES:
        return _US_STATE_CODES[code]
    return None


def _match_georgian_city(text: str) -> str | None:
    if not text:
        return None
    for alias, canonical in _GEORGIAN_ALIAS_TO_CITY:
        if re.search(
            rf"(?<![0-9A-Za-zა-ჰ]){re.escape(alias)}(?![0-9A-Za-zა-ჰ])",
            text,
            flags=re.IGNORECASE,
        ):
            return canonical
    return None


def _us_georgia_city_name(text: str) -> str | None:
    raw = _clip(text) or ""
    head = raw.split(",")[0].strip()
    head = re.sub(r"(?i)^(remote|hybrid)\s*[·\-|/]*\s*", "", head).strip()
    return _US_GEORGIA_CITY_BY_LOWER.get(head.lower())


def _is_non_place(city: str | None) -> bool:
    if not city or not city.strip():
        return True
    core = re.sub(r"(?i)^(remote|hybrid)\s*[·\-|/]*\s*", "", city).strip()
    token = _norm_token(core)
    if token in _NON_PLACES:
        return True
    # "Remote · " with nothing after it
    return token == "" or token in _NON_PLACES


def _strip_remote_prefix(city: str) -> str | None:
    core = re.sub(r"(?i)^(remote|hybrid)\s*[·\-|/]*\s*", "", city).strip()
    return _clip(core)


def _res(
    city: str | None,
    country: str | None,
    region: str | None,
    authoritative: bool,
    georgia: str | None,
) -> LocationResolution:
    return LocationResolution(_clip(city), country, region, authoritative, georgia)


def _disambiguate_bare(
    *,
    explicit_country: str | None,
    platform: str | None,
    context: str | None,
) -> LocationResolution:
    """The location string is only 'Georgia' (or Remote/Hybrid + Georgia)."""
    us_score = 0
    country_score = 0
    explicit_kind = classify_georgia_selector(explicit_country, allow_country_code=True)
    explicit_canon = _country_from_token(explicit_country or "")
    if explicit_canon == "USA" or explicit_kind == GEORGIA_US_STATE:
        us_score += 5
    elif explicit_kind == GEORGIA_COUNTRY:
        country_score += 2
    if platform in LOCAL_GEORGIA_PLATFORMS:
        country_score += 3
    elif platform == "employer" and explicit_kind == GEORGIA_COUNTRY:
        country_score += 2
    sample = (context or "")[:6000]
    has_us = bool(sample and _US_CONTEXT_RE.search(sample))
    has_country = bool(sample and _COUNTRY_CONTEXT_RE.search(sample))
    if has_us:
        us_score += 1
    if has_country:
        country_score += 1

    if us_score > country_score and us_score > 0:
        return _res(None, "USA", "Georgia", True, GEORGIA_US_STATE)
    if country_score > us_score and country_score > 0:
        return _res(None, "Georgia", None, True, GEORGIA_COUNTRY)
    # Not enough to pick a place. Keep the original text; do not file it as the country.
    return _res(None, None, None, True, GEORGIA_AMBIGUOUS)


_STATE_DASH_SITE_RE = re.compile(r"^(?P<state>[A-Za-z][A-Za-z .]*?)\s+-\s+(?P<rest>.+)$")


def _resolve_state_dash_site(
    text: str,
    *,
    explicit_country: str | None,
    platform: str | None,
    context: str | None,
) -> LocationResolution | None:
    """Workday style "<U.S. state> - <city | metro | Remote>", e.g. "Georgia - Atlanta Metro - Remote"."""
    match = _STATE_DASH_SITE_RE.match(text)
    if not match:
        return None
    state = _US_STATE_NAMES.get(_norm_token(match.group("state")))
    if not state:
        return None
    rest_parts = [part.strip() for part in re.split(r"\s+-\s+", match.group("rest")) if part.strip()]
    place_parts = [part for part in rest_parts if not _is_non_place(part)]
    city = re.sub(r"(?i)\s+metro$", "", place_parts[0]).strip() if place_parts else None
    if state != "Georgia":
        return _res(city, "USA", state, True, None)
    if city and _match_georgian_city(city):
        return _res(_match_georgian_city(city), "Georgia", None, True, GEORGIA_COUNTRY)
    if city and _us_georgia_city_name(city):
        return _res(_us_georgia_city_name(city), "USA", "Georgia", True, GEORGIA_US_STATE)
    if city:
        return _res(city, "USA", "Georgia", True, GEORGIA_US_STATE)
    return _disambiguate_bare(explicit_country=explicit_country, platform=platform, context=context)


def _resolve_sites(
    text: str,
    *,
    explicit_country: str | None,
    platform: str | None,
    context: str | None,
) -> LocationResolution | None:
    """
    Country/region for a multi-site list joined with " / " (Workday, Workable).

    Any U.S. site makes it a U.S. job, so "Georgia - Remote / Texas - Remote" is
    the state. Otherwise the first site with a country wins. City text is left
    to the caller so the remote filter still sees the full original string.
    """
    sites = [site.strip() for site in re.split(r"\s+/\s+", text) if site.strip()]
    if len(sites) < 2:
        return None
    resolved = [
        _resolve_segment(site, explicit_country=explicit_country, platform=platform, context=context)
        for site in sites[:30]
    ]
    us_sites = [site for site in resolved if site.country == "USA"]
    if us_sites:
        has_georgia_state = any(site.region == "Georgia" for site in us_sites) or any(
            site.georgia == GEORGIA_AMBIGUOUS for site in resolved
        )
        return _res(
            None,
            "USA",
            us_sites[0].region,
            True,
            GEORGIA_US_STATE if has_georgia_state else None,
        )
    for site in resolved:
        if site.country:
            return _res(None, site.country, site.region, True, site.georgia)
    if any(site.georgia == GEORGIA_AMBIGUOUS for site in resolved):
        return _res(None, None, None, True, GEORGIA_AMBIGUOUS)
    return None


def _resolve_segment(
    text: str,
    *,
    explicit_country: str | None,
    platform: str | None,
    context: str | None,
) -> LocationResolution:
    cleaned = text.strip()
    if not cleaned:
        return _res(None, None, None, False, None)

    dash_site = _resolve_state_dash_site(
        cleaned, explicit_country=explicit_country, platform=platform, context=context
    )
    if dash_site is not None:
        return dash_site

    if _GEORGIA_COUNTRY_RE.search(cleaned) and not _GEORGIA_US_RE.search(cleaned):
        city = _match_georgian_city(cleaned)
        return _res(city, "Georgia", None, True, GEORGIA_COUNTRY)

    if _GEORGIA_US_RE.search(cleaned):
        city = _us_georgia_city_name(cleaned)
        if city is None:
            left = re.split(r"(?i)\bgeorgia\b", cleaned, maxsplit=1)[0]
            left = _strip_remote_prefix(left) if left else None
            if left and not _is_non_place(left) and not _is_georgia_word(left):
                city = left
        return _res(city, "USA", "Georgia", True, GEORGIA_US_STATE)

    ge_city = _match_georgian_city(cleaned)
    parts = [part.strip() for part in cleaned.split(",") if part.strip()]
    trailing_code = parts[-1] if parts else ""
    code_key = _norm_token(trailing_code).upper()
    has_state_code = len(code_key) == 2 and code_key in _US_STATE_CODES
    if ge_city and not has_state_code and not (_USA_RE.search(cleaned) and not _is_georgia_word(cleaned)):
        # "United States" inside a Georgian-city string is unusual; a Georgian
        # city plus the word Georgia is the country. A trailing GA code is not.
        if not (len(parts) >= 2 and _is_usa_token(parts[-1]) and not ge_city):
            return _res(ge_city, "Georgia", None, True, GEORGIA_COUNTRY)

    if re.fullmatch(r"(?i)(?:north|south|metro|west)\s+georgia", cleaned):
        return _res(None, "USA", "Georgia", True, GEORGIA_US_STATE)

    if len(parts) >= 2:
        last = parts[-1]
        prev = parts[-2]
        if _is_usa_token(last):
            state = _state_from_token(prev)
            head_parts = parts[:-2] if state else parts[:-1]
            city = ", ".join(head_parts)
            if state == "Georgia" or _is_georgia_word(prev):
                city_name = _us_georgia_city_name(city) or (_clip(city) if city and not _is_georgia_word(city) else None)
                if city_name and _is_non_place(city_name):
                    return _disambiguate_bare(
                        explicit_country=explicit_country, platform=platform, context=context
                    )
                return _res(city_name, "USA", "Georgia", True, GEORGIA_US_STATE)
            if state:
                return _res(city, "USA", state, True, None)
            return _res(city, "USA", None, True, None)

        state = _state_from_token(last)
        city = ", ".join(parts[:-1])
        if state == "Georgia" or (_is_georgia_word(last) and state == "Georgia"):
            if _match_georgian_city(city):
                return _res(_match_georgian_city(city), "Georgia", None, True, GEORGIA_COUNTRY)
            if _is_non_place(city):
                return _disambiguate_bare(
                    explicit_country=explicit_country, platform=platform, context=context
                )
            city_name = _us_georgia_city_name(city) or _strip_remote_prefix(city) or _clip(city)
            return _res(city_name, "USA", "Georgia", True, GEORGIA_US_STATE)
        if state:
            return _res(_strip_remote_prefix(city) or city, "USA", state, True, None)
        if len(code_key) == 2 and code_key in _US_STATE_CODES:
            region = _US_STATE_CODES[code_key]
            kind = GEORGIA_US_STATE if code_key == "GA" else None
            return _res(city, "USA", region, True, kind)
        province = _CA_PROVINCE_CODES.get(code_key)
        if province:
            return _res(city, "Canada", province, True, None)
        country = _country_from_token(last)
        if country == "United Kingdom" and _norm_token(last) in _UK_NATIONS:
            return _res(city, "United Kingdom", None, True, None)
        if country:
            region = "Georgia" if country == "USA" and _is_georgia_word(prev) else None
            kind = GEORGIA_US_STATE if region == "Georgia" else None
            return _res(city, country, region, True, kind)
        if _norm_token(last) in _UK_NATIONS:
            return _res(city, "United Kingdom", None, True, None)

    if re.fullmatch(r"(?i)georgia", cleaned) or re.fullmatch(
        r"(?i)(?:remote|hybrid)\s*[·\-|/,]*\s*georgia", cleaned
    ):
        return _disambiguate_bare(explicit_country=explicit_country, platform=platform, context=context)

    if _USA_RE.search(cleaned) and not re.search(r"(?i)\bgeorgia\b", cleaned):
        city = _USA_RE.sub("", cleaned)
        city = _clip(city)
        if city and _is_non_place(city):
            city = None
        return _res(city, "USA", None, True, None)

    whole_country = _country_from_token(cleaned)
    if whole_country:
        return _res(None, whole_country, None, True, None)
    if _norm_token(cleaned) in _UK_NATIONS:
        return _res(None, "United Kingdom", None, True, None)

    return _res(cleaned, None, None, False, None)


def _apply_source_defaults(
    result: LocationResolution,
    *,
    explicit_country: str | None,
    platform: str | None,
    stored_country: str | None = None,
) -> LocationResolution:
    if result.georgia == GEORGIA_US_STATE:
        return result
    # A second save only has the city ("Atlanta") plus country USA. Do not let a
    # Georgian board default turn that city into the country of Georgia.
    # A different state already parsed ("Columbus, OH") is left alone.
    us_city = _us_georgia_city_name(result.city or "")
    stored_is_usa = _norm_token(stored_country or "") in {
        "usa",
        "us",
        "united states",
        "united states of america",
    }
    if (
        platform in LOCAL_GEORGIA_PLATFORMS
        and us_city
        and result.region in (None, "Georgia")
        and (stored_is_usa or result.country == "USA")
    ):
        return _res(us_city, "USA", "Georgia", True, GEORGIA_US_STATE)
    if platform in LOCAL_GEORGIA_PLATFORMS:
        if (
            result.country_authoritative
            and result.country not in (None, "Georgia")
            and result.georgia != GEORGIA_AMBIGUOUS
        ):
            return result
        return _res(result.city, "Georgia", None, True, GEORGIA_COUNTRY)

    if result.country_authoritative or result.country:
        return result

    explicit_kind = classify_georgia_selector(explicit_country, allow_country_code=True)
    if explicit_kind == GEORGIA_US_STATE or _country_from_token(explicit_country or "") == "USA":
        if result.georgia != GEORGIA_COUNTRY:
            return _res(result.city, "USA", result.region, True, result.georgia)
    if explicit_kind == GEORGIA_COUNTRY and result.georgia != GEORGIA_US_STATE:
        return _res(result.city, "Georgia", None, True, GEORGIA_COUNTRY)
    other = _country_from_token(explicit_country or "")
    if other and other != "USA":
        return _res(result.city, other, None, True, None)
    return result


def resolve_location(
    raw: str | None,
    *,
    explicit_country: str | None = None,
    platform: str | None = None,
    context: str | None = None,
    stored_country: str | None = None,
) -> LocationResolution:
    """
    Parse a job location into city, country, and region.

    `explicit_country` is a country supplied by the source feed, not a previous
    guess. `stored_country` is only used to repair rows the old parser labeled
    as the country of Georgia when the city is a U.S. Georgia city.
    """
    text = "" if raw is None else str(raw).strip()
    if not text:
        base = _res(None, None, None, False, None)
        base = _apply_source_defaults(
            base,
            explicit_country=explicit_country,
            platform=platform,
            stored_country=stored_country,
        )
        return _repair_stored_us_city(base, text, platform, stored_country)

    segments = [segment.strip() for segment in re.split(r"\s*;\s*", text) if segment.strip()]
    primary = segments[0] if segments else text
    sites = _resolve_sites(
        primary,
        explicit_country=explicit_country,
        platform=platform,
        context=context,
    )
    if sites is not None:
        result = _res(primary, sites.country, sites.region, sites.country_authoritative, sites.georgia)
    else:
        result = _resolve_segment(
            primary,
            explicit_country=explicit_country,
            platform=platform,
            context=context,
        )
    if not result.country_authoritative and not result.country and len(segments) > 1:
        full = _resolve_segment(
            text,
            explicit_country=explicit_country,
            platform=platform,
            context=context,
        )
        if full.country_authoritative or full.country:
            result = _res(result.city, full.country, full.region, full.country_authoritative, full.georgia)

    result = _apply_source_defaults(
        result,
        explicit_country=explicit_country,
        platform=platform,
        stored_country=stored_country,
    )
    return _repair_stored_us_city(result, primary, platform, stored_country)


def _repair_stored_us_city(
    result: LocationResolution,
    text: str,
    platform: str | None,
    stored_country: str | None,
) -> LocationResolution:
    """Atlanta + country 'Georgia' on an international board is the U.S. state."""
    if result.georgia in (GEORGIA_US_STATE, GEORGIA_COUNTRY) and result.country != "Georgia":
        return result
    if result.georgia == GEORGIA_COUNTRY and _match_georgian_city(text or result.city or ""):
        return result
    if platform in LOCAL_GEORGIA_PLATFORMS:
        return result
    if _norm_token(stored_country or "") != "georgia":
        return result
    city_name = _us_georgia_city_name(text or result.city or "")
    if not city_name:
        return result
    return _res(city_name, "USA", "Georgia", True, GEORGIA_US_STATE)


def parse_city_and_country(raw: str | None, **kwargs) -> tuple[str | None, str | None]:
    if raw is None or not str(raw).strip():
        return (None, None)
    resolved = resolve_location(raw, **kwargs)
    return (resolved.city, resolved.country)


# --- Search filters (applied to stored rows, including legacy mis-labels) ---

def _name_match_q(names: set[str] | frozenset[str]) -> Q:
    query = Q()
    for name in names:
        query |= Q(location__iexact=name)
        query |= Q(location__istartswith=f"{name},")
        query |= Q(location__istartswith=f"{name} ,")
    return query


def _georgia_country_text_q() -> Q:
    query = _name_match_q(set(GEORGIAN_CITY_NAMES))
    for city in ("Tbilisi", "Batumi", "Kutaisi", "Rustavi", "Zugdidi"):
        query |= Q(location__icontains=city)
    query |= Q(location__icontains="საქართველო")
    query |= Q(location__icontains="თბილისი")
    query |= Q(location__icontains="ბათუმი")
    query |= Q(location__icontains="Republic of Georgia")
    query |= Q(location__icontains="country of Georgia")
    query |= Q(location__icontains="Georgia, Country")
    query |= Q(location__icontains="Georgia (Country)")
    query |= Q(location__iexact="Georgia (Country)")
    return query


def _us_state_text_q() -> Q:
    """Location text that names the U.S. state, not the country."""
    comma_state = Q(location__iendswith=", Georgia") | Q(location__iendswith=",Georgia")
    comma_state = comma_state & ~_georgia_country_text_q()
    comma_state = comma_state & ~Q(location__istartswith="Remote")
    comma_state = comma_state & ~Q(location__istartswith="Hybrid")
    phrases = (
        Q(location__icontains="Georgia, USA")
        | Q(location__icontains="Georgia, US")
        | Q(location__icontains="Georgia, U.S")
        | Q(location__icontains="Georgia (USA)")
        | Q(location__icontains="Georgia (US)")
        | Q(location__icontains="Georgia, United States")
        | Q(location__icontains="Georgia, GA")
        | Q(location__icontains="state of Georgia")
        | Q(location__iendswith=", GA")
        | Q(location__iendswith=",GA")
        | Q(location__icontains=", GA,")
        | Q(location__icontains=",GA,")
    )
    # Workday multi-site lists: "Georgia - Remote / Texas - Remote", "Georgia - Atlanta Metro".
    workday_state = (
        Q(location__istartswith="Georgia - ") | Q(location__icontains="/ Georgia - ")
    ) & ~_georgia_country_text_q()
    legacy_cities = _name_match_q(set(_US_GEORGIA_CITIES)) & (
        Q(location_country__iexact="Georgia") | Q(location_region__iexact="Georgia")
    )
    return comma_state | phrases | workday_state | legacy_cities


def georgia_country_jobs_q() -> Q:
    """
    Every job in the country of Georgia, and nothing else.

    Georgian boards (and employer posts set to Georgia) count by source. Jobs from
    international ATS feeds also need the location text to name the country (a
    Georgian city or "Georgia, Country"); their stored country alone is not enough,
    because older rows labeled every "Georgia" (e.g. Salesforce "Georgia - Remote")
    as the country.
    """
    no_country = Q(location_country__isnull=True) | Q(location_country="")
    local_boards = Q(platform__in=LOCAL_GEORGIA_PLATFORMS) & (
        Q(location_country__iexact="Georgia") | no_country
    )
    employer_posts = Q(platform="employer") & Q(location_country__iexact="Georgia")
    international = (
        ~Q(platform__in=TRUSTED_GEORGIA_COUNTRY_PLATFORMS)
        & Q(location_country__iexact="Georgia")
        & _georgia_country_text_q()
    )
    return (
        (local_boards | employer_posts | international)
        & ~_us_state_text_q()
        & ~Q(location_region__iexact="Georgia")
    )


def georgia_us_state_jobs_q() -> Q:
    """Jobs in the U.S. state of Georgia. Country-of-Georgia rows never match."""
    proven_country = _georgia_country_text_q()
    structured = Q(location_region__iexact="Georgia") & (
        Q(location_country__iexact="USA") | Q(location_country__isnull=True) | Q(location_country="")
    )
    return (structured | _us_state_text_q()) & ~proven_country


def legacy_country_q(code: str) -> Q:
    """Previous country filter for every country other than the Georgia clash."""
    variations = {
        "us": ["usa", "united states", "united states of america", "us"],
        "uk": ["united kingdom", "england", "britain", "uk"],
        "ca": ["canada", "ca"],
        "de": ["germany", "deutschland"],
        "fr": ["france"],
        "au": ["australia"],
        "in": ["india"],
        "nl": ["netherlands", "holland"],
    }
    code_l = (code or "").strip().lower()
    query = Q(location__icontains=code_l) | Q(location_country__icontains=code_l)
    for variant in variations.get(code_l, []):
        query |= Q(location__icontains=variant) | Q(location_country__icontains=variant)
    return query


def q_for_country_param(value: str) -> Q:
    kind = classify_georgia_selector(value, allow_country_code=True)
    if kind == GEORGIA_COUNTRY:
        return georgia_country_jobs_q()
    if kind == GEORGIA_US_STATE:
        return georgia_us_state_jobs_q()
    return legacy_country_q(value)


def coalesce_georgia_filter_values(values: list[str]) -> list[str]:
    """Stick split pieces of 'Georgia, USA' / 'Georgia, Country' back together."""
    merged: list[str] = []
    index = 0
    while index < len(values):
        if index + 1 < len(values):
            combined = f"{values[index]}, {values[index + 1]}"
            if classify_georgia_selector(combined, allow_country_code=True):
                merged.append(combined)
                index += 2
                continue
        merged.append(values[index])
        index += 1
    return merged


def q_for_place_param(value: str) -> Q | None:
    """Georgia-aware filter for city/location params. None → caller uses substring match."""
    kind = classify_georgia_selector(value, allow_country_code=False)
    if kind == GEORGIA_COUNTRY:
        return georgia_country_jobs_q()
    if kind == GEORGIA_US_STATE:
        return georgia_us_state_jobs_q()
    return None
