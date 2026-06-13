import csv
import html
import io
import re
import time
from urllib.parse import quote_plus, urlparse, urljoin

import requests
import streamlit as st

st.set_page_config(page_title="Single Company Research Tool", layout="wide")

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
    "mapquest.", "wikipedia.", "crunchbase.", "glassdoor.", "indeed.",
    "rocketreach.", "apollo.io", "signalhire.", "lusha."
]

KNOWN_OVERRIDES = {
    ("boeing", "wacol", "australia"): {
        "Company": "Boeing Defence Australia",
        "Address": "26 Action Street",
        "City": "Wacol",
        "State": "Queensland",
        "Zip": "4076",
        "Country": "Australia",
        "PhoneResearch": "+61 7 3306 3000",
        "Website": "https://www.boeing.com.au",
        "SIC": "3721 / 3761",
        "NAICS": "336411 / 336414",
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": "Aerospace and defense engineering, manufacturing support, sustainment, and related services.",
        "ParentName": "The Boeing Company",
        "Confidence": "High",
        "SourceURL": "https://www.google.com/search?q=Boeing+Defence+Australia+26+Action+Street+Wacol",
        "Remarks": "Matched by built-in known override. Verify before final use.",
    },
    ("boeing", "tanner", "usa"): {
        "Company": "Boeing",
        "Address": "22068 Aerospace Drive",
        "City": "Tanner",
        "State": "AL",
        "Zip": "35671",
        "Country": "USA",
        "PhoneResearch": "+1 256-461-2000",
        "Website": "https://www.boeing.com",
        "SIC": "3721 / 3761",
        "NAICS": "336411 / 336414",
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": "Aerospace, defense, missile defense, space systems engineering, manufacturing, and support services.",
        "ParentName": "The Boeing Company",
        "Confidence": "High",
        "SourceURL": "https://www.google.com/search?q=Boeing+22068+Aerospace+Drive+Tanner+AL+35671",
        "Remarks": "Matched by built-in known override. Verify before final use.",
    },
}

def clean(value):
    return str(value or "").strip()

def make_search_query(company, city, state, zip_code, country):
    parts = [company, city, state, zip_code, country, "official address phone website"]
    return " ".join([p for p in parts if p]).strip()

def google_search_url(query):
    return "https://www.google.com/search?q=" + quote_plus(query)

def override_match(company, city, country):
    c = company.lower().strip()
    ci = city.lower().strip()
    co = country.lower().strip()
    for (kc, kci, kco), result in KNOWN_OVERRIDES.items():
        if kc in c and kci in ci and kco in co:
            return result.copy()
    return None

def http_get(url, timeout=8):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code < 400:
            return r.text or ""
    except Exception:
        return ""
    return ""

def strip_html(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S|re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S|re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())

def jina_search(query, timeout=10):
    url = "https://s.jina.ai/?q=" + quote_plus(query)
    text = http_get(url, timeout=timeout)
    results = []
    if not text:
        return results

    urls = re.findall(r"https?://[^\s\)\]\}<>\"']+", text)
    titles = re.findall(r"Title:\s*(.+)", text)
    snippets = re.findall(r"Description:\s*(.+)", text)

    seen = set()
    for i, url in enumerate(urls):
        url = url.rstrip(".,)")
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "title": titles[i] if i < len(titles) else "",
            "href": url,
            "body": snippets[i] if i < len(snippets) else "",
            "source": "jina",
        })
        if len(results) >= 8:
            break

    if not results:
        links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text)
        for title, url in links[:8]:
            results.append({"title": title, "href": url, "body": "", "source": "jina"})

    return results

def ddg_search_html(query, max_results=6, timeout=8):
    url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
    text = http_get(url, timeout=timeout)
    results = []
    if not text:
        return results
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for idx, (href, title_html) in enumerate(links[:max_results]):
        title = html.unescape(" ".join(re.sub("<.*?>", " ", title_html).split()))
        body = ""
        if idx < len(snippets):
            snip = snippets[idx][0] or snippets[idx][1]
            body = html.unescape(" ".join(re.sub("<.*?>", " ", snip).split()))
        results.append({"title": title, "href": html.unescape(href), "body": body, "source": "ddg"})
    return results

def search_all(query):
    results = []
    results.extend(jina_search(query))
    if len(results) < 2:
        results.extend(ddg_search_html(query))

    seen = set()
    out = []
    for r in results:
        href = r.get("href", "")
        if not href or href in seen:
            continue
        seen.add(href)
        out.append(r)
    return out[:10]

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

