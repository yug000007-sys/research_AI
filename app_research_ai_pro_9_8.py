import csv
import html
import io
import re
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
import streamlit as st

st.set_page_config(page_title="Research AI Pro - Top 5", layout="wide")

FIELDS = [
    "Company", "Address", "City", "State", "Zip", "Country", "PhoneResearch",
    "Website", "SIC", "NAICS", "NoOfEmployees(This site only)",
    "LineOfBusiness", "ParentName", "Confidence", "SourceURL", "Remarks"
]

US_STATES = {
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO",
    "connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID",
    "illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA",
    "maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN",
    "mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV",
    "new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY",
    "north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR",
    "pennsylvania":"PA","rhode island":"RI","south carolina":"SC","south dakota":"SD",
    "tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA",
    "washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY",
}
US_ABBR = set(US_STATES.values())
CA_PROV = {"ontario":"ON","quebec":"QC","québec":"QC","british columbia":"BC","alberta":"AB","manitoba":"MB","saskatchewan":"SK","nova scotia":"NS"}
CA_ABBR = set(CA_PROV.values())
AU_STATES = {"new south wales":"NSW","nsw":"NSW","queensland":"QLD","qld":"QLD","victoria":"VIC","vic":"VIC","south australia":"SA","western australia":"WA","tasmania":"TAS","northern territory":"NT","australian capital territory":"ACT"}
DIAL_CODES = {"usa":"+1","us":"+1","united states":"+1","united states of america":"+1","canada":"+1","italy":"+39","australia":"+61","japan":"+81","vietnam":"+84","viet nam":"+84","germany":"+49","france":"+33","uae":"+971","united arab emirates":"+971","china":"+86","india":"+91","spain":"+34","netherlands":"+31","singapore":"+65","united kingdom":"+44","uk":"+44","mexico":"+52","brazil":"+55"}
BAD_WEBSITE_DOMAINS = ["google","duckduckgo","facebook","linkedin","instagram","youtube","bloomberg","zoominfo","dnb","apollo","rocketreach","signalhire","lusha","volza","panjiva","importgenius","allbiz","yellowpages","chamberofcommerce","manta","buzzfile","opencorporates","paacc","macraesbluebook","kompass","processregister","craft.co","visualvisitor","contactout","datanyze","crunchbase","yelp","mapquest","soopage","ca.soopage","411","canada411","find-open","cybo","hotfrog","salespider"]
DIRECTORY_HINTS = ["yellowpages","chamberofcommerce","allbiz","manta","buzzfile","paacc","macraesbluebook","kompass","processregister","azom","craft.co","contactout","opencorporates","yelp","mapquest","soopage","ca.soopage","411","canada411","find-open","cybo","hotfrog","salespider"]
STREET_WORDS = "Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Place|Pl|Parkway|Pkwy|Circle|Cir|Highway|Hwy|Terrace|Ter|Square|Sq|Via|Viale|Piazza|Corso|Strada|Building|Suite|Unit|Floor|Industrial|Village"

KNOWN = {
    ("chromalox sales", "usa"): {"Company":"Chromalox Sales","Address":"103 Gamma Drive","City":"Pittsburgh","State":"PA","Zip":"15238","Country":"USA","PhoneResearch":"412-967-3800","Website":"www.chromalox.com","SIC":"3567","NAICS":"333414","NoOfEmployees(This site only)":"Not publicly disclosed","LineOfBusiness":"Industrial heating and thermal systems.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=Chromalox+Sales+103+Gamma+Drive+Pittsburgh+PA+15238","Remarks":"Known high-confidence match. Review before saving."},
    ("c&r electronic services", "australia"): {"Company":"C&R Electronic Services","Address":"30 Straits Ave","City":"South Granville","State":"NSW","Zip":"2142","Country":"Australia","PhoneResearch":"+61 2 9748 6030","Website":"Needs research","SIC":"3679","NAICS":"334418","NoOfEmployees(This site only)":"Needs research","LineOfBusiness":"Electronic equipment manufacturing / electronic services.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=C%26R+Electronic+Services+30+Straits+Ave+South+Granville+NSW+2142","Remarks":"Known high-confidence match. Review before saving."}
}

def clean(value):
    return str(value or "").strip()

def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()

def digits(value):
    return re.sub(r"\D+", "", clean(value))

def has_value(value):
    value = clean(value)
    return bool(value) and value != "Needs research"

def clear_final_editor_state():
    for field in FIELDS:
        st.session_state.pop(f"edit_{field}", None)

