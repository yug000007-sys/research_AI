import csv
import html
import io
import re
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

import requests
import streamlit as st

st.set_page_config(page_title="Research AI Pro", layout="wide")

FIELDS = [
    "Company", "Address", "City", "State", "Zip", "Country", "PhoneResearch",
    "Website", "SIC", "NAICS", "NoOfEmployees(This site only)",
    "LineOfBusiness", "ParentName", "Confidence", "SourceURL", "Remarks"
]

US_STATES = {
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO","connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID","illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA","maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN","mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV","new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY","north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR","pennsylvania":"PA","rhode island":"RI","south carolina":"SC","south dakota":"SD","tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA","washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY"
}
US_ABBR = set(US_STATES.values())
CA_PROV = {"ontario":"ON","quebec":"QC","québec":"QC","british columbia":"BC","alberta":"AB","manitoba":"MB","saskatchewan":"SK","nova scotia":"NS"}
CA_ABBR = set(CA_PROV.values())
AU_STATES = {"new south wales":"NSW","nsw":"NSW","queensland":"QLD","qld":"QLD","victoria":"VIC","vic":"VIC","south australia":"SA","western australia":"WA","tasmania":"TAS","northern territory":"NT","australian capital territory":"ACT"}
DIAL_CODES = {"usa":"+1","us":"+1","united states":"+1","united states of america":"+1","canada":"+1","italy":"+39","australia":"+61","japan":"+81","vietnam":"+84","viet nam":"+84","germany":"+49","france":"+33","uae":"+971","united arab emirates":"+971","china":"+86","india":"+91","spain":"+34","netherlands":"+31","singapore":"+65","united kingdom":"+44","uk":"+44","mexico":"+52","brazil":"+55"}
BAD_WEBSITE_DOMAINS = ["google","duckduckgo","facebook","linkedin","instagram","youtube","bloomberg","zoominfo","dnb","apollo","rocketreach","signalhire","lusha","volza","panjiva","importgenius","allbiz","yellowpages","chamberofcommerce","manta","buzzfile","opencorporates","paacc","macraesbluebook","kompass","processregister","craft.co","visualvisitor","contactout","datanyze","crunchbase"]
DIRECTORY_HINTS = ["yellowpages","chamberofcommerce","allbiz","manta","buzzfile","paacc","macraesbluebook","kompass","processregister","azom","craft.co","contactout","opencorporates"]
STREET_WORDS = "Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Place|Pl|Parkway|Pkwy|Circle|Cir|Highway|Hwy|Terrace|Ter|Square|Sq|Via|Viale|Piazza|Corso|Strada|Building|Suite|Unit|Floor|Industrial|Village|Poinsettia"

KNOWN = {
    ("chromalox sales", "usa"): {"Company":"Chromalox Sales","Address":"103 Gamma Drive","City":"Pittsburgh","State":"PA","Zip":"15238","Country":"USA","PhoneResearch":"412-967-3800","Website":"www.chromalox.com","SIC":"3567","NAICS":"333414","NoOfEmployees(This site only)":"Not publicly disclosed","LineOfBusiness":"Industrial heating and thermal systems.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=Chromalox+Sales+103+Gamma+Drive+Pittsburgh+PA+15238","Remarks":"Known high-confidence match. Review before saving."},
    ("c&r electronic services", "australia"): {"Company":"C&R Electronic Services","Address":"30 Straits Ave","City":"South Granville","State":"NSW","Zip":"2142","Country":"Australia","PhoneResearch":"+61 2 9748 6030","Website":"Needs research","SIC":"3679","NAICS":"334418","NoOfEmployees(This site only)":"Needs research","LineOfBusiness":"Electronic equipment manufacturing / electronic services.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=C%26R+Electronic+Services+30+Straits+Ave+South+Granville+NSW+2142","Remarks":"Known high-confidence match. Review before saving."}
}


def clean(v):
    return str(v or "").strip()

def norm(v):
    return re.sub(r"[^a-z0-9]+", " ", clean(v).lower()).strip()

def digits(v):
    return re.sub(r"\D+", "", clean(v))

def google_url(q):
    return "https://www.google.com/search?q=" + quote_plus(q)

def maps_url(q):
    return "https://www.google.com/maps/search/" + quote_plus(q)

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
        return up if up in US_ABBR else US_STATES.get(state.lower(), state)
    if c == "canada":
        return up if up in CA_ABBR else CA_PROV.get(state.lower(), state)
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
        cd = digits(code)
        if d.startswith(cd):
            return "+" + d[:len(cd)] + " " + d[len(cd):]
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