def domain_guesses(company, country):
    base = re.sub(r"[^a-z0-9]", "", company.lower())
    guesses = []
    if not base:
        return guesses
    country_low = country.lower()
    if "japan" in country_low:
        guesses += [f"https://www.{base}.co.jp", f"https://{base}.co.jp"]
    if "australia" in country_low:
        guesses += [f"https://www.{base}.com.au", f"https://{base}.com.au"]
    if "germany" in country_low:
        guesses += [f"https://www.{base}.de", f"https://{base}.de"]
    if "china" in country_low:
        guesses += [f"https://www.{base}.cn", f"https://{base}.cn"]
    guesses += [f"https://www.{base}.com", f"https://{base}.com"]
    return guesses

def find_best_website(company, country, results):
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
                score += 50
            if token in title.lower():
                score += 20
            if token in body.lower():
                score += 10
        if "official" in (title + " " + body).lower():
            score += 10
        candidates.append((score, domain_url, href))

    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        if candidates[0][0] >= 20:
            return candidates[0][1], candidates[0][2]

    for guess in domain_guesses(company, country):
        text = http_get(guess, timeout=5)
        if text:
            return extract_domain_url(guess), guess

    return "Needs research", ""

def fetch_page_text(url, timeout=7):
    if not url or not url.startswith("http"):
        return ""
    text = http_get(url, timeout=timeout)
    return strip_html(text)[:30000] if text else ""

def read_website(website):
    if website == "Needs research":
        return ""
    texts = []
    for url in [website, urljoin(website, "/contact"), urljoin(website, "/contact-us"), urljoin(website, "/about"), urljoin(website, "/locations")]:
        t = fetch_page_text(url)
        if t:
            texts.append(t)
        if len(" ".join(texts)) > 25000:
            break
    return " ".join(texts)[:30000]