def reset_research_page_state(clear_inputs=False):
    st.session_state.current = None
    st.session_state.raw_candidates = []
    st.session_state.parsed_candidates = []
    st.session_state.rejected_candidates = []
    clear_final_editor_state()
    if clear_inputs:
        for key in ["input_company", "input_address", "input_city", "input_state", "input_zip", "input_country", "manual_paste"]:
            st.session_state[key] = ""

def google_url(query):
    return "https://www.google.com/search?q=" + quote_plus(query)

def maps_url(query):
    return "https://www.google.com/maps/search/" + quote_plus(query)

def unwrap_url(url):
    url = html.unescape(clean(url))
    if url.startswith("//"):
        url = "https:" + url
    try:
        qs = parse_qs(urlparse(url).query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
        if "url" in qs and qs["url"]:
            return unquote(qs["url"][0])
    except Exception:
        pass
    return url

def domain(url):
    try:
        return urlparse(unwrap_url(url)).netloc.lower().replace("www.", "")
    except Exception:
        return ""

def format_country(country):
    c = norm(country)
    if c in ["usa", "us", "united states", "united states of america"]:
        return "USA"
    if c == "viet nam":
        return "Vietnam"
    return clean(country) or "Needs research"

def format_state(state, country):
    state = clean(state)
    if not state or state == "Needs research":
        return "Needs research"
    c = norm(country)
    up = state.upper().replace(".", "")
    if c in ["usa", "us", "united states", "united states of america"]:
        if up in US_ABBR:
            return up
        return US_STATES.get(state.lower(), state)
    if c == "canada":
        if up in CA_ABBR:
            return up
        return CA_PROV.get(state.lower(), state)
    if c == "australia":
        return AU_STATES.get(state.lower(), state)
    return state

def format_phone(phone, country):
    phone = clean(phone)
    if not phone or phone == "Needs research":
        return "Needs research"
    d = digits(phone)
    if len(d) < 7:
        return "Needs research"
    c = norm(country)
    if c in ["usa", "us", "united states", "united states of america", "canada"]:
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return phone
    if phone.startswith("+"):
        return re.sub(r"\s+", " ", phone)
    code = DIAL_CODES.get(c, "")
    if code:
        code_digits = digits(code)
        if d.startswith(code_digits):
            return "+" + d[:len(code_digits)] + " " + d[len(code_digits):]
        if d.startswith("0"):
            d = d[1:]
        return f"{code} {d}"
    return phone

def format_website(url):
    url = unwrap_url(clean(url))
    if not url or url == "Needs research":
        return "Needs research"
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    d = domain(url)
    if not d or "google" in d or "duckduckgo" in d:
        return "Needs research"
    return "www." + d

def is_bad_website_domain(url):
    d = domain(url)
    return any(bad in d for bad in BAD_WEBSITE_DOMAINS)

def is_official_website(url, company):
    d = domain(url)
    if not d or is_bad_website_domain(url):
        return False
    tokens = [t for t in norm(company).split() if len(t) >= 4 and t not in ["sales", "office", "company", "corp", "inc", "ltd", "llc", "group"]]
    return any(t in d for t in tokens)

def looks_like_bad_company_name(name):
    n = clean(name)
    if not n or n == "Needs research":
        return True
    if len(digits(n)) >= 7:
        return True
    low = n.lower()
    bad_words = ["address", "phone", "tel", "fax", "zipcode", "postal", "profile", "login", "download", "company search"]
    if any(w in low for w in bad_words):
        return True
    if re.search(r"\b\d{1,6}\s+[A-Za-z0-9 .'-]+\s+(?:" + STREET_WORDS + r")\b", n, flags=re.I):
        return True
    if len(n) > 70:
        return True
    return False

def clean_company_from_title(title, input_company=""):
    input_company = clean(input_company)
    if input_company and not looks_like_bad_company_name(input_company):
        return input_company
    title = clean(title)
    if not title:
        return "Needs research"
    title = html.unescape(title)
    title = re.split(r"\s+[-|]\s+", title)[0].strip()
    title = re.sub(r"\bCompany Profile\b.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bSales, Contacts.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bPhone, Email.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bOffice Locations.*", "", title, flags=re.I).strip()
    title = re.sub(r"\b(?:Ltd|Inc|LLC|Limited|Corp|Corporation)\.?\s*,?\s*\d[\d\s().-]{6,}$", lambda m: m.group(0).split(',')[0], title, flags=re.I)
    title = re.split(r",\s*\d|\s+\d{3}[- .]\d{3}[- .]\d{4}", title)[0]
    title = title.strip(" ,-;:")
    if looks_like_bad_company_name(title):
        return input_company or "Needs research"
    return title

def best_company_name(input_company, candidate=None, website=""):
    if clean(input_company) and not looks_like_bad_company_name(input_company):
        return clean(input_company)
    candidate = candidate or {}
    title_name = clean_company_from_title(candidate.get("title", ""), "")
    if not looks_like_bad_company_name(title_name):
        return title_name
    d = domain(website)
    if d:
        token = d.split(".")[0]
        if token and len(token) >= 3 and token not in ["www", "global", "group"]:
            return token.replace("-", " ").title()
    return "Needs research"

def clean_address(address):
    address = clean(address)
    if not address or address == "Needs research":
        return "Needs research"
    address = html.unescape(address)
    address = re.sub(r"\s+", " ", address)
    address = re.sub(r"^(Address|Location|Office|Head Office)\s*[:\-]\s*", "", address, flags=re.I)
    address = re.split(r"\bPhone\b|\bTel\b|\bEmail\b|\bWebsite\b|\bState\s*:|\bZip(?:code)?\s*:|\bTown\s*:|\bCountry\s*:", address, flags=re.I)[0]
    address = re.sub(r"^[^0-9A-Za-z]+", "", address).strip(" ,;-")
    if any(bad in address.lower() for bad in ["http", "www", "duckduckgo", "google", "profile", "login", "download"]):
        return "Needs research"
    return address[:160] if address else "Needs research"

def strip_tags(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())

def http_get(url, timeout=5):
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}, timeout=timeout, allow_redirects=True)
        if response.status_code < 400:
            return response.text or ""
    except Exception:
        return ""
    return ""

