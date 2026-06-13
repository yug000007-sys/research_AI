import csv
import html
import io
import re
import time
from urllib.parse import quote_plus, urlparse, urljoin

import requests
import streamlit as st

st.set_page_config(page_title="Company Enrichment Tool", layout="wide")

st.title("Company Enrichment Tool - Step 3")
st.success("App loaded successfully.")
st.write("CSV upload → website finder → phone/address extraction → confidence score → downloadable output.")

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
    "google.",
    "duckduckgo.",
    "facebook.",
    "linkedin.",
    "twitter.",
    "x.com",
    "instagram.",
    "youtube.",
    "bloomberg.",
    "dnb.",
    "zoominfo.",
    "yelp.",
    "mapquest.",
    "wikipedia.",
    "crunchbase.",
]

CONTACT_PATHS = ["/contact", "/contact-us", "/contacts", "/about", "/about-us", "/locations", "/location"]

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

def ddg_search_html(query, max_results=8):
    url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    results = []
    try:
        r = requests.get(url, headers=headers, timeout=12)
        text = r.text or ""
        links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
        snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
        for idx, (href, title_html) in enumerate(links[:max_results]):
            title = html.unescape(" ".join(re.sub("<.*?>", " ", title_html).split()))
            body = ""
            if idx < len(snippets):
                snip = snippets[idx][0] or snippets[idx][1]
                body = html.unescape(" ".join(re.sub("<.*?>", " ", snip).split()))
            href = html.unescape(href)
            results.append({"title": title, "href": href, "body": body})
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
        body = result.get("body", "")
        if not href.startswith("http") or domain_is_bad(href):
            continue
        domain_url = extract_domain_url(href)
        domain = urlparse(domain_url).netloc.lower()
        score = 0
        for token in company_tokens:
            if token in domain:
                score += 40
            if token in title.lower():
                score += 20
            if token in body.lower():
                score += 10
        if "official" in (title + " " + body).lower():
            score += 10
        candidates.append((score, domain_url, href))
    if not candidates:
        return "Needs research", ""
    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0][1] or "Needs research", candidates[0][2]

def fetch_text(url):
    if not url or not url.startswith("http"):
        return ""
    headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code >= 400:
            return ""
        text = r.text or ""
        text = re.sub(r"<script.*?</script>", " ", text, flags=re.S|re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S|re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        text = " ".join(text.split())
        return text[:25000]
    except Exception:
        return ""

def read_website_pages(website):
    if not website or website == "Needs research":
        return ""
    texts = []
    texts.append(fetch_text(website))
    for path in CONTACT_PATHS[:5]:
        texts.append(fetch_text(urljoin(website, path)))
        time.sleep(0.1)
    return " ".join([t for t in texts if t])[:50000]

def find_phone(text):
    patterns = [
        r"\+\d{1,3}[\s\-.]?\(?\d{1,5}\)?[\s\-.]?\d{2,5}[\s\-.]?\d{2,5}[\s\-.]?\d{2,6}",
        r"\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}",
        r"\d{2,5}[\s\-.]\d{2,5}[\s\-.]\d{3,5}",
    ]
    blocked = ["000-000", "123-456", "555-555"]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        for m in matches:
            phone = clean(m)
            if not any(b in phone for b in blocked):
                return phone
    return "Needs research"

def find_address(text, city, state, zip_code, country):
    tokens = [x for x in [zip_code, city, state, country] if x]
    if not tokens:
        return "Needs research"
    best = ""
    low = text.lower()
    for token in tokens:
        idx = low.find(token.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 140): min(len(text), idx + 220)]
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if len(snippet) > len(best):
                best = snippet
    if best and len(best) >= 30:
        return best[:300]
    return "Needs research"

def classify_confidence(company, city, zip_code, country, website, address, phone, results):
    combined = " ".join((r.get("title", "") + " " + r.get("body", "") + " " + r.get("href", "")) for r in results).lower()
    score = 0
    if company and company.lower().split()[0] in combined:
        score += 25
    if city and city.lower() in combined:
        score += 15
    if zip_code and zip_code.lower() in combined:
        score += 15
    if country and country.lower() in combined:
        score += 10
    if website and website != "Needs research":
        score += 15
    if address and address != "Needs research":
        score += 10
    if phone and phone != "Needs research":
        score += 10
    if score >= 75:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"

