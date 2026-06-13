import csv
import html
import io
import re
from urllib.parse import quote_plus, urlparse, urljoin

import requests
import streamlit as st

st.set_page_config(page_title="Single Company Research Tool", layout="wide")

OUTPUT_COLUMNS = [
    "Company","Address","City","State","Zip","Country","PhoneResearch","Website",
    "SIC","NAICS","NoOfEmployees(This site only)","LineOfBusiness","ParentName",
    "Confidence","SourceURL","Remarks",
]

BAD_DOMAINS = [
    "google.", "duckduckgo.", "facebook.", "linkedin.", "twitter.", "x.com",
    "instagram.", "youtube.", "bloomberg.", "dnb.", "zoominfo.", "yelp.",
    "mapquest.", "wikipedia.", "crunchbase.", "glassdoor.", "indeed.",
    "rocketreach.", "apollo.io", "signalhire.", "lusha.", "b2bhint."
]

STOP_PHRASES = [
    " điện thoại", " phone", " tel", " telephone", " fax", " email", " website",
    " explore", " import-export", " shipments", " volza", " b2bhint", " linkedin",
    " google reviews", " suggest an edit", " own this business", " add missing information",
    " read more", " login", " download", " request an update", " account access",
    " not in process", " company profile", " copyright", " privacy policy", " terms of",
]

COUNTRY_WORDS = {
    "usa": "United States",
    "united states": "United States",
    "u.s.a.": "United States",
    "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "vietnam": "Vietnam",
    "viet nam": "Vietnam",
    "japan": "Japan",
    "australia": "Australia",
}

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

def clean(v):
    return str(v or "").strip()

def google_search_url(q):
    return "https://www.google.com/search?q=" + quote_plus(q)

def google_maps_url(company, city, state, zip_code, country):
    q = " ".join([x for x in [company, city, state, zip_code, country] if x])
    return "https://www.google.com/maps/search/" + quote_plus(q)

def make_search_query(company, city, state, zip_code, country):
    return " ".join([x for x in [company, city, state, zip_code, country, "official address phone website"] if x])

def override_match(company, city, country):
    c, ci, co = company.lower().strip(), city.lower().strip(), country.lower().strip()
    for (kc, kci, kco), result in KNOWN_OVERRIDES.items():
        if kc in c and kci in ci and kco in co:
            return result.copy()
    return None

def http_get(url, timeout=8):
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9"},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code < 400:
            return r.text or ""
    except Exception:
        pass
    return ""

def strip_html(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())

def jina_search(query):
    text = http_get("https://s.jina.ai/?q=" + quote_plus(query), timeout=10)
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
    return results

def ddg_search_html(query):
    text = http_get("https://duckduckgo.com/html/?q=" + quote_plus(query), timeout=8)
    results = []
    if not text:
        return results
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for idx, (href, title_html) in enumerate(links[:6]):
        title = html.unescape(" ".join(re.sub("<.*?>", " ", title_html).split()))
        body = ""
        if idx < len(snippets):
            snip = snippets[idx][0] or snippets[idx][1]
            body = html.unescape(" ".join(re.sub("<.*?>", " ", snip).split()))
        results.append({"title": title, "href": html.unescape(href), "body": body, "source": "ddg"})
    return results

def search_all(query):
    results = jina_search(query)
    if len(results) < 2:
        results += ddg_search_html(query)
    out, seen = [], set()
    for r in results:
        href = r.get("href", "")
        if href and href not in seen:
            seen.add(href)
            out.append(r)
    return out[:10]

def domain_is_bad(url):
    netloc = urlparse(url).netloc.lower()
    return any(bad in netloc for bad in BAD_DOMAINS)

def extract_domain_url(url):
    p = urlparse(url)
    if p.scheme and p.netloc:
        return p.scheme + "://" + p.netloc
    return ""