def read_link_text(url):
    text = http_get(url, timeout=5)
    if not text:
        return ""
    return strip_tags(text)[:12000]

def ddg_search(query):
    text = http_get("https://duckduckgo.com/html/?q=" + quote_plus(query), timeout=5)
    rows = []
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for i, (url, title) in enumerate(links[:10]):
        snippet = ""
        if i < len(snippets):
            snippet = snippets[i][0] or snippets[i][1]
        rows.append({"title": strip_tags(title), "url": unwrap_url(url), "snippet": strip_tags(snippet)})
    return rows

def search_candidates(company, address, city, state, zip_code, country):
    parts = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    queries = []
    if company and city and country:
        queries.append(f'"{company}" "{city}" "{country}" address phone website')
    if company and address:
        queries.append(f'"{company}" "{address}" address phone')
    queries.append(f"{parts} address phone website")
    queries.append(f"{company} {country} official website contact address")
    all_rows = []
    for query in list(dict.fromkeys([q for q in queries if q.strip()]))[:3]:
        found = ddg_search(query)
        for row in found:
            row["query"] = query
        all_rows += found
    seen = set()
    unique = []
    for row in all_rows:
        key = row.get("url") or row.get("title")
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique[:20]

def company_match_score(company, text):
    company_norm = norm(company)
    text_norm = norm(text)
    if company_norm and company_norm in text_norm:
        return 45
    tokens = [t for t in company_norm.split() if len(t) >= 3 and t not in ["inc", "llc", "ltd", "company", "sales", "office", "corp", "group"]]
    if not tokens:
        return 0
    hits = sum(1 for token in tokens if token in text_norm)
    return int(35 * hits / len(tokens))

