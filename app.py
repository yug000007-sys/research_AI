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
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA","colorado":"CO",
    "connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA","hawaii":"HI","idaho":"ID",
    "illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY","louisiana":"LA",
    "maine":"ME","maryland":"MD","massachusetts":"MA","michigan":"MI","minnesota":"MN",
    "mississippi":"MS","missouri":"MO","montana":"MT","nebraska":"NE","nevada":"NV",
    "new hampshire":"NH","new jersey":"NJ","new mexico":"NM","new york":"NY",
    "north carolina":"NC","north dakota":"ND","ohio":"OH","oklahoma":"OK","oregon":"OR",
    "pennsylvania":"PA","rhode island":"RI","south carolina":"SC","south dakota":"SD",
    "tennessee":"TN","texas":"TX","utah":"UT","vermont":"VT","virginia":"VA",
    "washington":"WA","west virginia":"WV","wisconsin":"WI","wyoming":"WY"
}
US_ABBR = set(US_STATES.values())
CA_PROV = {"ontario":"ON","quebec":"QC","québec":"QC","british columbia":"BC","alberta":"AB","manitoba":"MB","saskatchewan":"SK","nova scotia":"NS"}
CA_ABBR = set(CA_PROV.values())
AU_STATES = {"new south wales":"NSW","nsw":"NSW","queensland":"QLD","qld":"QLD","victoria":"VIC","vic":"VIC","south australia":"SA","western australia":"WA","tasmania":"TAS","northern territory":"NT","australian capital territory":"ACT"}
DIAL = {"usa":"+1","us":"+1","united states":"+1","united states of america":"+1","canada":"+1","italy":"+39","australia":"+61","japan":"+81","vietnam":"+84","viet nam":"+84","germany":"+49","france":"+33","uae":"+971","united arab emirates":"+971","china":"+86","india":"+91","spain":"+34","netherlands":"+31","singapore":"+65","uk":"+44","united kingdom":"+44"}
BAD_DOMAINS = ["google","duckduckgo","facebook","linkedin","instagram","youtube","bloomberg","zoominfo","dnb","apollo","rocketreach","signalhire","lusha","volza","panjiva","importgenius","allbiz","yellowpages","chamberofcommerce","manta","buzzfile","opencorporates","paacc","macraesbluebook","kompass","processregister","visualvisitor","contactout","craft.co"]
DIR_HINTS = ["yellowpages","chamberofcommerce","allbiz","manta","buzzfile","paacc","macraesbluebook","kompass","processregister","azom","contactout","opencorporates"]
STREET_WORDS = "Street|St|Road|Rd|Drive|Dr|Avenue|Ave|Lane|Ln|Boulevard|Blvd|Way|Court|Ct|Place|Pl|Parkway|Pkwy|Circle|Cir|Highway|Hwy|Terrace|Ter|Square|Sq|Via|Viale|Piazza|Corso|Strada|Building|Suite|Unit|Floor|Industrial|Village"

KNOWN = {
    ("chromalox sales", "usa"): {"Company":"Chromalox Sales","Address":"103 Gamma Drive","City":"Pittsburgh","State":"PA","Zip":"15238","Country":"USA","PhoneResearch":"412-967-3800","Website":"www.chromalox.com","SIC":"3567","NAICS":"333414","NoOfEmployees(This site only)":"Not publicly disclosed","LineOfBusiness":"Industrial heating and thermal systems.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=Chromalox+Sales+103+Gamma+Drive+Pittsburgh+PA+15238","Remarks":"Known high-confidence match. Review before saving."},
    ("c&r electronic services", "australia"): {"Company":"C&R Electronic Services","Address":"30 Straits Ave","City":"South Granville","State":"NSW","Zip":"2142","Country":"Australia","PhoneResearch":"+61 2 9748 6030","Website":"Needs research","SIC":"3679","NAICS":"334418","NoOfEmployees(This site only)":"Needs research","LineOfBusiness":"Electronic equipment manufacturing / electronic services.","ParentName":"Needs research","Confidence":"High","SourceURL":"https://www.google.com/search?q=C%26R+Electronic+Services+30+Straits+Ave+South+Granville+NSW+2142","Remarks":"Known high-confidence match. Review before saving."}
}