def find_best_website(company, country, results):
    company_tokens = [t for t in re.split(r"[^a-z0-9]+", company.lower()) if len(t) >= 3]
    candidates = []
    for r in results:
        href = r.get("href", "")
        if not href.startswith("http") or domain_is_bad(href):
            continue
        domain_url = extract_domain_url(href)
        domain = urlparse(domain_url).netloc.lower()
        text = (r.get("title", "") + " " + r.get("body", "")).lower()
        score = 0
        for token in company_tokens:
            if token in domain: score += 50
            if token in text: score += 20
        if "official" in text: score += 10
        candidates.append((score, domain_url, href))
    if candidates:
        candidates.sort(reverse=True, key=lambda x: x[0])
        if candidates[0][0] >= 20:
            return candidates[0][1], candidates[0][2]
    return "Needs research", ""

def fetch_page_text(url):
    if not url or not url.startswith("http"):
        return ""
    return strip_html(http_get(url, timeout=7))[:30000]

def read_website(website):
    if website == "Needs research":
        return ""
    pages = [website, urljoin(website, "/contact"), urljoin(website, "/contact-us"), urljoin(website, "/about"), urljoin(website, "/locations")]
    chunks = []
    for p in pages:
        t = fetch_page_text(p)
        if t:
            chunks.append(t)
        if len(" ".join(chunks)) > 25000:
            break
    return " ".join(chunks)[:30000]

