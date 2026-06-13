import re
from urllib.parse import urlparse

def clean(value):
    return str(value or "").strip()

def norm(value):
    return re.sub(r"[^a-z0-9]+", " ", clean(value).lower()).strip()

def digits(value):
    return re.sub(r"\D+", "", clean(value))

US_STATES = {
    "alabama":"AL","alaska":"AK","arizona":"AZ","arkansas":"AR","california":"CA",
    "colorado":"CO","connecticut":"CT","delaware":"DE","florida":"FL","georgia":"GA",
    "illinois":"IL","indiana":"IN","iowa":"IA","kansas":"KS","kentucky":"KY",
    "louisiana":"LA","maryland":"MD","massachusetts":"MA","michigan":"MI",
    "minnesota":"MN","missouri":"MO","new jersey":"NJ","new york":"NY",
    "north carolina":"NC","ohio":"OH","pennsylvania":"PA","texas":"TX",
    "virginia":"VA","washington":"WA","wisconsin":"WI"
}

CA_PROV = {
    "ontario":"ON","quebec":"QC","québec":"QC","british columbia":"BC",
    "alberta":"AB","manitoba":"MB","saskatchewan":"SK","nova scotia":"NS"
}

AU_STATES = {
    "new south wales":"NSW","queensland":"QLD","victoria":"VIC",
    "south australia":"SA","western australia":"WA"
}

DIAL = {
    "usa":"+1","united states":"+1","canada":"+1","italy":"+39",
    "australia":"+61","japan":"+81","vietnam":"+84","germany":"+49",
    "france":"+33","united arab emirates":"+971","uae":"+971"
}

def format_state(state, country):
    state = clean(state)
    c = norm(country)
    up = state.upper()

    if c in ["usa", "united states", "united states of america"]:
        return up if len(up) == 2 else US_STATES.get(state.lower(), state)

    if c == "canada":
        return up if len(up) == 2 else CA_PROV.get(state.lower(), state)

    if c == "australia":
        return AU_STATES.get(state.lower(), state)

    return state or "Needs research"

def format_country(country):
    c = norm(country)
    if c in ["usa", "us", "united states", "united states of america"]:
        return "USA"
    if c == "viet nam":
        return "Vietnam"
    return clean(country) or "Needs research"

def format_phone(phone, country):
    phone = clean(phone)
    if not phone or phone == "Needs research":
        return "Needs research"

    d = digits(phone)
    c = norm(country)

    if c in ["usa", "united states", "united states of america", "canada"]:
        if len(d) == 11 and d.startswith("1"):
            d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f"{d[:3]}-{d[3:6]}-{d[6:]}"
        return phone

    if phone.startswith("+"):
        return phone

    code = DIAL.get(c, "")
    if code:
        if d.startswith("0"):
            d = d[1:]
        return f"{code} {d}"

    return phone

def format_website(website):
    website = clean(website)
    if not website or website == "Needs research":
        return "Needs research"

    website = website.replace("https://", "").replace("http://", "")
    website = website.split("/")[0].strip()

    if not website or "duckduckgo" in website or "google" in website:
        return "Needs research"

    if not website.startswith("www."):
        website = "www." + website.replace("www.", "")

    return website

def clean_address(address):
    address = clean(address)
    if not address:
        return "Needs research"

    bad_parts = ["State :", "Zipcode :", "Town :", "Country :", "http", "www", "duckduckgo"]
    for bad in bad_parts:
        if bad.lower() in address.lower():
            address = re.split(bad, address, flags=re.I)[0]

    return address.strip(" ,;-") or "Needs research"

def normalize_record(record):
    r = dict(record)

    r["Country"] = format_country(r.get("Country", ""))
    r["State"] = format_state(r.get("State", ""), r.get("Country", ""))
    r["PhoneResearch"] = format_phone(r.get("PhoneResearch", ""), r.get("Country", ""))
    r["Website"] = format_website(r.get("Website", ""))
    r["Address"] = clean_address(r.get("Address", ""))

    return r