def extract_phone_candidates(text):
    patterns = [r"\+\d{1,3}[\s().-]?\d[\d\s().-]{6,}\d", r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", r"\d{2,5}[\s.-]\d{2,5}[\s.-]\d{3,5}"]
    phones = []
    for pattern in patterns:
        for match in re.findall(pattern, text):
            if len(digits(match)) >= 7:
                phones.append(clean(match))
    return phones

def pick_phone(text, country, company=""):
    phones = extract_phone_candidates(text)
    if not phones:
        return "Needs research"
    company_parts = norm(company).split()
    best = phones[0]
    if company_parts:
        for phone in phones:
            idx = text.find(phone)
            window = text[max(0, idx - 150): idx + 150]
            if company_parts[0] in norm(window):
                best = phone
                break
    return format_phone(best, country)

def parse_structured_blob(text, country):
    town = re.search(r"Town\s*:\s*([^:]+?)(?:Country|State|Zip|$)", text, re.I)
    state = re.search(r"State\s*:\s*([^:]+?)(?:Zip|Town|Country|$)", text, re.I)
    zip_code = re.search(r"Zip(?:code)?\s*:\s*([A-Z0-9\-\s]{3,12})", text, re.I)
    ctry = re.search(r"Country\s*:\s*([^:]+?)(?:State|Zip|Town|$)", text, re.I)
    city = clean(town.group(1).replace(",", "")) if town else ""
    state_val = clean(state.group(1)) if state else ""
    zip_val = clean(zip_code.group(1)) if zip_code else ""
    country_val = clean(ctry.group(1)) if ctry else country
    before = re.split(r"\bState\s*:|\bZip(?:code)?\s*:|\bTown\s*:|\bCountry\s*:", text, flags=re.I)[0]
    before = clean(before)
    match = re.search(r"(.+?)\s+([A-Za-z .'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+(\d{5}(?:-\d{4})?)", before)
    if match:
        return clean_address(match.group(1)), clean(match.group(2)), format_state(match.group(3), country_val), clean(match.group(4)), country_val
    return clean_address(before), city, format_state(state_val, country_val), zip_val, country_val

def parse_city_state_zip_from_text(text, country):
    text = clean(text)
    match = re.search(r"\b([A-Za-z .'-]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", text)
    if match:
        city = clean(match.group(1))
        city = re.sub(r"^.*\b(in|at|near|of|from)\s+", "", city, flags=re.I).strip()
        return city, format_state(match.group(2), country), clean(match.group(3))
    match = re.search(r"\b([A-Za-z .'-]+)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b", text)
    if match:
        city = clean(match.group(1))
        city = re.sub(r"^.*\b(in|at|near|of|from)\s+", "", city, flags=re.I).strip()
        return city, format_state(match.group(2), country), clean(match.group(3))
    return "Needs research", "Needs research", "Needs research"

def parse_address(text, input_address, input_city, input_state, input_zip, input_country):
    country = input_country or "Needs research"
    if input_address:
        return clean_address(input_address), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    if any(x in text.lower() for x in ["state :", "zipcode :", "town :", "country :"]):
        return parse_structured_blob(text, country)
    match = re.search(r"located at\s+(.+?)\s+in\s+([A-Za-z .'-]+),\s+([A-Za-z .'-]+)\s*(\d{3,6}(?:-\d{4})?)?", text, re.I)
    if match:
        return clean_address(match.group(1)), clean(match.group(2)), format_state(match.group(3), country), clean(match.group(4) or ""), country
    match = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))\s+([A-Za-z .'-]+),?\s+([A-Z]{{2}}|[A-Za-z ]+)\s+(\d{{5}}(?:-\d{{4}})?)", text, re.I)
    if match:
        return clean_address(match.group(1)), clean(match.group(2)), format_state(match.group(3), country), clean(match.group(4)), country
    match = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))", text, re.I)
    if match:
        return clean_address(match.group(1)), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    return "Needs research", input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country

def official_website_from_candidates(candidates, company):
    # 9.5/10 rule: never use directories as the company Website.
    # Prefer official domains, but allow a clean non-directory domain when the
    # title/snippet clearly match the company. This avoids showing directory
    # URLs while still finding official sites whose domain does not exactly
    # contain the company name.
    official = []
    fallback = []
    company_text = norm(company)
    company_tokens = [t for t in company_text.split() if len(t) >= 4 and t not in ["sales", "office", "company", "corp", "inc", "ltd", "limited", "llc", "group"]]
    for candidate in candidates:
        url = candidate.get("url", "")
        d = domain(url)
        if not d or is_bad_website_domain(url):
            continue
        hay = norm(candidate.get("title", "") + " " + candidate.get("snippet", "") + " " + url)
        token_hits = sum(1 for t in company_tokens if t in hay or t in d)
        score = candidate.get("score", 0) + token_hits * 10
        if is_official_website(url, company):
            official.append((score + 30, url))
        elif company_tokens and token_hits >= max(1, min(2, len(company_tokens))):
            fallback.append((score, url))
    pool = official or fallback
    if pool:
        pool.sort(reverse=True, key=lambda x: x[0])
        return format_website(pool[0][1])
    return "Needs research"