def find_phone(text):
    patterns = [
        r"\+\d{1,3}[\s\-.]?\(?\d{1,5}\)?[\s\-.]?\d{2,5}[\s\-.]?\d{2,5}[\s\-.]?\d{2,6}",
        r"\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}",
        r"\d{2,5}[\s\-.]\d{2,5}[\s\-.]\d{3,5}",
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return clean(m.group(0))
    return "Needs research"

def cut_at_stop_phrases(text):
    low = text.lower()
    cut = len(text)
    for phrase in STOP_PHRASES:
        idx = low.find(phrase)
        if idx >= 0 and idx < cut:
            cut = idx
    return text[:cut].strip()

def remove_company_tail(text):
    # Remove repeated company-directory tail like "C&k Components (vietnam) Co. ..."
    patterns = [
        r"\s+[A-Z0-9&\-\., ]+\s+(Co\.?|Company|Ltd\.?|LLC|L\.L\.C|Inc\.?|GmbH|S\.A\.|Pte\.?)\b.*$",
        r"\s+Explore\s+.*$",
        r"\s+Volza\.com\s+.*$",
    ]
    out = text
    for p in patterns:
        out = re.sub(p, "", out, flags=re.I)
    return out.strip(" ,;-")

def clean_address_text(text):
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(Address|Registered Address|Location|Office|Head Office)\s*[:\-]\s*", "", text, flags=re.I)
    text = cut_at_stop_phrases(text)
    text = remove_company_tail(text)
    text = re.sub(r"\b(P\.?\s*O\.?\s*Box)\b", "PO Box", text, flags=re.I)
    return text.strip(" ,;-")[:180]

def has_address_marker(text):
    low = " " + text.lower() + " "
    markers = [
        " street ", " st ", " st. ", " road ", " rd ", " rd. ", " drive ", " dr ",
        " avenue ", " ave ", " lane ", " boulevard ", " building ", " warehouse ",
        " floor ", " suite ", " unit ", " po box ", " p.o. ", " industrial ",
        " business park ", " free zone ", " city ", " area ", " district ",
        " ngõ ", " ngach ", " phố ", " đường ", " phường ", " quận ",
        " warsan ", " jebel ali ", " al jaddaf ", " drydocks "
    ]
    return any(m in low for m in markers)

def bad_address(text):
    low = text.lower()
    bad = [
        "login required", "download or request", "followers", "reviews", "read more",
        "not in process of liquidation", "available options", "account access",
        "company profile", "b2bhint", "linkedin", "copyright", "privacy policy",
        "terms of service", "cookie", "sign in", "register", "search result",
        "import-export shipments", "explore", "volza.com"
    ]
    return any(b in low for b in bad)

def score_address(s, city, state, zip_code, country):
    low = s.lower()
    score = 0
    if has_address_marker(s): score += 35
    if re.search(r"\b\d{1,6}[A-Za-z]?\b", s): score += 20
    if city and city.lower() in low: score += 25
    if state and state.lower() in low: score += 10
    if zip_code and zip_code.lower() in low: score += 25
    if country and (country.lower() in low or COUNTRY_WORDS.get(country.lower(), "").lower() in low): score += 10
    if bad_address(s): score -= 70
    if len(s) > 220: score -= 20
    return score

def extract_candidates(text, city, state, zip_code, country):
    candidates = []

    # Pull from explicit Address: labels
    for m in re.finditer(r"(Address|Registered Address|Location|Office|Head Office)\s*[:\-]\s*([^|;\n]{20,240})", text, flags=re.I):
        candidates.append(m.group(2))

    # Pull chunks around likely address keywords
    marker_regex = r"([A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,90}(?:ngách|ngõ|phố|đường|Street|St\.|Road|Rd\.|Drive|Dr\.|Avenue|Ave\.|Lane|Ln\.|Building|Warehouse|Floor|Suite|Unit|PO Box|P\.O\. Box|Industrial|Business Park|Free Zone|Dubai International City|Warsan First|Jebel Ali|Al Jaddaf|Drydocks)[A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,140})"
    for m in re.finditer(marker_regex, text, flags=re.I):
        candidates.append(m.group(1))

    # Pull around city/zip/country but only in smaller windows.
    low = text.lower()
    for token in [zip_code, city, state, country]:
        if not token: 
            continue
        token_low = token.lower()
        start = 0
        while True:
            idx = low.find(token_low, start)
            if idx < 0:
                break
            candidates.append(text[max(0, idx - 100):min(len(text), idx + 120)])
            start = idx + len(token_low)

    return candidates

def find_address(text, city, state, zip_code, country):
    scored = []
    for raw in extract_candidates(text, city, state, zip_code, country):
        cand = clean_address_text(raw)
        if len(cand) < 15:
            continue
        if bad_address(cand):
            continue
        score = score_address(cand, city, state, zip_code, country)
        if score >= 25:
            scored.append((score, cand))

    if not scored:
        return "Needs research"

    scored.sort(reverse=True, key=lambda x: x[0])
    return scored[0][1]

def classify(company, website, text):
    low = (company + " " + website + " " + text[:5000]).lower()
    if any(x in low for x in ["aerospace", "aircraft", "aviation", "defense", "missile", "boeing"]):
        return "3721 / 3761", "336411 / 336414", "Aerospace and defense manufacturing, engineering, and support services."
    if any(x in low for x in ["marine", "maritime", "ship", "vessel", "propulsion"]):
        return "3731 / 4499", "336611 / 488390", "Marine, maritime, vessel technology, or related services."
    if any(x in low for x in ["electronics", "electronic", "semiconductor", "pcb", "component"]):
        return "3679 / 3672", "334418 / 334419", "Electronic components, assemblies, or related manufacturing/services."
    if any(x in low for x in ["software", "saas", "technology", "cloud", "cybersecurity"]):
        return "7372 / 7373", "541511 / 541512", "Software, IT, or technology services."
    if any(x in low for x in ["manufacturing", "manufacturer", "factory", "industrial"]):
        return "3999 / 3599", "339999 / 333249", "Manufacturing or industrial operations."
    return "Needs classification", "Needs classification", "Needs research"

def confidence(company, city, zip_code, country, website, address, phone, results):
    score = 0
    combined = " ".join([r.get("title","")+" "+r.get("body","")+" "+r.get("href","") for r in results]).lower()
    if company and company.lower().split()[0] in combined: score += 20
    if city and city.lower() in combined: score += 15
    if zip_code and zip_code.lower() in combined: score += 15
    if country and country.lower() in combined: score += 10
    if website != "Needs research": score += 20
    if address != "Needs research": score += 15
    if phone != "Needs research": score += 10
    return "High" if score >= 75 else "Medium" if score >= 45 else "Low"

def research_company(company, city, state, zip_code, country):
    ov = override_match(company, city, country)
    if ov:
        return ov, ["Known override matched."]

    query = make_search_query(company, city, state, zip_code, country)
    source_url = google_search_url(query)
    maps = google_maps_url(company, city, state, zip_code, country)
    logs = [f"Query: {query}", f"Google Maps URL: {maps}"]

    results = search_all(query)
    logs.append(f"Search results found: {len(results)}")
    for r in results[:5]:
        logs.append(f"- {r.get('source','?')}: {r.get('title','')[:90]} | {r.get('href','')[:110]}")

    website, website_source = find_best_website(company, country, results)
    if website_source:
        source_url = website_source

    page_text = read_website(website) if website != "Needs research" else ""
    combined = " ".join([r.get("title","")+" "+r.get("body","") for r in results]) + " " + page_text

    phone = find_phone(combined)
    address = find_address(combined, city, state, zip_code, country)
    sic, naics, lob = classify(company, website, combined)
    conf = confidence(company, city, zip_code, country, website, address, phone, results)

    remarks = "Auto-enriched using free search fallbacks. Review before final use."
    if address == "Needs research":
        remarks = "Address not safely extracted. Use Google Maps and paste into Manual Google Address."
    elif phone == "Needs research":
        remarks = "Address extracted, but phone not found. Review SourceURL."

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
    }, logs

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