def clean_company_from_title(title, input_company):
    title = clean(title)
    if not title:
        return input_company or "Needs research"
    title = re.split(r"\s+[-|]\s+", title)[0].strip()
    title = re.sub(r"\bCompany Profile\b.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bSales, Contacts.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bPhone, Email.*", "", title, flags=re.I).strip()
    title = re.sub(r"\bOffice Locations.*", "", title, flags=re.I).strip()
    title = title.strip(" ,-")
    if len(title) < 2:
        return input_company or "Needs research"
    if len(title) > 80:
        return input_company or title[:80]
    return title

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
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}, timeout=timeout, allow_redirects=True)
        if r.status_code < 400:
            return r.text or ""
    except Exception:
        return ""
    return ""

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
    seen, unique = set(), []
    for row in all_rows:
        key = row.get("url") or row.get("title")
        if key and key not in seen:
            seen.add(key)
            unique.append(row)
    return unique[:15]

def company_match_score(company, text):
    cn, tn = norm(company), norm(text)
    if cn and cn in tn:
        return 45
    tokens = [t for t in cn.split() if len(t) >= 3 and t not in ["inc", "llc", "ltd", "company", "sales", "office", "corp", "group"]]
    if not tokens:
        return 0
    hits = sum(1 for t in tokens if t in tn)
    return int(35 * hits / len(tokens))

def extract_phone_candidates(text):
    patterns = [r"\+\d{1,3}[\s().-]?\d[\d\s().-]{6,}\d", r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", r"\d{2,5}[\s.-]\d{2,5}[\s.-]\d{3,5}"]
    phones = []
    for p in patterns:
        for m in re.findall(p, text):
            if len(digits(m)) >= 7:
                phones.append(clean(m))
    return phones

def pick_phone(text, country, company=""):
    phones = extract_phone_candidates(text)
    if not phones:
        return "Needs research"
    best = phones[0]
    parts = norm(company).split()
    if parts:
        for ph in phones:
            idx = text.find(ph)
            window = text[max(0, idx - 150):idx + 150]
            if parts[0] in norm(window):
                best = ph
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
    m = re.search(r"(.+?)\s+([A-Za-z .'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+(\d{5}(?:-\d{4})?)", before)
    if m:
        return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), country_val), clean(m.group(4)), country_val
    return clean_address(before), city, format_state(state_val, country_val), zip_val, country_val

def parse_city_state_zip_from_text(text, country):
    text = clean(text)
    patterns = [
        r"\b([A-Za-z .'-]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b",
        r"\b([A-Za-z .'-]+)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b",
        r"\b([A-Za-z .'-]+)\s+([A-Z]{2}),?\s*(\d{3,5})\b"
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            city = clean(m.group(1))
            city = re.sub(r"^.*\b(in|at|near|of|from|located)\s+", "", city, flags=re.I).strip()
            # remove common junk words that leak into city
            city = re.sub(r"^(Address|Office|Contact|Company|Profile)\s+", "", city, flags=re.I).strip()
            return city, format_state(m.group(2), country), clean(m.group(3))
    return "Needs research", "Needs research", "Needs research"

def parse_address(text, input_address, input_city, input_state, input_zip, input_country):
    country = input_country or "Needs research"
    if input_address:
        return clean_address(input_address), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    if any(x in text.lower() for x in ["state :", "zipcode :", "town :", "country :"]):
        return parse_structured_blob(text, country)
    m = re.search(r"located at\s+(.+?)\s+in\s+([A-Za-z .'-]+),\s+([A-Za-z .'-]+)\s*(\d{3,6}(?:-\d{4})?)?", text, re.I)
    if m:
        return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), country), clean(m.group(4) or ""), country
    m = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))\s+([A-Za-z .'-]+),?\s+([A-Z]{{2}}|[A-Za-z ]+)\s+(\d{{5}}(?:-\d{{4}})?)", text, re.I)
    if m:
        return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), country), clean(m.group(4)), country
    m = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))", text, re.I)
    if m:
        return clean_address(m.group(1)), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    return "Needs research", input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country

def official_website_from_candidates(candidates, company):
    official, fallback = [], []
    for c in candidates:
        url = c.get("url", "")
        d = domain(url)
        if not d:
            continue
        if is_official_website(url, company):
            official.append((c.get("score", 0), url))
        elif not any(bad in d for bad in BAD_WEBSITE_DOMAINS):
            fallback.append((c.get("score", 0), url))
    if official:
        official.sort(reverse=True, key=lambda x: x[0])
        return format_website(official[0][1])
    if fallback:
        fallback.sort(reverse=True, key=lambda x: x[0])
        return format_website(fallback[0][1])
    return "Needs research"