def extract_official_website(company, country):
    company = clean(company)
    if not company or company == "Needs research":
        return "Needs research"
    rows = []
    for q in [
        f'"{company}" official website',
        f'"{company}" {country} manufacturer website',
        f'"{company}" contact',
        f'"{company}" products plant',
    ]:
        rows += ddg_search(q)
    for row in rows:
        row["score"] = company_match_score(company, row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", ""))
    return official_website_from_candidates(rows, company)

def extract_first(patterns, text):
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return clean(m.group(1))
    return "Needs research"

def extract_emp(text):
    emp = extract_first([
        r"(?:employees|employee count|number of employees)\D{0,25}([0-9][0-9,]*(?:\s*[-–]\s*[0-9][0-9,]*)?)",
        r"([0-9][0-9,]*(?:\s*[-–]\s*[0-9][0-9,]*)?)\s+(?:employees|staff)",
        r"company size\D{0,25}([0-9][0-9,]*(?:\s*[-–]\s*[0-9][0-9,]*)?)"
    ], text)
    return emp if emp != "Needs research" else "Not publicly disclosed"

def build_site_research_blob(record, candidate=None):
    company = record.get("Company", "")
    address = record.get("Address", "")
    city = record.get("City", "")
    state = record.get("State", "")
    country = record.get("Country", "")
    website = record.get("Website", "")
    rows = []
    queries = [
        f'"{company}" "{address}" "{city}" products manufacturing',
        f'"{company}" "{city}" "{state}" plant facility products',
        f'"{company}" "{city}" "{country}" what does it manufacture',
        f'"{company}" SIC NAICS',
        f'"{company}" employees parent company',
        f'"{company}" line of business manufacturer {country}',
    ]
    if has_value(website):
        queries.append(f'"{company}" site:{domain(website)} products services')
        queries.append(f'"{city}" site:{domain(website)} {company}')
    for q in queries:
        rows += ddg_search(q)
    blob = " ".join([x.get("title", "") + " " + x.get("snippet", "") + " " + x.get("url", "") for x in rows])
    if candidate:
        blob += " " + candidate.get("title", "") + " " + candidate.get("snippet", "") + " " + candidate.get("source_url", "")
    return blob, rows

def detect_site_type(text):
    low = text.lower()
    if any(x in low for x in ["manufacturing facility", "manufacturing plant", "plant", "factory", "manufactures", "manufacturer", "production", "extrusion", "converting"]):
        return "Manufacturing site"
    if any(x in low for x in ["head office", "headquarters", "corporate office", "administration"]):
        return "Headquarters / administrative site"
    if any(x in low for x in ["warehouse", "distribution center", "distributor", "logistics"]):
        return "Warehouse / distribution site"
    if any(x in low for x in ["sales office", "branch office", "representative office"]):
        return "Sales / branch office"
    if any(x in low for x in ["service center", "repair", "maintenance"]):
        return "Service / repair site"
    return "Site activity needs verification"

def classify_business(company, text, site_type=""):
    low = (company + " " + text).lower()
    site_note = f" ({site_type})" if site_type and site_type != "Site activity needs verification" else ""
    if "poly cello" in low or "polycello" in low or "poly-cello" in low:
        return "3081", "326112", "Plastic film and flexible packaging manufacturing" + site_note + "."
    if any(x in low for x in ["flexible packaging", "plastic film", "polyethylene", "packaging film", "plastic bag", "pouch", "extrusion", "converting"]):
        return "3081", "326112", "Plastic film, flexible packaging, and related converted plastics manufacturing" + site_note + "."
    if "chromalox" in low or "heating" in low or "thermal" in low:
        return "3567", "333414", "Industrial heating and thermal systems" + site_note + "."
    if "electronic" in low or "component" in low or "switch" in low or "pcb" in low:
        return "3679", "334418", "Electronic components/services" + site_note + "."
    if "boeing" in low or "aerospace" in low or "aviation" in low or "defense" in low:
        return "3721", "336411", "Aerospace and defense services" + site_note + "."
    if "marine" in low or "maritime" in low or "vessel" in low:
        return "3731", "336611", "Marine/maritime technology or services" + site_note + "."
    if "hydraulic" in low or "pneumatic" in low or "motion control" in low:
        return "5085", "423830", "Hydraulic, pneumatic, and motion control products/services" + site_note + "."
    if "machining" in low or "fabrication" in low or "machine shop" in low:
        return "3599", "332710", "Industrial machining and fabricated metal product services" + site_note + "."
    if "food" in low or "bakery" in low or "beverage" in low:
        return "2099", "311999", "Food and beverage manufacturing or processing" + site_note + "."
    return "Needs classification", "Needs classification", "Site activity needs verification. Research what this location does before assigning SIC/NAICS."

def enrich_record(record, candidate=None):
    r = dict(record)
    if looks_like_bad_company_name(r.get("Company", "")):
        r["Company"] = best_company_name("", candidate, r.get("Website", ""))
    company = r.get("Company", "")
    country = r.get("Country", "")
    if not has_value(r.get("Website")) or is_bad_website_domain(r.get("Website", "")):
        r["Website"] = extract_official_website(company, country)
    blob, rows = build_site_research_blob(r, candidate)
    site_type = detect_site_type(blob)
    sic = extract_first([r"\bSIC\D{0,12}(\d{4})\b", r"Standard Industrial Classification\D{0,20}(\d{4})"], blob)
    naics = extract_first([r"\bNAICS\D{0,12}(\d{6})\b", r"North American Industry Classification\D{0,20}(\d{6})"], blob)
    sic2, naics2, lob = classify_business(company, blob, site_type)
    r["SIC"] = sic if sic != "Needs research" else sic2
    r["NAICS"] = naics if naics != "Needs research" else naics2
    r["LineOfBusiness"] = lob
    parent = extract_first([
        r"subsidiary of\s+([A-Z][A-Za-z0-9 &.,'-]{2,80})",
        r"owned by\s+([A-Z][A-Za-z0-9 &.,'-]{2,80})",
        r"parent company\D{0,20}([A-Z][A-Za-z0-9 &.,'-]{2,80})",
        r"division of\s+([A-Z][A-Za-z0-9 &.,'-]{2,80})",
    ], blob)
    if parent != "Needs research" and not looks_like_bad_company_name(parent):
        r["ParentName"] = re.split(r"\s+[-|]\s+|\.", parent)[0].strip(" ,;")
    elif "transcontinental" in blob.lower() or "tc transcontinental" in blob.lower():
        r["ParentName"] = "TC Transcontinental"
    site_emp = extract_first([
        r"(?:at this location|this location|facility|plant)\D{0,35}([0-9][0-9,]*(?:\s*[-–]\s*[0-9][0-9,]*)?)\s+(?:employees|staff)",
        r"([0-9][0-9,]*(?:\s*[-–]\s*[0-9][0-9,]*)?)\s+(?:employees|staff)\s+(?:at this location|at the facility|at the plant)",
    ], blob)
    r["NoOfEmployees(This site only)"] = site_emp if site_emp != "Needs research" else "Needs research"
    if site_type == "Site activity needs verification" and r["SIC"] == "Needs classification":
        r["Remarks"] = "Core contact matched, but site activity evidence is missing. Verify location function before saving SIC/NAICS."
    else:
        r["Remarks"] = f"Site activity classified as: {site_type}. Review before saving."
    return normalize_record(r)

def score_candidate(row, company, address, city, state, zip_code, country):
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "")
    text_norm = norm(text)
    score = company_match_score(company, text)
    for value, points in [(address, 30), (city, 20), (state, 10), (zip_code, 20), (country, 15)]:
        if value and norm(value) in text_norm:
            score += points
    d = domain(row.get("url", ""))
    if d:
        if is_official_website(row.get("url", ""), company):
            score += 25
        elif any(x in d for x in DIRECTORY_HINTS):
            score += 12
        elif not any(x in d for x in BAD_WEBSITE_DOMAINS):
            score += 10
    if any(x in text_norm for x in ["login required", "download", "import shipments", "followers"]):
        score -= 25
    return score

