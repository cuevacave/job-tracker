"""Where is a job, and what kind of place is that for you?

Turns a job's Location text ("Cambridge, MA", "Greater Boston", "Hybrid - Denver, CO 80202",
"Boston, MA; New York, NY (+3 more)") into coordinates, then sorts it into one of:
  Home       within your commute radius of home
  Area       inside one of your preferred areas (a metro + radius, or a whole state)
  Region     another place in your preferred region (states list)
  Elsewhere  anywhere else
No AI involved: it's a lookup table plus distance math, so it's exact and instant.

Place data: a small built-in table (major cities, suburbs, metro nicknames) plus, once Setup has run,
every US town from the free 'zipcodes' package, cached in app/places.json.
Run  python geo.py --build  to (re)build the cache, or  python geo.py "Cambridge, MA"  to test a location.
"""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CACHE = APP_DIR / "places.json"

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA",
    "michigan": "MI", "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY", "puerto rico": "PR",
}
CODES = set(STATES.values())

# (city, state, lat, lon): metro centers, common office suburbs and big cities. Used even without the full data.
BUILTIN = """
Colorado Springs,CO,38.834,-104.821|Denver,CO,39.739,-104.990|Boulder,CO,40.015,-105.271|Aurora,CO,39.729,-104.832
Lakewood,CO,39.705,-105.081|Fort Collins,CO,40.585,-105.084|Pueblo,CO,38.254,-104.609|Castle Rock,CO,39.372,-104.856
Englewood,CO,39.648,-104.988|Littleton,CO,39.613,-105.017|Golden,CO,39.756,-105.221|Broomfield,CO,39.921,-105.087
Greenwood Village,CO,39.617,-104.951|Monument,CO,39.092,-104.873|Fountain,CO,38.682,-104.701|Centennial,CO,39.579,-104.877
Westminster,CO,39.837,-105.037|Louisville,CO,39.978,-105.132|Longmont,CO,40.167,-105.102|Lone Tree,CO,39.552,-104.886
Pittsburgh,PA,40.441,-79.996|Canonsburg,PA,40.262,-80.187|Cranberry Township,PA,40.685,-80.107
Philadelphia,PA,39.953,-75.165|King of Prussia,PA,40.089,-75.396|Malvern,PA,40.036,-75.514|Conshohocken,PA,40.079,-75.302
Wayne,PA,40.044,-75.388|Radnor,PA,40.046,-75.360|Harrisburg,PA,40.274,-76.884|Allentown,PA,40.608,-75.490
Camden,NJ,39.926,-75.120|Cherry Hill,NJ,39.935,-75.031|Wilmington,DE,39.739,-75.540|Dover,DE,39.158,-75.524
Newark,NJ,40.736,-74.172|Jersey City,NJ,40.728,-74.078|Hoboken,NJ,40.744,-74.032|Princeton,NJ,40.357,-74.667
Trenton,NJ,40.217,-74.743|Parsippany,NJ,40.858,-74.426|Morristown,NJ,40.797,-74.481|Edison,NJ,40.519,-74.412
New Brunswick,NJ,40.486,-74.452|Iselin,NJ,40.575,-74.322|Florham Park,NJ,40.788,-74.388
New York,NY,40.713,-74.006|New York City,NY,40.713,-74.006|Manhattan,NY,40.783,-73.971|Brooklyn,NY,40.678,-73.944
Queens,NY,40.728,-73.795|Bronx,NY,40.845,-73.865|Staten Island,NY,40.579,-74.151|Long Island City,NY,40.744,-73.949
White Plains,NY,41.034,-73.763|Yonkers,NY,40.931,-73.899|Tarrytown,NY,41.076,-73.859|Purchase,NY,41.041,-73.715
Albany,NY,42.653,-73.756|Rochester,NY,43.157,-77.616|Buffalo,NY,42.886,-78.878|Syracuse,NY,43.049,-76.147
Hartford,CT,41.764,-72.685|New Haven,CT,41.308,-72.928|Stamford,CT,41.053,-73.539|Norwalk,CT,41.118,-73.408
Greenwich,CT,41.026,-73.628|Bridgeport,CT,41.186,-73.195|Danbury,CT,41.394,-73.454|Waterbury,CT,41.558,-73.051
Boston,MA,42.360,-71.059|Cambridge,MA,42.374,-71.110|Somerville,MA,42.388,-71.100|Waltham,MA,42.376,-71.236
Burlington,MA,42.505,-71.196|Lexington,MA,42.447,-71.225|Quincy,MA,42.253,-71.002|Newton,MA,42.337,-71.209
Needham,MA,42.281,-71.236|Woburn,MA,42.479,-71.152|Framingham,MA,42.279,-71.416|Worcester,MA,42.263,-71.802
Andover,MA,42.658,-71.137|Marlborough,MA,42.346,-71.552|Bedford,MA,42.491,-71.276|Providence,RI,41.824,-71.413
Washington,DC,38.907,-77.037|Arlington,VA,38.880,-77.107|Alexandria,VA,38.805,-77.047|Reston,VA,38.969,-77.341
Tysons,VA,38.919,-77.231|McLean,VA,38.934,-77.177|Herndon,VA,38.970,-77.386|Fairfax,VA,38.846,-77.306
Chantilly,VA,38.894,-77.431|Ashburn,VA,39.044,-77.487|Bethesda,MD,38.981,-77.100|Rockville,MD,39.084,-77.153
Silver Spring,MD,38.991,-77.026|Gaithersburg,MD,39.143,-77.202|Columbia,MD,39.204,-76.861|Baltimore,MD,39.290,-76.612
Annapolis,MD,38.978,-76.492|Richmond,VA,37.541,-77.436|Norfolk,VA,36.851,-76.286|Virginia Beach,VA,36.853,-75.978
Chicago,IL,41.878,-87.630|Evanston,IL,42.045,-87.688|Naperville,IL,41.786,-88.147|Schaumburg,IL,42.033,-88.083
Oak Brook,IL,41.833,-87.929|Deerfield,IL,42.171,-87.845|Northbrook,IL,42.128,-87.829|Rosemont,IL,41.995,-87.884
Downers Grove,IL,41.809,-88.011|Itasca,IL,41.975,-88.007|Lake Forest,IL,42.259,-87.841|Hoffman Estates,IL,42.043,-88.080
Aurora,IL,41.761,-88.320|Joliet,IL,41.525,-88.082
San Francisco,CA,37.775,-122.419|Sunnyvale,CA,37.369,-122.036|San Jose,CA,37.338,-121.886|Mountain View,CA,37.386,-122.084
Palo Alto,CA,37.442,-122.143|Santa Clara,CA,37.354,-121.955|Cupertino,CA,37.323,-122.032|Menlo Park,CA,37.453,-122.182
Redwood City,CA,37.485,-122.236|San Mateo,CA,37.563,-122.326|Oakland,CA,37.804,-122.271|Berkeley,CA,37.872,-122.273
Fremont,CA,37.548,-121.989|Milpitas,CA,37.428,-121.907|South San Francisco,CA,37.655,-122.408|Emeryville,CA,37.831,-122.285
Pleasanton,CA,37.662,-121.875|San Ramon,CA,37.780,-121.978|Foster City,CA,37.559,-122.271|Los Gatos,CA,37.227,-121.975
Walnut Creek,CA,37.910,-122.065|Sacramento,CA,38.582,-121.494
Los Angeles,CA,34.052,-118.244|Santa Monica,CA,34.019,-118.491|Pasadena,CA,34.148,-118.144|Burbank,CA,34.181,-118.309
Glendale,CA,34.143,-118.255|Irvine,CA,33.684,-117.826|Long Beach,CA,33.770,-118.194|El Segundo,CA,33.919,-118.416
Culver City,CA,34.021,-118.396|Torrance,CA,33.836,-118.341|Anaheim,CA,33.836,-117.915|Costa Mesa,CA,33.641,-117.919
Newport Beach,CA,33.619,-117.929|Santa Ana,CA,33.746,-117.868|Playa Vista,CA,33.976,-118.418|Thousand Oaks,CA,34.170,-118.838
San Diego,CA,32.716,-117.161|Carlsbad,CA,33.158,-117.351|La Jolla,CA,32.833,-117.271|Chula Vista,CA,32.640,-117.084
Escondido,CA,33.119,-117.086|Oceanside,CA,33.196,-117.380
Seattle,WA,47.606,-122.332|Bellevue,WA,47.610,-122.201|Redmond,WA,47.674,-122.121|Kirkland,WA,47.677,-122.206
Bothell,WA,47.760,-122.205|Tacoma,WA,47.253,-122.444|Everett,WA,47.979,-122.202|Renton,WA,47.483,-122.217
Issaquah,WA,47.530,-122.033|Kent,WA,47.381,-122.235|Lynnwood,WA,47.821,-122.315|Tukwila,WA,47.474,-122.261
Austin,TX,30.267,-97.743|Dallas,TX,32.777,-96.797|Houston,TX,29.760,-95.370|Atlanta,GA,33.749,-84.388
Charlotte,NC,35.227,-80.843|Raleigh,NC,35.780,-78.639|Miami,FL,25.762,-80.192|Phoenix,AZ,33.448,-112.074
Salt Lake City,UT,40.761,-111.891|Minneapolis,MN,44.978,-93.265|Columbus,OH,39.961,-82.999|Detroit,MI,42.331,-83.046
Nashville,TN,36.163,-86.781|Portland,OR,45.515,-122.679|Albuquerque,NM,35.084,-106.651|Cheyenne,WY,41.140,-104.820
"""
# Metro nicknames used by LinkedIn and others -> a representative city
ALIASES = {
    "greater boston": ("boston", "MA"), "boston metro": ("boston", "MA"),
    "new york city metropolitan area": ("new york", "NY"), "new york metropolitan area": ("new york", "NY"),
    "greater new york": ("new york", "NY"), "nyc": ("new york", "NY"), "new york city": ("new york", "NY"),
    "san francisco bay area": ("sunnyvale", "CA"), "bay area": ("sunnyvale", "CA"), "silicon valley": ("sunnyvale", "CA"),
    "sf bay area": ("sunnyvale", "CA"), "greater chicago area": ("chicago", "IL"), "chicagoland": ("chicago", "IL"),
    "washington dc-baltimore area": ("washington", "DC"), "washington dc metro area": ("washington", "DC"),
    "greater washington": ("washington", "DC"), "dmv": ("washington", "DC"), "washington dc": ("washington", "DC"),
    "washington d c": ("washington", "DC"), "greater philadelphia": ("philadelphia", "PA"),
    "greater pittsburgh region": ("pittsburgh", "PA"), "greater pittsburgh": ("pittsburgh", "PA"),
    "los angeles metropolitan area": ("los angeles", "CA"), "greater los angeles": ("los angeles", "CA"),
    "greater san diego area": ("san diego", "CA"), "denver metropolitan area": ("denver", "CO"),
    "greater denver area": ("denver", "CO"), "colorado springs metropolitan area": ("colorado springs", "CO"),
    "greater seattle area": ("seattle", "WA"), "seattle metropolitan area": ("seattle", "WA"),
    "greater hartford": ("hartford", "CT"), "greater new haven": ("new haven", "CT"),
}