def classify_business(company, text):
    low = (company + " " + text).lower()
    if "chromalox" in low or "heating" in low or "thermal" in low:
        return "3567", "333414", "Industrial heating and thermal systems."
    if "electronic" in low or "component" in low or "switch" in low or "pcb" in low:
        return "3679", "334418", "Electronic components/services."
    if "boeing" in low or "aerospace" in low or "aviation" in low or "defense" in low:
        return "3721", "336411", "Aerospace and defense services."
    if "marine" in low or "maritime" in low or "vessel" in low:
        return "3731", "336611", "Marine/maritime technology or services."
    if "hydraulic" in low or "pneumatic" in low or "motion control" in low:
        return "5085", "423830", "Hydraulic, pneumatic, and motion control products/services."
    return "Needs classification", "Needs classification", "Needs research"

def score_candidate(row, company, address, city, state, zip_code, country):
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "")
    tn = norm(text)
    score = company_match_score(company, text)
    for value, points in [(address, 30), (city, 20), (state, 10), (zip_code, 20), (country, 15)]:
        if value and norm(value) in tn:
            score += points
    d = domain(row.get("url", ""))
    if d:
        if is_official_website(row.get("url", ""), company):
            score += 25
        elif any(x in d for x in DIRECTORY_HINTS):
            score += 12
        elif not any(x in d for x in BAD_WEBSITE_DOMAINS):
            score += 10
    if any(x in tn for x in ["login required", "download", "import shipments", "followers"]):
        score -= 25
    return score

def parse_candidate_fields(row, company, address, city, state, zip_code, country, all_candidates):
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "")
    parsed_address, parsed_city, parsed_state, parsed_zip, parsed_country = parse_address(text, address, city, state, zip_code, country)
    city2, state2, zip2 = parse_city_state_zip_from_text(text, country)
    if parsed_city == "Needs research" and city2 != "Needs research": parsed_city = city2
    if parsed_state == "Needs research" and state2 != "Needs research": parsed_state = state2
    if parsed_zip == "Needs research" and zip2 != "Needs research": parsed_zip = zip2
    phone = pick_phone(text, parsed_country, company)
    website = official_website_from_candidates(all_candidates, company)
    detected_company = clean_company_from_title(row.get("title", ""), company)
    score = row.get("score", 0)
    for field in [parsed_address, parsed_city, parsed_state, parsed_zip, phone, website]:
        if field != "Needs research": score += 10
    return {"score": score, "company": detected_company, "address": parsed_address, "city": parsed_city, "state": parsed_state, "zip": parsed_zip, "country": parsed_country, "phone": phone, "website": website, "source_url": row.get("url", ""), "title": row.get("title", ""), "snippet": row.get("snippet", "")}

def quality_score(record):
    score, reasons = 0, []
    for field, points in [("Address",25),("City",15),("State",15),("Zip",15),("PhoneResearch",15),("Website",15)]:
        if record.get(field) and record.get(field) != "Needs research":
            score += points
            reasons.append(field)
    if score >= 80: return "High", "Matched: " + ", ".join(reasons)
    if score >= 45: return "Medium", "Partial match: " + ", ".join(reasons)
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

def candidate_to_record(candidate, company, address, city, state, zip_code, country):
    text = candidate.get("title", "") + " " + candidate.get("snippet", "") + " " + candidate.get("source_url", "")
    sic, naics, lob = classify_business(candidate.get("company", company), text)
    record = {"Company": candidate.get("company") or company or "Needs research", "Address": candidate.get("address", "Needs research"), "City": candidate.get("city", "Needs research"), "State": candidate.get("state", "Needs research"), "Zip": candidate.get("zip", "Needs research"), "Country": candidate.get("country", country or "Needs research"), "PhoneResearch": candidate.get("phone", "Needs research"), "Website": candidate.get("website", "Needs research"), "SIC": sic, "NAICS": naics, "NoOfEmployees(This site only)": "Not publicly disclosed", "LineOfBusiness": lob, "ParentName": "Needs research", "Confidence": "Low", "SourceURL": candidate.get("source_url", ""), "Remarks": "Candidate selected. Review before saving."}
    record = normalize_record(record)
    confidence, reason = quality_score(record)
    record["Confidence"], record["Remarks"] = confidence, reason
    return record

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
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")

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
if "current" not in st.session_state: st.session_state.current = None
if "saved" not in st.session_state: st.session_state.saved = []

st.title("Research AI Pro")
st.caption("Structured candidate table + Use Candidate + strict formatting + save/export")

tab_research, tab_saved = st.tabs(["Research", "Saved / Export"])

