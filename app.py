import csv
import html
import io
import re
import time
from urllib.parse import quote_plus, urlparse

import requests
import streamlit as st

st.set_page_config(page_title="Company Enrichment Tool", layout="wide")

st.title("Company Enrichment Tool - Step 3.1 Non-Hanging")
st.success("App loaded successfully.")
st.write("This version always creates output. Website reading is limited to prevent endless loading.")

OUTPUT_COLUMNS = [
    "Company",
    "Address",
    "City",
    "State",
    "Zip",
    "Country",
    "PhoneResearch",
    "Website",
    "SIC",
    "NAICS",
    "NoOfEmployees(This site only)",
    "LineOfBusiness",
    "ParentName",
    "Confidence",
    "SourceURL",
    "Remarks",
]

BAD_DOMAINS = [
    "google.", "duckduckgo.", "facebook.", "linkedin.", "twitter.", "x.com",
    "instagram.", "youtube.", "bloomberg.", "dnb.", "zoominfo.", "yelp.",
    "mapquest.", "wikipedia.", "crunchbase."
]

def clean(value):
    return str(value or "").strip()

def normalize_key(key):
    return str(key or "").strip().lower().replace(" ", "").replace("_", "")

def get_value(row, target):
    aliases = {
        "Company": ["company", "companyname", "name"],
        "City": ["city", "town"],
        "State": ["state", "province", "region"],
        "Zip": ["zip", "zipcode", "postal", "postalcode", "postcode"],
        "Country": ["country", "nation"],
    }
    wanted = aliases.get(target, [target.lower()])
    for k, v in row.items():
        if normalize_key(k) in wanted:
            return clean(v)
    return ""

def make_search_query(company, city, state, zip_code, country):
    parts = [company, city, state, zip_code, country, "official website address phone"]
    return " ".join([p for p in parts if p]).strip()

def google_search_url(query):
    return "https://www.google.com/search?q=" + quote_plus(query)

def fallback_row(row, note):
    company = get_value(row, "Company")
    city = get_value(row, "City")
    state = get_value(row, "State")
    zip_code = get_value(row, "Zip")
    country = get_value(row, "Country")
    query = make_search_query(company, city, state, zip_code, country)
    return {
        "Company": company,
        "Address": "Needs research",
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
        "SourceURL": google_search_url(query),
        "Remarks": note,
    }

def ddg_search_html(query, max_results=6, timeout=6):
    url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    results = []
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        text = r.text or ""
        links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
        for href, title_html in links[:max_results]:
            title = html.unescape(" ".join(re.sub("<.*?>", " ", title_html).split()))
            href = html.unescape(href)
            results.append({"title": title, "href": href, "body": ""})
    except Exception as e:
        results.append({"title": "Search failed", "href": "", "body": str(e)})
    return results

def domain_is_bad(url):
    try:
        netloc = urlparse(url).netloc.lower()
        return any(bad in netloc for bad in BAD_DOMAINS)
    except Exception:
        return True

def extract_domain_url(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return parsed.scheme + "://" + parsed.netloc
    except Exception:
        pass
    return ""

def find_best_website(company, results):
    company_tokens = [t for t in re.split(r"[^a-z0-9]+", company.lower()) if len(t) >= 3]
    candidates = []

    for result in results:
        href = result.get("href", "")
        title = result.get("title", "")
        if not href.startswith("http") or domain_is_bad(href):
            continue

        domain_url = extract_domain_url(href)
        domain = urlparse(domain_url).netloc.lower()
        score = 0

        for token in company_tokens:
            if token in domain:
                score += 40
            if token in title.lower():
                score += 15

        candidates.append((score, domain_url, href))

    if not candidates:
        return "Needs research", ""

    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]

def fetch_text_once(url, timeout=5):
    if not url or not url.startswith("http"):
        return ""
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return ""
        text = r.text or ""
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.S|re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S|re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = " ".join(text.split())
        return text[:15000]
    except Exception:
        return ""

def find_phone(text):
    patterns = [
        r"\+\d{1,3}[\s\-.]?\(?\d{1,5}\)?[\s\-.]?\d{2,5}[\s\-.]?\d{2,5}[\s\-.]?\d{2,6}",
        r"\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean(match.group(0))
    return "Needs research"

def find_address(text, city, state, zip_code, country):
    tokens = [x for x in [zip_code, city, state, country] if x]
    best = ""
    low = text.lower()
    for token in tokens:
        idx = low.find(token.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 120): min(len(text), idx + 180)]
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if len(snippet) > len(best):
                best = snippet
    return best[:280] if len(best) >= 30 else "Needs research"

def classify(company, website, page_text):
    text = (company + " " + website + " " + page_text[:3000]).lower()
    if any(x in text for x in ["boeing", "aerospace", "aircraft", "aviation", "defense", "missile"]):
        return "3721 / 3761", "336411 / 336414", "Aerospace and defense manufacturing, engineering, and support services."
    if any(x in text for x in ["software", "saas", "technology", "cloud", "cybersecurity"]):
        return "7372 / 7373", "541511 / 541512", "Software, IT, or technology services."
    if any(x in text for x in ["consulting", "consultant", "advisory"]):
        return "8742 / 8748", "541611", "Business or management consulting services."
    if any(x in text for x in ["manufacturing", "manufacturer", "factory", "industrial"]):
        return "3999 / 3599", "339999 / 333249", "Manufacturing or industrial operations."
    return "Needs classification", "Needs classification", "Needs research"