# ------------------------------------------------------------------ data
_places = None


def places() -> dict:
    """{"city|ST": (lat, lon)}"""
    global _places
    if _places is not None:
        return _places
    p = {}
    if CACHE.exists():
        try:
            p = {k: tuple(v) for k, v in json.loads(CACHE.read_text()).items()}
        except Exception:
            p = {}
    if not p:
        p = build(write=False) or {}
    for line in BUILTIN.strip().splitlines():
        for item in line.split("|"):
            c, st, la, lo = item.split(",")
            p[f"{c.lower()}|{st}"] = (float(la), float(lo))
    _places = p
    return p


def build(write=True) -> dict | None:
    """Build the full US town table from the free 'zipcodes' package (installed by Setup)."""
    try:
        import zipcodes
    except ImportError:
        return None
    try:
        rows = zipcodes.list_all()
    except Exception:
        return None
    acc = {}
    for z in rows:
        try:
            st = str(z.get("state") or "").upper()
            la = float(z.get("lat") or z.get("latitude"))
            lo = float(z.get("long") or z.get("lng") or z.get("longitude"))
        except (TypeError, ValueError):
            continue
        names = [z.get("city")] + list(z.get("acceptable_cities") or [])
        for n in names:
            if not n or st not in CODES:
                continue
            k = f"{str(n).strip().lower()}|{st}"
            a = acc.setdefault(k, [0.0, 0.0, 0])
            a[0] += la
            a[1] += lo
            a[2] += 1
    out = {k: (round(a[0] / a[2], 4), round(a[1] / a[2], 4)) for k, a in acc.items() if a[2]}
    if write and out:
        CACHE.write_text(json.dumps(out, separators=(",", ":")))
    return out