def clean(x): return str(x or "").strip()
def norm(x): return re.sub(r"[^a-z0-9]+", " ", clean(x).lower()).strip()
def digits(x): return re.sub(r"\D+", "", clean(x))
def google_url(q): return "https://www.google.com/search?q=" + quote_plus(q)
def maps_url(q): return "https://www.google.com/maps/search/" + quote_plus(q)

def unwrap_url(url):
    url = html.unescape(clean(url))
    if url.startswith("//"): url = "https:" + url
    try:
        qs = parse_qs(urlparse(url).query)
        if "uddg" in qs and qs["uddg"]: return unquote(qs["uddg"][0])
        if "url" in qs and qs["url"]: return unquote(qs["url"][0])
    except Exception: pass
    return url

def domain(url):
    try: return urlparse(unwrap_url(url)).netloc.lower().replace("www.", "")
    except Exception: return ""

def format_country(country):
    c = norm(country)
    if c in ["usa", "us", "united states", "united states of america"]: return "USA"
    if c == "viet nam": return "Vietnam"
    return clean(country) or "Needs research"

def format_state(state, country):
    state = clean(state)
    if not state or state == "Needs research": return "Needs research"
    c = norm(country); up = state.upper().replace(".", "")
    if c in ["usa", "us", "united states", "united states of america"]:
        return up if up in US_ABBR else US_STATES.get(state.lower(), state)
    if c == "canada": return up if up in CA_ABBR else CA_PROV.get(state.lower(), state)
    if c == "australia": return AU_STATES.get(state.lower(), state)
    return state

def format_phone(phone, country):
    phone = clean(phone)
    if not phone or phone == "Needs research": return "Needs research"
    d = digits(phone)
    if len(d) < 7: return "Needs research"
    c = norm(country)
    if c in ["usa", "us", "united states", "united states of america", "canada"]:
        if len(d) == 11 and d.startswith("1"): d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return phone
    if phone.startswith("+"): return re.sub(r"\s+", " ", phone)
    code = DIAL.get(c, "")
    if code:
        cd = digits(code)
        if d.startswith(cd): return "+" + d[:len(cd)] + " " + d[len(cd):]
        if d.startswith("0"): d = d[1:]
        return f"{code} {d}"
    return phone

def format_website(url):
    url = unwrap_url(clean(url))
    if not url or url == "Needs research": return "Needs research"
    if not url.startswith(("http://", "https://")): url = "https://" + url
    d = domain(url)
    if not d or "google" in d or "duckduckgo" in d: return "Needs research"
    return "www." + d

def is_bad_website(url):
    d = domain(url)
    return any(b in d for b in BAD_DOMAINS)

def is_official(url, company):
    d = domain(url)
    if not d or is_bad_website(url): return False
    tokens = [t for t in norm(company).split() if len(t) >= 4 and t not in ["sales", "office", "company", "corp", "inc", "ltd", "llc", "group"]]
    return any(t in d for t in tokens)

def clean_company(title, input_company):
    title = clean(title)
    if not title: return input_company or "Needs research"
    title = re.split(r"\s+[-|]\s+", title)[0].strip()
    title = re.sub(r"\bCompany Profile\b.*", "", title, flags=re.I)
    title = re.sub(r"\bSales, Contacts.*", "", title, flags=re.I)
    title = re.sub(r"\bPhone, Email.*", "", title, flags=re.I)
    title = re.sub(r"\bOffice Locations.*", "", title, flags=re.I)
    title = title.strip(" ,-")
    if len(title) < 2: return input_company or "Needs research"
    if len(title) > 80: return input_company or title[:80]
    return title