if "saved_records" not in st.session_state:
    st.session_state.saved_records = []
if "current_result" not in st.session_state:
    st.session_state.current_result = None
if "logs" not in st.session_state:
    st.session_state.logs = []

st.title("Single Company Research Tool")
st.caption("v3: cleaner address extraction and formatting.")

tab1, tab2, tab3 = st.tabs(["Research Single Company", "Saved Records", "Export"])

with tab1:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Input")
        company = st.text_input("Company")
        city = st.text_input("City")
        state = st.text_input("State")
        zip_code = st.text_input("Zip")
        country = st.text_input("Country")
        run = st.button("Research Company", type="primary")
    with col2:
        st.subheader("Google helper")
        helper_q = " ".join([x for x in [company, city, state, zip_code, country] if x])
        if helper_q:
            st.link_button("Open Google Search", google_search_url(helper_q + " address phone website"))
            st.link_button("Open Google Maps", google_maps_url(company, city, state, zip_code, country))
        st.caption("When Google Maps has the clean address, paste it below and click Use Manual Address.")

    if run:
        if not clean(company):
            st.error("Company is required.")
        else:
            with st.spinner("Researching company..."):
                st.session_state.current_result, st.session_state.logs = research_company(clean(company), clean(city), clean(state), clean(zip_code), clean(country))

    if st.session_state.current_result:
        st.divider()
        st.subheader("Manual correction from Google panel")
        manual_addr = st.text_input("Manual Google Address (optional)")
        if st.button("Use Manual Address"):
            if manual_addr.strip():
                st.session_state.current_result["Address"] = clean_address_text(manual_addr)
                st.session_state.current_result["Remarks"] = "Address manually corrected from Google panel."
                st.success("Manual address applied.")
            else:
                st.warning("Paste an address first.")

        st.subheader("Research Result - Edit Before Saving")
        edited = {}
        for col in OUTPUT_COLUMNS:
            val = clean(st.session_state.current_result.get(col, ""))
            if col in ["Address", "LineOfBusiness", "Remarks"]:
                edited[col] = st.text_area(col, value=val, height=80)
            else:
                edited[col] = st.text_input(col, value=val)

        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save Record"):
                st.session_state.saved_records.append(edited.copy())
                st.success("Record saved.")
        with c2:
            if st.button("Clear Current Result"):
                st.session_state.current_result = None
                st.session_state.logs = []
                st.rerun()

        with st.expander("Debug logs"):
            st.write("\n".join(st.session_state.logs))

with tab2:
    st.subheader("Saved Records")
    if not st.session_state.saved_records:
        st.info("No saved records yet.")
    else:
        st.write(f"Saved records: {len(st.session_state.saved_records)}")
        st.table(st.session_state.saved_records)
        delete_index = st.number_input("Delete record number", min_value=1, max_value=len(st.session_state.saved_records), value=1)
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