# ------------------------------------------------------------------ parsing
def miles(a, b) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    dp, dl = p2 - p1, math.radians(lo2 - lo1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(h))


def _state_code(s: str):
    s = s.strip().strip(".").lower().replace(".", "")
    if s.upper() in CODES:
        return s.upper()
    return STATES.get(s)


def _clean(part: str) -> str:
    s = part.lower()
    s = re.sub(r"\(.*?\)", " ", s)  # (+3 more), (hybrid)
    s = re.sub(r"\b(remote|hybrid|on-?site|in[- ]office|onsite)\b\s*[-–:|]?\s*", " ", s)
    s = re.sub(r"\b\d{5}(-\d{4})?\b", " ", s)  # zip codes
    s = re.sub(r",?\s*\b(united states( of america)?|usa|u\.s\.a?\.?)\b", " ", s)
    s = s.replace("d.c.", "dc").replace("st.", "saint").replace("ft.", "fort")
    s = re.sub(r"\s+", " ", s).strip(" ,-–|")
    return s


def locate(text: str) -> list:
    """Return candidate places: dicts with state and (when known) point=(lat, lon)."""
    out = []
    if not text:
        return out
    P = places()
    for part in re.split(r";|\s/\s|\||\n|\bor\b|\s&\s", str(text)):
        s = _clean(part)
        if not s:
            continue
        hit = None
        for alias, (c, st) in ALIASES.items():
            if s == alias or s.startswith(alias + " ") or s.endswith(" " + alias) or f" {alias} " in f" {s} ":
                hit = {"state": st, "point": P.get(f"{c}|{st}"), "name": f"{c.title()}, {st}"}
                break
        if not hit:
            m = re.match(r"^(.*?),\s*([a-z .]+?)(?:,.*)?$", s)
            if m:
                city, st = m.group(1).strip(), _state_code(m.group(2))
                if st:
                    city = re.sub(r"^(greater|metro|downtown)\s+", "", city)
                    pt = P.get(f"{city}|{st}") or P.get(f"{city.replace('saint', 'st')}|{st}")
                    hit = {"state": st, "point": pt, "name": f"{city.title()}, {st}"}
        if not hit:
            st = _state_code(s)
            if st:
                hit = {"state": st, "point": None, "name": st}
        if not hit:  # bare city name with no state ("Boston"): accept only if it's unambiguous in the table
            matches = [k for k in P if k.split("|")[0] == s]
            if len(matches) > 1:
                major = [k for k in matches if f"{k.split('|')[0].title()},{k.split('|')[1]}," in BUILTIN]
                matches = major if len(major) == 1 else matches
            if len(matches) == 1:
                c, st = matches[0].split("|")
                hit = {"state": st, "point": P[matches[0]], "name": f"{c.title()}, {st}"}
        if hit:
            out.append(hit)
    return out