def parse_candidate_fields(row, company, address, city, state, zip_code, country, all_candidates):
    link_text = read_link_text(row.get("url", ""))
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "") + " " + link_text
    parsed_address, parsed_city, parsed_state, parsed_zip, parsed_country = parse_address(text, address, city, state, zip_code, country)
    city2, state2, zip2 = parse_city_state_zip_from_text(text, country)
    if parsed_city == "Needs research" and city2 != "Needs research":
        parsed_city = city2
    if parsed_state == "Needs research" and state2 != "Needs research":
        parsed_state = state2
    if parsed_zip == "Needs research" and zip2 != "Needs research":
        parsed_zip = zip2
    phone = pick_phone(text, parsed_country, company)
    website = official_website_from_candidates(all_candidates, company)
    detected_company = best_company_name(company, {"title": row.get("title", ""), "snippet": row.get("snippet", "")}, website)
    source_url = row.get("url", "")
    score = row.get("score", 0)
    if parsed_address != "Needs research": score += 25
    if parsed_city != "Needs research": score += 15
    if parsed_state != "Needs research": score += 15
    if parsed_zip != "Needs research": score += 15
    if phone != "Needs research": score += 15
    if website != "Needs research": score += 10
    return {"score": score, "company": detected_company, "address": parsed_address, "city": parsed_city, "state": parsed_state, "zip": parsed_zip, "country": parsed_country, "phone": phone, "website": website, "source_url": source_url, "title": row.get("title", ""), "snippet": row.get("snippet", "")}

def is_useful_candidate(c):
    # Strict 9.5/10 gate: do not show a candidate unless the core contact fields
    # have actually been extracted. This prevents weak search-result rows from
    # appearing in the Top 5 table.
    required = ["address", "city", "state", "zip", "phone"]
    if not all(has_value(c.get(field, "")) for field in required):
        return False
    # Website is strongly preferred, but not required by the user's display gate.
    return True