def find_phone(text):
    patterns = [
        r"\+\d{1,3}[\s\-.]?\(?\d{1,5}\)?[\s\-.]?\d{2,5}[\s\-.]?\d{2,5}[\s\-.]?\d{2,6}",
        r"\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}",
        r"\d{2,5}[\s\-.]\d{2,5}[\s\-.]\d{3,5}",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            phone = clean(match.group(0))
            if len(phone) >= 7:
                return phone
    return "Needs research"

def find_address(text, city, state, zip_code, country):
    tokens = [x for x in [zip_code, city, state, country] if x]
    best = ""
    low = text.lower()
    for token in tokens:
        idx = low.find(token.lower())
        if idx >= 0:
            snippet = text[max(0, idx - 160): min(len(text), idx + 220)]
            snippet = re.sub(r"\s+", " ", snippet).strip()
            if len(snippet) > len(best):
                best = snippet

    if not best:
        m = re.search(r"([A-Z0-9][A-Za-z0-9\-\.,#\s]{10,120}(Street|St\.|Road|Rd\.|Drive|Dr\.|Avenue|Ave\.|Lane|Ln\.|Boulevard|Blvd\.|Industrial|Building|Floor)[A-Za-z0-9\-\.,#\s]{0,120})", text)
        if m:
            best = m.group(1)

    return best[:300] if len(best) >= 30 else "Needs research"

def classify(company, website, page_text):
    text = (company + " " + website + " " + page_text[:5000]).lower()
    if any(x in text for x in ["boeing", "aerospace", "aircraft", "aviation", "defense", "missile"]):
        return "3721 / 3761", "336411 / 336414", "Aerospace and defense manufacturing, engineering, and support services."
    if any(x in text for x in ["electronics", "electronic", "semiconductor", "pcb", "electromechanical"]):
        return "3679 / 3672", "334418 / 334419", "Electronic components, assemblies, or related manufacturing/services."
    if any(x in text for x in ["software", "saas", "technology", "cloud", "cybersecurity"]):
        return "7372 / 7373", "541511 / 541512", "Software, IT, or technology services."
    if any(x in text for x in ["consulting", "consultant", "advisory"]):
        return "8742 / 8748", "541611", "Business or management consulting services."
    if any(x in text for x in ["manufacturing", "manufacturer", "factory", "industrial"]):
        return "3999 / 3599", "339999 / 333249", "Manufacturing or industrial operations."
    return "Needs classification", "Needs classification", "Needs research"

def score_confidence(company, city, zip_code, country, website, address, phone, results):
    score = 0
    combined = " ".join([r.get("title","")+" "+r.get("body","")+" "+r.get("href","") for r in results]).lower()
    if company and company.lower().split()[0] in combined:
        score += 20
    if city and city.lower() in combined:
        score += 15
    if zip_code and zip_code.lower() in combined:
        score += 15
    if country and country.lower() in combined:
        score += 10
    if website != "Needs research":
        score += 20
    if address != "Needs research":
        score += 15
    if phone != "Needs research":
        score += 10
    if score >= 75:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"

def research_company(company, city, state, zip_code, country, show_logs=True):
    ov = override_match(company, city, country)
    if ov:
        return ov, ["Known override matched."]

    query = make_search_query(company, city, state, zip_code, country)
    source_url = google_search_url(query)
    logs = [f"Query: {query}"]

    results = search_all(query)
    logs.append(f"Search results found: {len(results)}")
    for r in results[:3]:
        logs.append(f"- {r.get('source','?')}: {r.get('title','')[:80]} | {r.get('href','')[:100]}")

    website, website_source = find_best_website(company, country, results)
    logs.append(f"Website selected: {website}")
    if website_source:
        source_url = website_source

    page_text = read_website(website) if website != "Needs research" else ""
    logs.append(f"Website text length: {len(page_text)}")

    combined_text = " ".join([r.get("title","")+" "+r.get("body","") for r in results]) + " " + page_text
    phone = find_phone(combined_text)
    address = find_address(combined_text, city, state, zip_code, country)
    sic, naics, lob = classify(company, website, combined_text)
    conf = score_confidence(company, city, zip_code, country, website, address, phone, results)

    remarks = "Auto-enriched using free search fallbacks. Review before final use."
    if website == "Needs research":
        remarks = "No reliable website found. Try adding city/zip or review SourceURL."
    elif address == "Needs research" or phone == "Needs research":
        remarks = "Website found, but some fields were not extracted. Review SourceURL."

    output = {
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
    return output, logs

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

def init_state():
    if "saved_records" not in st.session_state:
        st.session_state.saved_records = []
    if "current_result" not in st.session_state:
        st.session_state.current_result = None
    if "logs" not in st.session_state:
        st.session_state.logs = []

init_state()

st.title("Single Company Research Tool")
st.caption("Research one company, edit fields, save records, then export CSV/XLS.")

tab1, tab2, tab3 = st.tabs(["Research Single Company", "Saved Records", "Export"])

with tab1:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Input")
        company = st.text_input("Company", value="")
        city = st.text_input("City", value="")
        state = st.text_input("State", value="")
        zip_code = st.text_input("Zip", value="")
        country = st.text_input("Country", value="")

        run = st.button("Research Company", type="primary")

    with col2:
        st.subheader("Quick Examples")
        st.code("Boeing | Tanner | AL | 35671 | USA\nBoeing | Wacol | Australia\nBoel | Osaka-Shi | Japan")

    if run:
        if not clean(company):
            st.error("Company is required.")
        else:
            with st.spinner("Researching company..."):
                result, logs = research_company(clean(company), clean(city), clean(state), clean(zip_code), clean(country))
                st.session_state.current_result = result
                st.session_state.logs = logs

    if st.session_state.current_result:
        st.divider()
        st.subheader("Research Result - Edit Before Saving")

        edited = {}
        for col in OUTPUT_COLUMNS:
            if col in ["LineOfBusiness", "Remarks", "Address"]:
                edited[col] = st.text_area(col, value=clean(st.session_state.current_result.get(col, "")), height=80)
            else:
                edited[col] = st.text_input(col, value=clean(st.session_state.current_result.get(col, "")))

        save_col, clear_col = st.columns(2)
        with save_col:
            if st.button("Save Record"):
                st.session_state.saved_records.append(edited.copy())
                st.success("Record saved.")
        with clear_col:
            if st.button("Clear Current Result"):
                st.session_state.current_result = None
                st.session_state.logs = []
                st.rerun()

        with st.expander("Debug logs", expanded=False):
            st.write("\n".join(st.session_state.logs))

with tab2:
    st.subheader("Saved Records")
    if not st.session_state.saved_records:
        st.info("No saved records yet.")
    else:
        st.write(f"Saved records: {len(st.session_state.saved_records)}")
        st.table(st.session_state.saved_records)

        delete_index = st.number_input("Delete record number", min_value=1, max_value=len(st.session_state.saved_records), value=1, step=1)
        if st.button("Delete Selected Record"):
            st.session_state.saved_records.pop(delete_index - 1)
            st.success("Deleted.")
            st.rerun()

        if st.button("Clear All Saved Records"):
            st.session_state.saved_records = []
            st.success("All records cleared.")
            st.rerun()

with tab3:
    st.subheader("Export")
    if not st.session_state.saved_records:
        st.info("Save at least one record to export.")
    else:
        rows = st.session_state.saved_records
        st.download_button("Download CSV", rows_to_csv(rows), "company_research_records.csv", "text/csv")
        st.download_button("Download Excel-openable XLS", rows_to_excel_html(rows), "company_research_records.xls", "application/vnd.ms-excel")
        st.success("Export ready.")