FOREIGN = re.compile(
    r"\b(germany|deutschland|switzerland|schweiz|suisse|france|ireland|united kingdom|england|scotland|wales|netherlands|"
    r"belgium|italy|italia|spain|españa|portugal|poland|polska|czech|austria|österreich|sweden|denmark|norway|finland|"
    r"israel|india|china|japan|korea|singapore|malaysia|philippines|vietnam|thailand|australia|new zealand|mexico|méxico|"
    r"canada|brazil|brasil|argentina|chile|colombia|costa rica|puerto rico|dominican republic|south africa|"
    r"ontario|quebec|québec|british columbia|alberta|toronto|montreal|vancouver|london|paris|munich|münchen|berlin|"
    r"dublin|galway|shanghai|beijing|tokyo|bangalore|bengaluru|hyderabad|tel aviv|zug|zurich|zürich|"
    # places that host many US companies' foreign R&D/manufacturing sites (seen with no country in the posting)
    r"kfar saba|caesarea|yokneam|yoqneam|herzliya|haifa|petah tikva|petach tikva|netanya|ra'?anana|rehovot|jerusalem|"
    r"beer[- ]?sheva|beersheba|hod hasharon|or yehuda|limerick|shannon|cork|athlone|eindhoven|leuven|penang|suzhou|"
    r"shenzhen|hsinchu|taipei|taiwan|hong kong|seoul|osaka|pune|chennai|mumbai|gurgaon|gurugram|noida|kuala lumpur|"
    r"ho chi minh|tijuana|juarez|juárez|monterrey|guadalajara|heredia|alajuela|cartago|são paulo|sao paulo|brno|"
    r"krak[oó]w|wroc[lł]aw|budapest|hungary|romania|bucharest|erlangen|tuttlingen|stuttgart|grenoble|copenhagen|"
    r"stockholm|helsinki|lausanne|basel|milano)\b"
    r"|\((?:m/w/d|w/m/d|f/m/d|m/f/d|h/f|f/h|m/w|w/m)\)", re.I)


COUNTRY_CODES = re.compile(r"(?<![\w-])(UK|GB|GBR|DEU|IRL|IE|CHE|CH|NLD|NL|FRA|FR|ITA|ESP|POL|AUT|SWE|DNK|BEL|ISR|IND|"
                           r"CHN|CN|JPN|JP|KOR|SGP|SG|MYS|AUS|NZL|MEX|MX|CAN|CA-ON|CA-QC|CA-BC|BRA|BR|PRI|CRI)(?![\w-])")
