import csv, html, io, re, requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote
import streamlit as st

st.set_page_config(page_title="Research AI", layout="wide")

FIELDS = ["Company","Address","City","State","Zip","Country","PhoneResearch","Website","SIC","NAICS","NoOfEmployees(This site only)","LineOfBusiness","ParentName","Confidence","SourceURL","Remarks"]

US_STATES = {"pennsylvania":"PA","alabama":"AL","california":"CA","texas":"TX","new york":"NY","florida":"FL","illinois":"IL","ohio":"OH"}
AU_STATES = {"new south wales":"NSW","queensland":"QLD","victoria":"VIC"}

def clean(x): return str(x or "").strip()
def digits(x): return re.sub(r"\D+", "", clean(x))
def norm(x): return re.sub(r"[^a-z0-9]+", " ", clean(x).lower()).strip()
def google(q): return "https://www.google.com/search?q=" + quote_plus(q)
def maps(q): return "https://www.google.com/maps/search/" + quote_plus(q)

def unwrap(url):
    url = html.unescape(clean(url))
    if url.startswith("//"): url = "https:" + url
    try:
        q = parse_qs(urlparse(url).query)
        if "uddg" in q: return unquote(q["uddg"][0])
        if "url" in q: return unquote(q["url"][0])
    except Exception:
        pass
    return url

def domain(url):
    try: return urlparse(unwrap(url)).netloc.lower().replace("www.","")
    except Exception: return ""

def fmt_website(site):
    site = unwrap(clean(site))
    if not site: return "Needs research"
    if not site.startswith(("http://","https://")): site = "https://" + site
    d = domain(site)
    if not d or "google" in d or "duckduckgo" in d: return "Needs research"
    return "www." + d

def fmt_state(state, country):
    s, c = clean(state), norm(country)
    if c in ["usa","united states"]:
        return US_STATES.get(s.lower(), s.upper() if len(s)==2 else s)
    if c == "australia":
        return AU_STATES.get(s.lower(), s)
    return s or "Needs research"

def fmt_phone(phone, country):
    phone, c, d = clean(phone), norm(country), digits(phone)
    if not d: return "Needs research"
    if c in ["usa","united states","canada"]:
        if len(d) == 11 and d.startswith("1"): d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return phone
    codes = {"australia":"+61","italy":"+39","japan":"+81","vietnam":"+84","germany":"+49","france":"+33","uae":"+971","united arab emirates":"+971"}
    code = codes.get(c, "")
    if phone.startswith("+"): return phone
    if code:
        if d.startswith("0"): d = d[1:]
        return f"{code} {d}"
    return phone

def normalize(r):
    r["State"] = fmt_state(r.get("State",""), r.get("Country",""))
    r["PhoneResearch"] = fmt_phone(r.get("PhoneResearch",""), r.get("Country",""))
    r["Website"] = fmt_website(r.get("Website",""))
    return r

def http_get(url):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=5)
        if r.status_code < 400: return r.text or ""
    except Exception:
        return ""
    return ""

def strip_tags(t):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", t)).split())

def ddg_search(query):
    text = http_get("https://duckduckgo.com/html/?q=" + quote_plus(query))
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    rows = []
    for i, (url, title) in enumerate(links[:10]):
        snip = ""
        if i < len(snippets): snip = snippets[i][0] or snippets[i][1]
        rows.append({"title": strip_tags(title), "url": unwrap(url), "snippet": strip_tags(snip)})
    return rows

def score(row, company, address, city, state, zip_code, country):
    text = norm(row["title"] + " " + row["snippet"] + " " + row["url"])
    sc = 0
    if norm(company) in text: sc += 40
    for val, pts in [(address,25),(city,20),(state,10),(zip_code,15),(country,20)]:
        if val and norm(val) in text: sc += pts
    d = domain(row["url"])
    if d and not any(x in d for x in ["google","duckduckgo","facebook","linkedin","zoominfo","dnb"]): sc += 10
    return sc

def find_phone(text):
    m = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    return clean(m.group(1)) if m else "Needs research"

def parse_address(text, country):
    # 107 Gamma Drive Pittsburgh, PA 15238
    m = re.search(r"(.+?)\s+([A-Za-z .'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+(\d{4,6}(?:-\d{4})?)", text)
    if m:
        return clean(m.group(1)), clean(m.group(2)), clean(m.group(3)), clean(m.group(4)), country

    # located at 30 Straits Ave in South Granville, New South Wales 2142
    m = re.search(r"located at\s+(.+?)\s+in\s+([A-Za-z .'-]+),\s+([A-Za-z .'-]+)\s*(\d{3,6})?", text, re.I)
    if m:
        return clean(m.group(1)), clean(m.group(2)), clean(m.group(3)), clean(m.group(4) or ""), country

    return "Needs research", "Needs research", "Needs research", "Needs research", country