with tab_research:
    company = st.text_input("Company")
    address = st.text_input("Address")
    city = st.text_input("City")
    state = st.text_input("State")
    zip_code = st.text_input("Zip")
    country = st.text_input("Country")

    query_text = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    if query_text:
        st.link_button("Open Google Search", google_url(query_text + " address phone website"))
        st.link_button("Open Google Maps", maps_url(query_text))

    if st.button("Search Web", type="primary"):
        known = check_known(company, country)
        if known:
            st.session_state.current = known
            st.session_state.raw_candidates = []
            st.session_state.parsed_candidates = []
            st.success("Known high-confidence match loaded.")
        else:
            raw_rows = search_candidates(company, address, city, state, zip_code, country)
            for row in raw_rows:
                row["score"] = score_candidate(row, company, address, city, state, zip_code, country)
            raw_rows = sorted(raw_rows, key=lambda x: x.get("score", 0), reverse=True)
            parsed = [parse_candidate_fields(row, company, address, city, state, zip_code, country, raw_rows) for row in raw_rows]
            parsed = sorted(parsed, key=lambda x: x.get("score", 0), reverse=True)
            st.session_state.raw_candidates = raw_rows
            st.session_state.parsed_candidates = parsed

    if st.session_state.parsed_candidates:
        st.subheader("Candidate Finder")
        st.caption("Review structured candidate fields. Click Use to overwrite the final result.")
        header = st.columns([0.4,0.7,2.0,2.2,1.3,0.8,0.8,1.0,1.4,1.7,0.8])
        labels = ["#", "Score", "Company", "Address", "City", "State", "Zip", "Country", "Phone", "Website", "Use"]
        for col, label in zip(header, labels): col.markdown(f"**{label}**")
        for i, candidate in enumerate(st.session_state.parsed_candidates[:10]):
            cols = st.columns([0.4,0.7,2.0,2.2,1.3,0.8,0.8,1.0,1.4,1.7,0.8])
            cols[0].write(i+1); cols[1].write(candidate.get("score",0)); cols[2].write(candidate.get("company","")[:50]); cols[3].write(candidate.get("address","")[:60]); cols[4].write(candidate.get("city","")[:28]); cols[5].write(candidate.get("state","")[:10]); cols[6].write(candidate.get("zip","")[:12]); cols[7].write(candidate.get("country","")[:15]); cols[8].write(candidate.get("phone","")[:18]); cols[9].write(candidate.get("website","")[:28])
            if cols[10].button("Use", key=f"use_{i}"):
                st.session_state.current = candidate_to_record(candidate, company, address, city, state, zip_code, country)
                st.success("Candidate applied.")
        with st.expander("Raw candidate snippets"):
            for i, raw in enumerate(st.session_state.raw_candidates[:10], start=1):
                st.markdown(f"**{i}. {raw.get('title', '')}**")
                st.write(raw.get("snippet", ""))
                st.write(raw.get("url", ""))
                st.divider()

    st.subheader("Manual Paste Parser")
    paste = st.text_area("Paste Google / Maps / Directory text here")
    if st.button("Parse Manual Text"):
        if not st.session_state.current:
            st.session_state.current = {field: "Needs research" for field in FIELDS}
            st.session_state.current["Company"] = company
            st.session_state.current["Country"] = country
        st.session_state.current = manual_parse(paste, st.session_state.current, country)
        st.success("Manual text parsed.")

    if st.session_state.current:
        st.subheader("Final Result")
        edited = {}
        for field in FIELDS:
            value = clean(st.session_state.current.get(field, ""))
            if field in ["Address", "LineOfBusiness", "Remarks"]:
                edited[field] = st.text_area(field, value=value, height=70)
            else:
                edited[field] = st.text_input(field, value=value)
        c1, c2, c3 = st.columns(3)
        if c1.button("Normalize"):
            st.session_state.current = normalize_record(edited.copy()); st.rerun()
        if c2.button("Save Record"):
            st.session_state.saved.append(normalize_record(edited.copy())); st.success("Saved.")
        if c3.button("Clear"):
            st.session_state.current = None; st.session_state.raw_candidates = []; st.session_state.parsed_candidates = []; st.rerun()

with tab_saved:
    st.subheader("Saved Records")
    st.dataframe(st.session_state.saved, use_container_width=True)
    if st.session_state.saved:
        st.download_button("Download CSV", export_csv(st.session_state.saved), "company_records.csv", "text/csv")
        st.download_button("Download Excel-openable XLS", export_xls(st.session_state.saved), "company_records.xls", "application/vnd.ms-excel")