def clean_address(addr):
    addr = html.unescape(clean(addr))
    if not addr or addr == "Needs research": return "Needs research"
    addr = re.sub(r"\s+", " ", addr)
    addr = re.sub(r"^(Address|Location|Office|Head Office)\s*[:\-]\s*", "", addr, flags=re.I)
    addr = re.split(r"\bPhone\b|\bTel\b|\bEmail\b|\bWebsite\b|\bState\s*:|\bZip(?:code)?\s*:|\bTown\s*:|\bCountry\s*:", addr, flags=re.I)[0]
    addr = re.sub(r"^[^0-9A-Za-z]+", "", addr).strip(" ,;-")
    if any(b in addr.lower() for b in ["http", "www", "duckduckgo", "google", "profile", "login", "download"]): return "Needs research"
    return addr[:160] if addr else "Needs research"

def strip_tags(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S|re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S|re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())

def http_get(url, timeout=5):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0", "Accept-Language":"en-US,en;q=0.9"}, timeout=timeout, allow_redirects=True)
        if r.status_code < 400: return r.text or ""
    except Exception: pass
    return ""

def ddg_search(query):
    text = http_get("https://duckduckgo.com/html/?q=" + quote_plus(query), timeout=5)
    rows = []
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for i, (url, title) in enumerate(links[:10]):
        snip = ""
        if i < len(snippets): snip = snippets[i][0] or snippets[i][1]
        rows.append({"title": strip_tags(title), "url": unwrap_url(url), "snippet": strip_tags(snip)})
    return rows

def search_candidates(company, address, city, state, zip_code, country):
    parts = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    queries = []
    if company and city and country: queries.append(f'"{company}" "{city}" "{country}" address phone website')
    if company and address: queries.append(f'"{company}" "{address}" address phone')
    queries.append(f"{parts} address phone website")
    queries.append(f"{company} {country} official website contact address")
    all_rows = []
    for q in list(dict.fromkeys([q for q in queries if q.strip()]))[:3]:
        found = ddg_search(q)
        for row in found: row["query"] = q
        all_rows += found
    seen, unique = set(), []
    for row in all_rows:
        key = row.get("url") or row.get("title")
        if key and key not in seen:
            seen.add(key); unique.append(row)
    return unique[:15]

def company_match_score(company, text):
    cn, tn = norm(company), norm(text)
    if cn and cn in tn: return 45
    toks = [t for t in cn.split() if len(t) >= 3 and t not in ["inc", "llc", "ltd", "company", "sales", "office", "corp", "group"]]
    if not toks: return 0
    hits = sum(1 for t in toks if t in tn)
    return int(35 * hits / len(toks))

def score_candidate(row, company, address, city, state, zip_code, country):
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "")
    tn = norm(text); score = company_match_score(company, text)
    for value, points in [(address,30), (city,20), (state,10), (zip_code,20), (country,15)]:
        if value and norm(value) in tn: score += points
    d = domain(row.get("url", ""))
    if d:
        if is_official(row.get("url", ""), company): score += 25
        elif any(x in d for x in DIR_HINTS): score += 12
        elif not any(x in d for x in BAD_DOMAINS): score += 10
    if any(x in tn for x in ["login required", "download", "import shipments", "followers"]): score -= 25
    return score

