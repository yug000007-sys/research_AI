import re
import csv
import io
import streamlit as st
from urllib.parse import quote_plus

st.set_page_config(page_title="Research AI", layout="wide")

FIELDS = [
    "Company","Address","City","State","Zip","Country","PhoneResearch",
    "Website","SIC","NAICS","NoOfEmployees(This site only)",
    "LineOfBusiness","ParentName","Confidence","SourceURL","Remarks"
]

US_STATES = {
    "pennsylvania":"PA","alabama":"AL","california":"CA","texas":"TX",
    "new york":"NY","florida":"FL","illinois":"IL","ohio":"OH"
}

AU_STATES = {"new south wales":"NSW","queensland":"QLD","victoria":"VIC"}

def clean(x):
    return str(x or "").strip()

def digits(x):
    return re.sub(r"\D+", "", clean(x))

def google_url(q):
    return "https://www.google.com/search?q=" + quote_plus(q)

def maps_url(q):
    return "https://www.google.com/maps/search/" + quote_plus(q)

def format_state(state, country):
    s = clean(state)
    c = clean(country).lower()
    if c in ["usa","united states"]:
        return US_STATES.get(s.lower(), s.upper() if len(s)==2 else s)
    if c == "australia":
        return AU_STATES.get(s.lower(), s)
    return s

def format_phone(phone, country):
    d = digits(phone)
    c = clean(country).lower()

    if not d:
        return "Needs research"

    if c in ["usa","united states","canada"]:
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return phone

    codes = {
        "australia":"+61","italy":"+39","japan":"+81",
        "vietnam":"+84","germany":"+49","france":"+33",
        "united arab emirates":"+971","uae":"+971"
    }

    code = codes.get(c, "")
    if phone.startswith("+"):
        return phone
    if code:
        if d.startswith("0"):
            d = d[1:]
        return f"{code} {d}"

    return phone

def format_website(site):
    site = clean(site)
    if not site:
        return "Needs research"
    site = site.replace("https://","").replace("http://","").split("/")[0]
    if "google" in site or "duckduckgo" in site:
        return "Needs research"
    if not site.startswith("www."):
        site = "www." + site.replace("www.","")
    return site

def parse_manual_text(text, record):
    text = clean(text)

    phone_match = re.search(r"(\+?\d[\d\s().-]{7,}\d)", text)
    if phone_match:
        record["PhoneResearch"] = phone_match.group(1)

    website_match = re.search(r"(https?://[^\s]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,})", text)
    if website_match:
        record["Website"] = website_match.group(1)

    # USA format: 107 Gamma Drive Pittsburgh, PA 15238
    usa = re.search(r"(.+?)\s+([A-Za-z .'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+(\d{5}(?:-\d{4})?)", text)
    if usa:
        record["Address"] = usa.group(1).strip()
        record["City"] = usa.group(2).strip()
        record["State"] = usa.group(3).strip()
        record["Zip"] = usa.group(4).strip()

    # Directory format: located at 30 Straits Ave in South Granville, New South Wales 2142
    loc = re.search(r"located at\s+(.+?)\s+in\s+([A-Za-z .'-]+),\s+([A-Za-z .'-]+)\s*(\d{3,6})?", text, re.I)
    if loc:
        record["Address"] = loc.group(1).strip()
        record["City"] = loc.group(2).strip()
        record["State"] = loc.group(3).strip()
        if loc.group(4):
            record["Zip"] = loc.group(4).strip()

    return record

def normalize(record):
    record["State"] = format_state(record["State"], record["Country"])
    record["PhoneResearch"] = format_phone(record["PhoneResearch"], record["Country"])
    record["Website"] = format_website(record["Website"])
    return record

def make_record(company,address,city,state,zip_code,country,manual_text):
    q = " ".join([company,address,city,state,zip_code,country,"address phone website"])

    record = {
        "Company": company or "Needs research",
        "Address": address or "Needs research",
        "City": city or "Needs research",
        "State": state or "Needs research",
        "Zip": zip_code or "Needs research",
        "Country": country or "Needs research",
        "PhoneResearch": "Needs research",
        "Website": "Needs research",
        "SIC": "Needs classification",
        "NAICS": "Needs classification",
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": "Needs research",
        "ParentName": "Needs research",
        "Confidence": "Low",
        "SourceURL": google_url(q),
        "Remarks": "Generated from input. Paste Google/Maps text for better parsing."
    }

    if manual_text.strip():
        record = parse_manual_text(manual_text, record)
        record["Confidence"] = "Medium"
        record["Remarks"] = "Generated from manual pasted research text."

    return normalize(record)

def to_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")

st.title("Research AI")

if "saved" not in st.session_state:
    st.session_state.saved = []
if "current" not in st.session_state:
    st.session_state.current = None

tab1, tab2 = st.tabs(["Research", "Saved / Export"])

with tab1:
    company = st.text_input("Company")
    address = st.text_input("Address")
    city = st.text_input("City")
    state = st.text_input("State")
    zip_code = st.text_input("Zip")
    country = st.text_input("Country")

    q = " ".join([company,address,city,state,zip_code,country])
    if q.strip():
        st.link_button("Open Google Search", google_url(q + " address phone website"))
        st.link_button("Open Google Maps", maps_url(q))

    manual_text = st.text_area("Paste Google / Maps / Directory text here")

    if st.button("Generate Result", type="primary"):
        st.session_state.current = make_record(company,address,city,state,zip_code,country,manual_text)

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
    st.subheader("Saved Records")
    st.dataframe(st.session_state.saved)

    if st.session_state.saved:
        st.download_button(
            "Download CSV",
            to_csv(st.session_state.saved),
            "company_records.csv",
            "text/csv"
        )