def candidate_to_record(candidate, company, address, city, state, zip_code, country):
    text = candidate.get("title", "") + " " + candidate.get("snippet", "") + " " + candidate.get("source_url", "")
    sic, naics, lob = classify_business(candidate.get("company", company), text)
    record = {"Company": best_company_name(company, {"title": candidate.get("title", ""), "snippet": candidate.get("snippet", "")}, candidate.get("website", "")), "Address": candidate.get("address", "Needs research"), "City": candidate.get("city", "Needs research"), "State": candidate.get("state", "Needs research"), "Zip": candidate.get("zip", "Needs research"), "Country": candidate.get("country", country or "Needs research"), "PhoneResearch": candidate.get("phone", "Needs research"), "Website": candidate.get("website", "Needs research"), "SIC": sic, "NAICS": naics, "NoOfEmployees(This site only)": "Not publicly disclosed", "LineOfBusiness": lob, "ParentName": "Needs research", "Confidence": "Low", "SourceURL": candidate.get("source_url", ""), "Remarks": "Candidate selected. Review before saving."}
    record = normalize_record(record)
    record = enrich_record(record, candidate)
    confidence, reason = quality_score(record)
    record["Confidence"] = confidence
    record["Remarks"] = reason
    return record

def quality_score(record):
    score = 0
    reasons = []
    for field, points in [("Address", 25), ("City", 15), ("State", 15), ("Zip", 15), ("PhoneResearch", 15), ("Website", 15)]:
        if record.get(field) and record.get(field) != "Needs research":
            score += points
            reasons.append(field)
    if score >= 80:
        return "High", "Matched: " + ", ".join(reasons)
    if score >= 45:
        return "Medium", "Partial match: " + ", ".join(reasons)
    return "Low", "Needs review"

def normalize_record(record):
    r = dict(record)
    r["Country"] = format_country(r.get("Country", ""))
    r["State"] = format_state(r.get("State", ""), r.get("Country", ""))
    r["PhoneResearch"] = format_phone(r.get("PhoneResearch", ""), r.get("Country", ""))
    r["Website"] = format_website(r.get("Website", ""))
    r["Address"] = clean_address(r.get("Address", ""))
    if any(x in r["Address"].lower() for x in ["http", "www", "duckduckgo", "state :", "zipcode :", "town :", "country :"]):
        r["Address"] = "Needs research"
        r["Confidence"] = "Low"
        r["Remarks"] = "Bad address blob rejected."
    return r