def extract_phones(text):
    pats = [r"\+\d{1,3}[\s().-]?\d[\d\s().-]{6,}\d", r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", r"\d{2,5}[\s.-]\d{2,5}[\s.-]\d{3,5}"]
    out = []
    for p in pats:
        for m in re.findall(p, text):
            if len(digits(m)) >= 7: out.append(clean(m))
    return out

def pick_phone(text, country, company=""):
    phones = extract_phones(text)
    if not phones: return "Needs research"
    best = phones[0]
    parts = norm(company).split()
    if parts:
        for ph in phones:
            idx = text.find(ph)
            window = text[max(0, idx-150):idx+150]
            if parts[0] in norm(window):
                best = ph; break
    return format_phone(best, country)

def parse_structured_blob(text, country):
    town = re.search(r"Town\s*:\s*([^:]+?)(?:Country|State|Zip|$)", text, re.I)
    state = re.search(r"State\s*:\s*([^:]+?)(?:Zip|Town|Country|$)", text, re.I)
    zipc = re.search(r"Zip(?:code)?\s*:\s*([A-Z0-9\-\s]{3,12})", text, re.I)
    ctry = re.search(r"Country\s*:\s*([^:]+?)(?:State|Zip|Town|$)", text, re.I)
    city = clean(town.group(1).replace(",", "")) if town else ""
    st = clean(state.group(1)) if state else ""
    zp = clean(zipc.group(1)) if zipc else ""
    co = clean(ctry.group(1)) if ctry else country
    before = re.split(r"\bState\s*:|\bZip(?:code)?\s*:|\bTown\s*:|\bCountry\s*:", text, flags=re.I)[0]
    m = re.search(r"(.+?)\s+([A-Za-z .'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+(\d{5}(?:-\d{4})?)", clean(before))
    if m: return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), co), clean(m.group(4)), co
    return clean_address(before), city, format_state(st, co), zp, co