def confidence(company, city, zip_code, country, website, address, phone):
    score = 0
    if company:
        score += 20
    if city:
        score += 10
    if zip_code:
        score += 10
    if country:
        score += 10
    if website != "Needs research":
        score += 25
    if address != "Needs research":
        score += 15
    if phone != "Needs research":
        score += 10
    if score >= 75:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"

def enrich(row, enable_search, enable_website_read, timeout):
    try:
        company = get_value(row, "Company")
        city = get_value(row, "City")
        state = get_value(row, "State")
        zip_code = get_value(row, "Zip")
        country = get_value(row, "Country")
        query = make_search_query(company, city, state, zip_code, country)
        source_url = google_search_url(query)

        website = "Needs research"
        page_text = ""

        if enable_search and company:
            results = ddg_search_html(query, timeout=timeout)
            website, website_source = find_best_website(company, results)
            if website_source:
                source_url = website_source

        if enable_website_read and website != "Needs research":
            page_text = fetch_text_once(website, timeout=timeout)

        phone = find_phone(page_text) if page_text else "Needs research"
        address = find_address(page_text, city, state, zip_code, country) if page_text else "Needs research"
        sic, naics, lob = classify(company, website, page_text)
        conf = confidence(company, city, zip_code, country, website, address, phone)

        if website == "Needs research":
            remarks = "Output generated. Website not found; use SourceURL for manual review."
        elif not page_text:
            remarks = "Website found, but page could not be read quickly. Output still generated."
        else:
            remarks = "Output generated with website page extraction."

        return {
            "Company": company,
            "Address": address,
            "City": city or "Needs research",
            "State": state or "Needs research",
            "Zip": zip_code or "Needs research",
            "Country": country or "Needs research",
            "PhoneResearch": phone,
            "Website": website,
            "SIC": sic,
            "NAICS": naics,
            "NoOfEmployees(This site only)": "Not publicly disclosed",
            "LineOfBusiness": lob,
            "ParentName": "Needs research",
            "Confidence": conf,
            "SourceURL": source_url,
            "Remarks": remarks,
        }
    except Exception as e:
        return fallback_row(row, "Error on this row, but output was generated: " + str(e)[:120])

def rows_to_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")

def rows_to_excel_html(rows):
    table = ['<html><head><meta charset="utf-8"></head><body><table border="1">']
    table.append("<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in OUTPUT_COLUMNS) + "</tr>")
    for row in rows:
        table.append("<tr>" + "".join(f"<td>{html.escape(clean(row.get(c, '')))}</td>" for c in OUTPUT_COLUMNS) + "</tr>")
    table.append("</table></body></html>")
    return "\n".join(table).encode("utf-8")

with st.sidebar:
    st.header("Settings")
    enable_search = st.checkbox("Enable website finder", value=True)
    enable_website_read = st.checkbox("Read website homepage", value=False)
    timeout = st.number_input("Timeout seconds", min_value=2, max_value=10, value=5, step=1)
    delay = st.number_input("Delay per row", min_value=0.0, max_value=3.0, value=0.2, step=0.1)
    st.caption("Keep website reading OFF first. Turn it ON only after output works.")

sample_csv = "Company,City,State,Zip,Country\nBoeing,Tanner,AL,35671,USA\nBOEL,Osaka-Shi,,,Japan\n"
uploaded = st.file_uploader("Upload CSV file", type=["csv"])

if uploaded is None:
    st.subheader("Sample CSV")
    st.code(sample_csv)
    st.download_button("Download sample CSV", sample_csv.encode("utf-8"), "sample_input.csv", "text/csv")
else:
    content = uploaded.read().decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    input_rows = list(reader)

    if not input_rows:
        st.error("CSV is empty or headers are missing.")
        st.stop()

    st.write(f"Rows loaded: {len(input_rows)}")
    st.table(input_rows[:10])

    rows_to_process = st.number_input("Rows to process now", 1, len(input_rows), min(len(input_rows), 10), 1)

    if st.button("Run enrichment"):
        output_rows = []
        progress = st.progress(0)
        status = st.empty()
        selected = input_rows[:rows_to_process]

        for idx, row in enumerate(selected, start=1):
            company = get_value(row, "Company")
            status.write(f"Processing {idx}/{len(selected)}: {company}")
            output_rows.append(enrich(row, enable_search, enable_website_read, timeout))
            progress.progress(idx / len(selected))
            time.sleep(delay)

        status.write("Finished.")
        st.success("Output generated.")
        st.subheader("Output preview")
        st.table(output_rows[:20])

        st.download_button("Download CSV", rows_to_csv(output_rows), "company_enrichment_output.csv", "text/csv")
        st.download_button("Download Excel-openable XLS", rows_to_excel_html(output_rows), "company_enrichment_output.xls", "application/vnd.ms-excel")

st.info("If no output appears, turn OFF website finder and website reading, then test again.")