UK_PLACES = re.compile(r"\b(hertfordshire|watford|hampshire|surrey|kent|essex|berkshire|oxfordshire|cambridgeshire|"
                       r"leeds|manchester, uk|edinburgh|glasgow|cardiff|belfast|bristol, uk|reading, uk)\b", re.I)


def is_foreign(text: str, location: str = "") -> bool:
    """Postings outside the US (country names/codes, big foreign cities, German/French job-ad markers like (m/w/d))."""
    t = f"{text or ''} {location or ''}"
    marker = re.search(r"\((?:m/w/d|w/m/d|f/m/d|m/f/d|h/f|f/h)\)", t, re.I)
    if re.search(r"\b(united states|usa|u\.s\.)\b", t, re.I) and not marker:
        return False
    return bool(marker or FOREIGN.search(t) or UK_PLACES.search(t) or COUNTRY_CODES.search(str(location or "")))


# ------------------------------------------------------------------ classification
RANK = {"Home": 4, "Area": 3, "Region": 2, "Elsewhere": 1}


def classify(location: str, cfg: dict) -> dict:
    """cfg: home (lat,lon) or None, home_radius, areas [ {name, center:(lat,lon)|None, state:str|None, radius, bonus} ],
    region (set of state codes). Returns {area, area_type, miles, area_bonus}."""
    cands = locate(location)
    if not cands:
        if location and is_foreign("", location):
            return {"area": "Outside US", "area_type": "Elsewhere", "miles": None, "area_bonus": None}
        return {"area": "?" if location and not re.search(r"\bremote\b", str(location), re.I) else None,
                "area_type": None, "miles": None, "area_bonus": None}
    best = None
    for c in cands:
        pt, st = c.get("point"), c.get("state")
        res = None
        if pt and cfg.get("home"):
            d = miles(pt, cfg["home"])
            if d <= cfg.get("home_radius", 40):
                res = {"area": f"Home · {d:.0f} mi", "area_type": "Home", "miles": round(d, 1), "area_bonus": None}
        if not res:
            for a in cfg.get("areas", []):
                if a.get("state") and st == a["state"]:
                    res = {"area": a["name"], "area_type": "Area", "miles": None, "area_bonus": a.get("bonus", 0)}
                elif pt and a.get("center"):
                    d = miles(pt, a["center"])
                    if d <= a.get("radius", 35):
                        res = {"area": f"{a['name']} · {d:.0f} mi", "area_type": "Area", "miles": round(d, 1),
                               "area_bonus": a.get("bonus", 0)}
                if res:
                    break
        if not res and st in cfg.get("region", set()):
            res = {"area": f"Region · {c['name']}", "area_type": "Region", "miles": None, "area_bonus": None}
        if not res and st:
            res = {"area": f"Elsewhere · {c['name']}", "area_type": "Elsewhere", "miles": None, "area_bonus": None}
        if res and (best is None or (RANK[res["area_type"]], res.get("area_bonus") or 0, -(res.get("miles") or 0))
                    > (RANK[best["area_type"]], best.get("area_bonus") or 0, -(best.get("miles") or 0))):
            best = res
    return best or {"area": "?", "area_type": None, "miles": None, "area_bonus": None}


def point_for(text: str):
    c = locate(text)
    return c[0]["point"] if c and c[0].get("point") else None


def config(settings: dict, areas: list) -> dict:
    """Turn Settings + Areas rows into what classify() needs."""
    cfg = {"home": point_for(settings.get("home_city") or ""),
           "home_radius": float(settings.get("home_radius") or 40),
           "region": {s.strip().upper() for s in str(settings.get("region_states") or "").split(",") if s.strip()},
           "areas": []}
    for a in areas:
        center = str(a.get("center") or "").strip()
        if not center:
            continue
        st = _state_code(center)
        if st and "," not in center:
            cfg["areas"].append({"name": a.get("name") or center, "state": st, "center": None,
                                 "radius": None, "bonus": a.get("bonus") or 0})
        else:
            cfg["areas"].append({"name": a.get("name") or center, "state": None, "center": point_for(center),
                                 "radius": float(a.get("radius") or 35), "bonus": a.get("bonus") or 0,
                                 "_missing": point_for(center) is None})
    return cfg


if __name__ == "__main__":
    if "--build" in sys.argv:
        out = build(write=True)
        print(f"  Place data: {len(out):,} US towns ready." if out else "  Place data: package not available; using the built-in list.")
        sys.exit(0)
    for t in sys.argv[1:]:
        print(t, "->", locate(t))