def classify(company, text):
    low = (company + " " + text).lower()
    if "chromalox" in low or "heating" in low: return "3567","333414","Industrial heating and thermal systems."
    if "electronic" in low or "component" in low: return "3679","334418","Electronic components/services."
    if "boeing" in low or "aerospace" in low: return "3721","336411","Aerospace and defense services."
    return "Needs classification","Needs classification","Needs research"

def candidate_to_record(c, company, address, city, state, zip_code, country):
    text = c["title"] + " " + c["snippet"]
    a, ct, stt, zp, co = parse_address(text, country)
    sic, naics, lob = classify(company, text)
    rec = {
        "Company": company,
        "Address": address or a,
        "City": city or ct,
        "State": state or stt,
        "Zip": zip_code or zp,
        "Country": country or co,
        "PhoneResearch": find_phone(text),
        "Website": fmt_website(c["url"]),
        "SIC": sic,
        "NAICS": naics,
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": lob,
        "ParentName": "Needs research",
        "Confidence": "High" if c["score"] >= 80 else "Medium" if c["score"] >= 50 else "Low",
        "SourceURL": c["url"],
        "Remarks": "Candidate selected. Review before saving."
    }
    return normalize(rec)

def to_csv(rows):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(rows)
    return out.getvalue().encode("utf-8")

st.title("Research AI")

if "candidates" not in st.session_state: st.session_state.candidates = []
if "current" not in st.session_state: st.session_state.current = None
if "saved" not in st.session_state: st.session_state.saved = []

tab1, tab2 = st.tabs(["Research", "Saved / Export"])

with tab1:
    company = st.text_input("Company")
    address = st.text_input("Address")
    city = st.text_input("City")
    state = st.text_input("State")
    zip_code = st.text_input("Zip")
    country = st.text_input("Country")

    q = " ".join([company,address,city,state,zip_code,country])
    if q:
        st.link_button("Open Google Search", google(q + " address phone website"))
        st.link_button("Open Google Maps", maps(q))

    if st.button("Search Web", type="primary"):
        query = " ".join([company,address,city,state,zip_code,country,"address phone website"])
        results = ddg_search(query)
        for r in results:
            r["score"] = score(r, company, address, city, state, zip_code, country)
        st.session_state.candidates = sorted(results, key=lambda x:x["score"], reverse=True)

    if st.session_state.candidates:
        st.subheader("Candidates")
        for i, c in enumerate(st.session_state.candidates[:10]):
            cols = st.columns([1,1,3,4,2,1])
            cols[0].write(i+1)
            cols[1].write(c["score"])
            cols[2].write(c["title"][:80])
            cols[3].write(c["snippet"][:160])
            cols[4].write(fmt_website(c["url"]))
            if cols[5].button("Use", key=f"use_{i}"):
                st.session_state.current = candidate_to_record(c, company, address, city, state, zip_code, country)

    manual = st.text_area("Paste Google / Maps / Directory text here")
    if st.button("Parse Manual Text"):
        if not st.session_state.current:
            st.session_state.current = {f:"Needs research" for f in FIELDS}
            st.session_state.current["Company"] = company
            st.session_state.current["Country"] = country
        a, ct, stt, zp, co = parse_address(manual, country)
        if a != "Needs research": st.session_state.current["Address"] = a
        if ct != "Needs research": st.session_state.current["City"] = ct
        if stt != "Needs research": st.session_state.current["State"] = stt
        if zp != "Needs research": st.session_state.current["Zip"] = zp
        phone = find_phone(manual)
        if phone != "Needs research": st.session_state.current["PhoneResearch"] = phone
        st.session_state.current = normalize(st.session_state.current)

    if st.session_state.current:
        st.subheader("Final Result")
        edited = {}
        for f in FIELDS:
            edited[f] = st.text_input(f, st.session_state.current.get(f,""))

        if st.button("Normalize"):
            st.session_state.current = normalize(edited.copy())
            st.rerun()

        if st.button("Save Record"):
            st.session_state.saved.append(normalize(edited.copy()))
            st.success("Saved")

with tab2:
    st.dataframe(st.session_state.saved)
    if st.session_state.saved:
        st.download_button("Download CSV", to_csv(st.session_state.saved), "company_records.csv", "text/csv")