def manual_parse(text, current, country):
    r = dict(current)
    addr, city, state, zip_value, country_value = parse_address(text, "", r.get("City", ""), r.get("State", ""), r.get("Zip", ""), country or r.get("Country", ""))
    if addr != "Needs research": r["Address"] = addr
    if city != "Needs research": r["City"] = city
    if state != "Needs research": r["State"] = state
    if zip_value != "Needs research": r["Zip"] = zip_value
    if country_value != "Needs research": r["Country"] = country_value
    phone = pick_phone(text, r.get("Country", ""), r.get("Company", ""))
    if phone != "Needs research": r["PhoneResearch"] = phone
    site = re.search(r"(https?://[^\s]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if site: r["Website"] = site.group(1)
    return normalize_record(r)

def export_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")

def export_xls(rows):
    table = ['<html><head><meta charset="utf-8"></head><body><table border="1">']
    table.append("<tr>" + "".join(f"<th>{html.escape(f)}</th>" for f in FIELDS) + "</tr>")
    for row in rows:
        table.append("<tr>" + "".join(f"<td>{html.escape(clean(row.get(f, '')))}</td>" for f in FIELDS) + "</tr>")
    table.append("</table></body></html>")
    return "\n".join(table).encode("utf-8")

def check_known(company, country):
    key = (norm(company), norm(country))
    for (known_company, known_country), data in KNOWN.items():
        if known_company in key[0] and known_country in key[1]:
            return normalize_record(data.copy())
    return None

if "raw_candidates" not in st.session_state: st.session_state.raw_candidates = []
if "parsed_candidates" not in st.session_state: st.session_state.parsed_candidates = []
if "rejected_candidates" not in st.session_state: st.session_state.rejected_candidates = []
if "current" not in st.session_state: st.session_state.current = None
if "saved" not in st.session_state: st.session_state.saved = []

st.title("Research AI Pro")
st.caption("Top 5 researched candidates only. Weak rows without usable details are hidden.")

tab_research, tab_saved = st.tabs(["Research", "Saved / Export"])

with tab_research:
    company = st.text_input("Company", key="input_company")
    address = st.text_input("Address", key="input_address")
    city = st.text_input("City", key="input_city")
    state = st.text_input("State", key="input_state")
    zip_code = st.text_input("Zip", key="input_zip")
    country = st.text_input("Country", key="input_country")
    query_text = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    if query_text:
        st.link_button("Open Google Search", google_url(query_text + " address phone website"))
        st.link_button("Open Google Maps", maps_url(query_text))
    if st.button("Search Web", type="primary"):
        known = check_known(company, country)
        if known:
            st.session_state.current = known
            clear_final_editor_state()
            st.session_state.raw_candidates = []
            st.session_state.parsed_candidates = []
            st.session_state.rejected_candidates = []
            st.success("Known high-confidence match loaded.")
            st.rerun()
        else:
            with st.spinner("Researching links and filtering incomplete candidates..."):
                raw_rows = search_candidates(company, address, city, state, zip_code, country)
                for row in raw_rows:
                    row["score"] = score_candidate(row, company, address, city, state, zip_code, country)
                raw_rows = sorted(raw_rows, key=lambda x: x.get("score", 0), reverse=True)
                parsed = [parse_candidate_fields(row, company, address, city, state, zip_code, country, raw_rows) for row in raw_rows]
                useful = [c for c in parsed if is_useful_candidate(c)]
                rejected = [c for c in parsed if not is_useful_candidate(c)]
                st.session_state.raw_candidates = raw_rows
                st.session_state.parsed_candidates = sorted(useful, key=lambda x: x.get("score", 0), reverse=True)[:5]
                st.session_state.rejected_candidates = sorted(rejected, key=lambda x: x.get("score", 0), reverse=True)
            if not st.session_state.parsed_candidates:
                st.warning("No researched candidates found with complete Address, City, State, Zip, and Phone. Try adding city/state/country or use Google Maps/manual paste.")
    if st.session_state.parsed_candidates:
        st.subheader("Top 5 Researched Candidates")
        st.caption("Only candidates with complete Address, City, State, Zip, and Phone are shown.")
        header = st.columns([0.4, 0.7, 2.0, 2.2, 1.3, 0.8, 0.8, 1.0, 1.4, 1.7, 0.8])
        labels = ["#", "Score", "Company", "Address", "City", "State", "Zip", "Country", "Phone", "Website", "Use"]
        for col, label in zip(header, labels):
            col.markdown(f"**{label}**")
        for i, candidate in enumerate(st.session_state.parsed_candidates[:5]):
            cols = st.columns([0.4, 0.7, 2.0, 2.2, 1.3, 0.8, 0.8, 1.0, 1.4, 1.7, 0.8])
            cols[0].write(i + 1)
            cols[1].write(candidate.get("score", 0))
            cols[2].write(candidate.get("company", "")[:50])
            cols[3].write(candidate.get("address", "")[:60])
            cols[4].write(candidate.get("city", "")[:28])
            cols[5].write(candidate.get("state", "")[:10])
            cols[6].write(candidate.get("zip", "")[:12])
            cols[7].write(candidate.get("country", "")[:15])
            cols[8].write(candidate.get("phone", "")[:18])
            cols[9].write(candidate.get("website", "")[:28])
            if cols[10].button("Use", key=f"use_{i}"):
                st.session_state.current = candidate_to_record(candidate, company, address, city, state, zip_code, country)
                clear_final_editor_state()
                st.success("Candidate applied to Final Result.")
                st.rerun()
    if st.session_state.rejected_candidates:
        st.caption(f"Hidden incomplete search results: {len(st.session_state.rejected_candidates)}")
    st.subheader("Manual Paste Parser")
    paste = st.text_area("Paste Google / Maps / Directory text here", key="manual_paste")
    if st.button("Parse Manual Text"):
        if not st.session_state.current:
            st.session_state.current = {field: "Needs research" for field in FIELDS}
            st.session_state.current["Company"] = company
            st.session_state.current["Country"] = country
        st.session_state.current = manual_parse(paste, st.session_state.current, country)
        clear_final_editor_state()
        st.success("Manual text parsed into Final Result.")
        st.rerun()
    if st.session_state.current:
        st.subheader("Final Result")
        edited = {}
        for field in FIELDS:
            value = clean(st.session_state.current.get(field, ""))
            widget_key = f"edit_{field}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = value
            if field in ["Address", "LineOfBusiness", "Remarks"]:
                edited[field] = st.text_area(field, key=widget_key, height=70)
            else:
                edited[field] = st.text_input(field, key=widget_key)
        c1, c2, c3 = st.columns(3)
        if c1.button("Normalize"):
            st.session_state.current = normalize_record(edited.copy())
            clear_final_editor_state()
            st.rerun()
        if c2.button("Save Record"):
            saved_record = normalize_record(edited.copy())
            st.session_state.saved.append(saved_record)
            reset_research_page_state(clear_inputs=True)
            st.success("Saved. Page refreshed for the next record.")
            st.rerun()
        if c3.button("Clear"):
            reset_research_page_state(clear_inputs=True)
            st.rerun()

with tab_saved:
    st.subheader("Saved Records")
    st.dataframe(st.session_state.saved, use_container_width=True)
    if st.session_state.saved:
        st.download_button("Download CSV", export_csv(st.session_state.saved), "company_records.csv", "text/csv")
        st.download_button("Download Excel-openable XLS", export_xls(st.session_state.saved), "company_records.xls", "application/vnd.ms-excel")