def classify_sic_naics(company, website, page_text):
    text = (company + " " + website + " " + page_text[:4000]).lower()
    if any(x in text for x in ["boeing", "aerospace", "aircraft", "aviation", "defense", "missile"]):
        return "3721 / 3761", "336411 / 336414", "Aerospace and defense manufacturing, engineering, and support services."
    if any(x in text for x in ["software", "saas", "technology", "cloud", "cybersecurity", "it services"]):
        return "7372 / 7373", "541511 / 541512", "Software, IT, or technology services."
    if any(x in text for x in ["logistics", "freight", "transport", "warehouse"]):
        return "4731 / 4225", "488510 / 493110", "Logistics, freight, warehousing, and transportation services."
    if any(x in text for x in ["consulting", "consultant", "advisory"]):
        return "8742 / 8748", "541611", "Business or management consulting services."
    if any(x in text for x in ["manufacturing", "manufacturer", "factory", "industrial"]):
        return "3999 / 3599", "339999 / 333249", "Manufacturing or industrial operations."
    return "Needs classification", "Needs classification", "Needs research"

def create_output_row(row, enable_search, enable_page_read, delay):
    company = get_value(row, "Company")
    city = get_value(row, "City")
    state = get_value(row, "State")
    zip_code = get_value(row, "Zip")
    country = get_value(row, "Country")

    query = make_search_query(company, city, state, zip_code, country)
    source_url = google_search_url(query)
    website = "Needs research"
    results = []
    page_text = ""

    if enable_search and company:
        results = ddg_search_html(query, max_results=8)
        website, website_source = find_best_website(company, results)
        if website_source:
            source_url = website_source
        time.sleep(delay)

    if enable_page_read and website != "Needs research":
        page_text = read_website_pages(website)

    phone = find_phone(page_text) if page_text else "Needs research"
    address = find_address(page_text, city, state, zip_code, country) if page_text else "Needs research"
    sic, naics, lob = classify_sic_naics(company, website, page_text)
    confidence = classify_confidence(company, city, zip_code, country, website, address, phone, results)

    remarks = "Website, phone, and address extraction completed. Review Low/Medium confidence rows."
    if website == "Needs research":
        remarks = "No reliable website found. Review SourceURL manually."
    elif address == "Needs research" and phone == "Needs research":
        remarks = "Website found, but address/phone not extracted. Website may block reading or use images/scripts."

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
        "Confidence": confidence,
        "SourceURL": source_url,
        "Remarks": remarks,
    }

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
    enable_page_read = st.checkbox("Read website/contact pages", value=True)
    delay = st.number_input("Delay per record", min_value=0.0, max_value=5.0, value=0.7, step=0.1)
    st.caption("Free Streamlit Cloud: process 5–20 rows first.")

sample_csv = "Company,City,State,Zip,Country\nBoeing,Tanner,AL,35671,USA\nBOEL,Osaka-Shi,,,Japan\n"
uploaded = st.file_uploader("Upload CSV file", type=["csv"])

if uploaded is None:
    st.subheader("Sample CSV format")
    st.code(sample_csv)
    st.download_button("Download sample CSV", sample_csv.encode("utf-8"), "sample_input.csv", "text/csv")
else:
    try:
        content = uploaded.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        input_rows = list(reader)

        if not input_rows:
            st.error("CSV is empty or headers are missing.")
            st.stop()

        st.write(f"Rows loaded: {len(input_rows)}")
        st.subheader("Input preview")
        st.table(input_rows[:10])

        rows_to_process = st.number_input("Rows to process now", 1, len(input_rows), min(len(input_rows), 10), 1)

        if st.button("Run enrichment"):
            progress = st.progress(0)
            status = st.empty()
            output_rows = []
            selected_rows = input_rows[:rows_to_process]

            for idx, row in enumerate(selected_rows, start=1):
                company = get_value(row, "Company")
                status.write(f"Processing {idx}/{len(selected_rows)}: {company}")
                output_rows.append(create_output_row(row, enable_search, enable_page_read, delay))
                progress.progress(idx / len(selected_rows))

            st.success("Done.")
            st.subheader("Output preview")
            st.table(output_rows[:20])

            st.download_button("Download CSV", rows_to_csv(output_rows), "company_enrichment_output.csv", "text/csv")
            st.download_button("Download Excel-openable XLS", rows_to_excel_html(output_rows), "company_enrichment_output.xls", "application/vnd.ms-excel")

    except Exception as e:
        st.error("Error processing CSV")
        st.exception(e)

st.info("Next step after this works: add optional Gemini AI enrichment to clean and format the fields more like ChatGPT.")