def parse_address(text, input_address, input_city, input_state, input_zip, input_country):
    country = input_country or "Needs research"
    if input_address: return clean_address(input_address), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    if any(x in text.lower() for x in ["state :", "zipcode :", "town :", "country :"]): return parse_structured_blob(text, country)
    m = re.search(r"located at\s+(.+?)\s+in\s+([A-Za-z .'-]+),\s+([A-Za-z .'-]+)\s*(\d{3,6}(?:-\d{4})?)?", text, re.I)
    if m: return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), country), clean(m.group(4) or ""), country
    m = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))\s+([A-Za-z .'-]+),?\s+([A-Z]{{2}}|[A-Za-z ]+)\s+(\d{{5}}(?:-\d{{4}})?)", text, re.I)
    if m: return clean_address(m.group(1)), clean(m.group(2)), format_state(m.group(3), country), clean(m.group(4)), country
    m = re.search(rf"([0-9]{{1,6}}\s+[A-Za-z0-9 .'-]+?\s+(?:{STREET_WORDS}))", text, re.I)
    if m: return clean_address(m.group(1)), input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country
    return "Needs research", input_city or "Needs research", format_state(input_state, country), input_zip or "Needs research", country

def official_website(candidates, company):
    official, fallback = [], []
    for c in candidates:
        u = c.get("url", ""); d = domain(u)
        if not d: continue
        if is_official(u, company): official.append((c.get("score", 0), u))
        elif not any(b in d for b in BAD_DOMAINS): fallback.append((c.get("score", 0), u))
    if official:
        official.sort(reverse=True, key=lambda x:x[0]); return format_website(official[0][1])
    if fallback:
        fallback.sort(reverse=True, key=lambda x:x[0]); return format_website(fallback[0][1])
    return "Needs research"

def classify_business(company, text):
    low = (company + " " + text).lower()
    if "chromalox" in low or "heating" in low or "thermal" in low: return "3567", "333414", "Industrial heating and thermal systems."
    if "electronic" in low or "component" in low or "switch" in low or "pcb" in low: return "3679", "334418", "Electronic components/services."
    if "boeing" in low or "aerospace" in low or "aviation" in low or "defense" in low: return "3721", "336411", "Aerospace and defense services."
    if "marine" in low or "maritime" in low or "vessel" in low: return "3731", "336611", "Marine/maritime technology or services."
    if "hydraulic" in low or "pneumatic" in low or "motion control" in low: return "5085", "423830", "Hydraulic, pneumatic, and motion control products/services."
    return "Needs classification", "Needs classification", "Needs research"

def parse_candidate(row, company, address, city, state, zip_code, country, all_candidates):
    text = row.get("title", "") + " " + row.get("snippet", "") + " " + row.get("url", "")
    addr, ct, st, zp, co = parse_address(text, address, city, state, zip_code, country)
    phone = pick_phone(text, co, company)
    website = official_website(all_candidates, company)
    detected_company = clean_company(row.get("title", ""), company)
    score = row.get("score", 0)
    if addr != "Needs research": score += 20
    if phone != "Needs research": score += 10
    if website != "Needs research": score += 10
    return {"score": score, "company": detected_company, "address": addr, "city": ct, "state": st, "zip": zp, "country": co, "phone": phone, "website": website, "source_url": row.get("url", ""), "title": row.get("title", ""), "snippet": row.get("snippet", "")}

def quality_score(record):
    score, reasons = 0, []
    for field, points in [("Address",25),("City",15),("State",15),("Zip",15),("PhoneResearch",15),("Website",15)]:
        if record.get(field) and record.get(field) != "Needs research":
            score += points; reasons.append(field)
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
        r["Address"] = "Needs research"; r["Confidence"] = "Low"; r["Remarks"] = "Bad address blob rejected."
    return r

def candidate_to_record(candidate, company, address, city, state, zip_code, country):
    text = candidate.get("title", "") + " " + candidate.get("snippet", "") + " " + candidate.get("source_url", "")
    sic, naics, lob = classify_business(candidate.get("company", company), text)
    rec = {"Company": candidate.get("company") or company or "Needs research", "Address": candidate.get("address", "Needs research"), "City": candidate.get("city", "Needs research"), "State": candidate.get("state", "Needs research"), "Zip": candidate.get("zip", "Needs research"), "Country": candidate.get("country", country or "Needs research"), "PhoneResearch": candidate.get("phone", "Needs research"), "Website": candidate.get("website", "Needs research"), "SIC": sic, "NAICS": naics, "NoOfEmployees(This site only)": "Not publicly disclosed", "LineOfBusiness": lob, "ParentName": "Needs research", "Confidence": "Low", "SourceURL": candidate.get("source_url", ""), "Remarks": "Candidate selected. Review before saving."}
    rec = normalize_record(rec)
    conf, reason = quality_score(rec)
    rec["Confidence"] = conf; rec["Remarks"] = reason
    return rec

def manual_parse(text, current, country):
    r = dict(current)
    addr, city, state, zp, co = parse_address(text, "", r.get("City", ""), r.get("State", ""), r.get("Zip", ""), country or r.get("Country", ""))
    if addr != "Needs research": r["Address"] = addr
    if city != "Needs research": r["City"] = city
    if state != "Needs research": r["State"] = state
    if zp != "Needs research": r["Zip"] = zp
    if co != "Needs research": r["Country"] = co
    ph = pick_phone(text, r.get("Country", ""), r.get("Company", ""))
    if ph != "Needs research": r["PhoneResearch"] = ph
    site = re.search(r"(https?://[^\s]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if site: r["Website"] = site.group(1)
    return normalize_record(r)

def export_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader(); writer.writerows(rows)
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
        if known_company in key[0] and known_country in key[1]: return normalize_record(data.copy())
    return None

if "raw_candidates" not in st.session_state: st.session_state.raw_candidates = []
if "parsed_candidates" not in st.session_state: st.session_state.parsed_candidates = []
if "current" not in st.session_state: st.session_state.current = None
if "saved" not in st.session_state: st.session_state.saved = []

st.title("Research AI Pro")
st.caption("Structured candidate table + Use Candidate + strict formatting + save/export")

tab1, tab2 = st.tabs(["Research", "Saved / Export"])

with tab1:
    company = st.text_input("Company")
    address = st.text_input("Address")
    city = st.text_input("City")
    state = st.text_input("State")
    zip_code = st.text_input("Zip")
    country = st.text_input("Country")
    q = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    if q:
        st.link_button("Open Google Search", google_url(q + " address phone website"))
        st.link_button("Open Google Maps", maps_url(q))
    if st.button("Search Web", type="primary"):
        known = check_known(company, country)
        if known:
            st.session_state.current = known; st.session_state.raw_candidates = []; st.session_state.parsed_candidates = []
            st.success("Known high-confidence match loaded.")
        else:
            raw = search_candidates(company, address, city, state, zip_code, country)
            for row in raw: row["score"] = score_candidate(row, company, address, city, state, zip_code, country)
            raw = sorted(raw, key=lambda x: x.get("score", 0), reverse=True)
            parsed = [parse_candidate(row, company, address, city, state, zip_code, country, raw) for row in raw]
            parsed = sorted(parsed, key=lambda x: x.get("score", 0), reverse=True)
            st.session_state.raw_candidates = raw; st.session_state.parsed_candidates = parsed
    if st.session_state.parsed_candidates:
        st.subheader("Candidate Finder")
        st.caption("Review structured candidate fields. Click Use to overwrite the final result.")
        header = st.columns([0.4,0.7,2.0,2.2,1.3,0.8,0.8,1.0,1.4,1.7,0.8])
        labels = ["#", "Score", "Company", "Address", "City", "State", "Zip", "Country", "Phone", "Website", "Use"]
        for col, label in zip(header, labels): col.markdown(f"**{label}**")
        for i, cand in enumerate(st.session_state.parsed_candidates[:10]):
            cols = st.columns([0.4,0.7,2.0,2.2,1.3,0.8,0.8,1.0,1.4,1.7,0.8])
            cols[0].write(i+1); cols[1].write(cand.get("score", 0)); cols[2].write(cand.get("company", "")[:50]); cols[3].write(cand.get("address", "")[:60]); cols[4].write(cand.get("city", "")[:28]); cols[5].write(cand.get("state", "")[:10]); cols[6].write(cand.get("zip", "")[:12]); cols[7].write(cand.get("country", "")[:15]); cols[8].write(cand.get("phone", "")[:18]); cols[9].write(cand.get("website", "")[:28])
            if cols[10].button("Use", key=f"use_{i}"):
                st.session_state.current = candidate_to_record(cand, company, address, city, state, zip_code, country); st.success("Candidate applied.")
        with st.expander("Raw candidate snippets"):
            for i, raw in enumerate(st.session_state.raw_candidates[:10], 1):
                st.markdown(f"**{i}. {raw.get('title', '')}**"); st.write(raw.get("snippet", "")); st.write(raw.get("url", "")); st.divider()
    st.subheader("Manual Paste Parser")
    paste = st.text_area("Paste Google / Maps / Directory text here")
    if st.button("Parse Manual Text"):
        if not st.session_state.current:
            st.session_state.current = {field: "Needs research" for field in FIELDS}; st.session_state.current["Company"] = company; st.session_state.current["Country"] = country
        st.session_state.current = manual_parse(paste, st.session_state.current, country); st.success("Manual text parsed.")
    if st.session_state.current:
        st.subheader("Final Result")
        edited = {}
        for field in FIELDS:
            value = clean(st.session_state.current.get(field, ""))
            if field in ["Address", "LineOfBusiness", "Remarks"]:
                edited[field] = st.text_area(field, value=value, height=70)
            else:
                edited[field] = st.text_input(field, value=value)
        c1,c2,c3 = st.columns(3)
        if c1.button("Normalize"):
            st.session_state.current = normalize_record(edited.copy()); st.rerun()
        if c2.button("Save Record"):
            st.session_state.saved.append(normalize_record(edited.copy())); st.success("Saved.")
        if c3.button("Clear"):
            st.session_state.current = None; st.session_state.raw_candidates = []; st.session_state.parsed_candidates = []; st.rerun()

with tab2:
    st.subheader("Saved Records")
    st.dataframe(st.session_state.saved, use_container_width=True)
    if st.session_state.saved:
        st.download_button("Download CSV", export_csv(st.session_state.saved), "company_records.csv", "text/csv")
        st.download_button("Download Excel-openable XLS", export_xls(st.session_state.saved), "company_records.xls", "application/vnd.ms-excel")
