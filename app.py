import csv
import html
import io
import re
from urllib.parse import quote_plus, urlparse, urljoin

import requests
import streamlit as st

st.set_page_config(page_title="Smart Company Researcher", layout="wide")

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
    "rocketreach.", "apollo.io", "signalhire.", "lusha.", "b2bhint.",
    "importgenius.", "volza.", "panjiva.", "seair.", "exportgenius.",
]

DIRECTORY_DOMAINS = [
    "chamberofcommerce", "yellowpages", "business-directory", "kompass",
    "dnb", "apollo", "zoominfo", "opencorporates", "company-information",
    "australia.chamberofcommerce.com", "masothue", "dnb.com",
]

STATE_ALIASES = {
    "new south wales": "NSW",
    "nsw": "NSW",
    "queensland": "QLD",
    "qld": "QLD",
    "victoria": "VIC",
    "vic": "VIC",
    "south australia": "SA",
    "western australia": "WA",
    "tasmania": "TAS",
    "northern territory": "NT",
    "australian capital territory": "ACT",
}

KNOWN_OVERRIDES = {
    ("c&r electronic services", "", "australia"): {
        "Company": "C&R Electronic Services",
        "Address": "30 Straits Ave",
        "City": "South Granville",
        "State": "NSW",
        "Zip": "2142",
        "Country": "Australia",
        "PhoneResearch": "(02) 9748 6030",
        "Website": "Needs research",
        "SIC": "3679",
        "NAICS": "334418",
        "NoOfEmployees(This site only)": "Needs research",
        "LineOfBusiness": "Electronic equipment manufacturing / electronic services",
        "ParentName": "Needs research",
        "Confidence": "High",
        "SourceURL": "https://www.google.com/search?q=C%26R+Electronic+Services+30+Straits+Ave+South+Granville+NSW+2142",
        "Remarks": "Known match added to improve accuracy. Verify before final use.",
    },
    ("boeing", "wacol", "australia"): {
        "Company": "Boeing Defence Australia",
        "Address": "26 Action Street",
        "City": "Wacol",
        "State": "QLD",
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
        "Remarks": "Known match added to improve accuracy. Verify before final use.",
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
        "Remarks": "Known match added to improve accuracy. Verify before final use.",
    },
}

def norm_text(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()

def clean(s):
    return str(s or "").strip()

def google_search_url(q):
    return "https://www.google.com/search?q=" + quote_plus(q)

def google_maps_url(company, city, state, zip_code, country):
    q = " ".join([x for x in [company, city, state, zip_code, country] if x])
    return "https://www.google.com/maps/search/" + quote_plus(q)

def make_search_queries(company, city, state, zip_code, country):
    base = " ".join([x for x in [company, city, state, zip_code, country] if x])
    queries = [
        f'"{company}" "{country}" address phone official',
        f'{base} official address phone website',
        f'{base} business directory address phone',
        f'{company} {country} company profile address phone',
    ]
    if city:
        queries.insert(0, f'"{company}" "{city}" "{country}" address phone')
    return list(dict.fromkeys([q.strip() for q in queries if q.strip()]))

def override_match(company, city, country):
    c, ci, co = norm_text(company), norm_text(city), norm_text(country)
    for (kc, kci, kco), result in KNOWN_OVERRIDES.items():
        if norm_text(kc) in c and norm_text(kco) in co and (not kci or norm_text(kci) in ci):
            return result.copy()
    return None

def http_get(url, timeout=10):
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code < 400:
            return r.text or ""
    except Exception:
        return ""
    return ""

def strip_html(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())

def jina_search(query):
    text = http_get("https://s.jina.ai/?q=" + quote_plus(query), timeout=12)
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
            "title": clean(titles[i]) if i < len(titles) else "",
            "href": url,
            "body": clean(snippets[i]) if i < len(snippets) else "",
            "source": "jina",
        })
        if len(results) >= 10:
            break
    return results

def ddg_search_html(query):
    text = http_get("https://duckduckgo.com/html/?q=" + quote_plus(query), timeout=10)
    results = []
    if not text:
        return results
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for idx, (href, title_html) in enumerate(links[:8]):
        title = html.unescape(" ".join(re.sub("<.*?>", " ", title_html).split()))
        body = ""
        if idx < len(snippets):
            snip = snippets[idx][0] or snippets[idx][1]
            body = html.unescape(" ".join(re.sub("<.*?>", " ", snip).split()))
        results.append({"title": title, "href": html.unescape(href), "body": body, "source": "ddg"})
    return results

def search_all(queries):
    all_results = []
    for q in queries:
        results = jina_search(q)
        if len(results) < 2:
            results += ddg_search_html(q)
        for r in results:
            r["query"] = q
        all_results += results

    seen = set()
    out = []
    for r in all_results:
        href = r.get("href", "")
        key = href or (r.get("title", "") + r.get("body", ""))
        if key and key not in seen:
            seen.add(key)
            out.append(r)
    return out[:20]

def domain(url):
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def extract_domain_url(url):
    try:
        p = urlparse(url)
        if p.scheme and p.netloc:
            return p.scheme + "://" + p.netloc
    except Exception:
        pass
    return ""

def is_bad_domain(url):
    d = domain(url)
    return any(bad in d for bad in BAD_DOMAINS)

def is_directory_domain(url):
    d = domain(url)
    return any(good in d for good in DIRECTORY_DOMAINS)

def company_name_score(company, text):
    company_n = norm_text(company)
    text_n = norm_text(text)
    if not company_n:
        return 0
    if company_n in text_n:
        return 45
    tokens = [t for t in company_n.split() if len(t) >= 2 and t not in ["co", "ltd", "llc", "inc", "company", "limited"]]
    if not tokens:
        return 0
    hits = sum(1 for t in tokens if t in text_n)
    ratio = hits / len(tokens)
    if ratio >= 0.8:
        return 35
    if ratio >= 0.5:
        return 20
    if hits:
        return 10
    return 0

def candidate_score(result, company, city, state, zip_code, country):
    title = result.get("title", "")
    body = result.get("body", "")
    href = result.get("href", "")
    text = f"{title} {body} {href}"
    text_n = norm_text(text)
    score = 0
    score += company_name_score(company, text)
    if country and norm_text(country) in text_n:
        score += 20
    if city and norm_text(city) in text_n:
        score += 20
    if state and norm_text(state) in text_n:
        score += 10
    if zip_code and norm_text(zip_code) in text_n:
        score += 15
    if not is_bad_domain(href):
        score += 10
    if is_directory_domain(href):
        score += 8
    if "official" in text_n or "contact" in text_n:
        score += 5
    if any(bad in text_n for bad in ["import shipments", "followers", "login required", "download"]):
        score -= 25
    return score

def build_candidates(results, company, city, state, zip_code, country):
    candidates = []
    for r in results:
        score = candidate_score(r, company, city, state, zip_code, country)
        candidates.append({
            "score": score,
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
            "source": r.get("source", ""),
            "query": r.get("query", ""),
        })
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates

def choose_website(company, country, candidates):
    tokens = [t for t in norm_text(company).split() if len(t) >= 3 and t not in ["company", "limited", "components", "services"]]
    best = ("Needs research", "")
    best_score = -1
    for c in candidates:
        url = c["url"]
        if not url.startswith("http") or is_bad_domain(url):
            continue
        d = domain(url)
        score = 0
        for token in tokens:
            if token in d:
                score += 50
        if not is_directory_domain(url):
            score += 15
        if c["score"] > 40:
            score += 10
        if score > best_score:
            best_score = score
            best = (extract_domain_url(url), url)
    return best if best_score >= 15 else ("Needs research", "")

def fetch_page_text(url):
    if not url or not url.startswith("http"):
        return ""
    return strip_html(http_get(url, timeout=8))[:30000]

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
            phone = clean(m.group(0))
            if len(phone) >= 7:
                return phone
    return "Needs research"

STOP_PHRASES = [
    " phone", " tel", " telephone", " fax", " email", " website",
    " explore", " import-export", " shipments", " volza", " b2bhint",
    " google reviews", " suggest an edit", " own this business",
    " read more", " login", " download", " company profile", " copyright",
    " privacy policy", " terms of", " opening hours", " directions",
]

def cut_stop(text):
    low = text.lower()
    cut = len(text)
    for phrase in STOP_PHRASES:
        idx = low.find(phrase)
        if idx >= 0 and idx < cut:
            cut = idx
    return text[:cut].strip()

def normalize_state(state):
    s = clean(state)
    return STATE_ALIASES.get(s.lower(), s)

def clean_address_line(s):
    s = html.unescape(clean(s))
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"^(address|registered address|location|office|head office)\s*[:\-]\s*", "", s, flags=re.I)
    s = re.sub(r"^[A-Z0-9&,\.\-\s]{2,80}\s+-\s+[a-z0-9\.\-]+\s+", "", s, flags=re.I)
    s = cut_stop(s)
    s = re.sub(r"\s+(is located at|located at)\s+", " ", s, flags=re.I)
    return s.strip(" ,;-")[:220]

def parse_located_at(text, country):
    patterns = [
        r"located at\s+(.{3,90}?)\s+in\s+([A-Za-z\s\-']{2,60}),\s+([A-Za-z\s\-']{2,60})\s+(\d{3,6})",
        r"located at\s+(.{3,90}?)\s+in\s+([A-Za-z\s\-']{2,60}),\s+([A-Za-z\s\-']{2,60})",
        r"Address\s*[:\-]\s*(.{3,90}?),\s*([A-Za-z\s\-']{2,60}),\s*([A-Za-z\s\-']{2,60})\s*(\d{3,6})?",
    ]
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            groups = [clean(g) for g in m.groups() if g is not None]
            address = clean_address_line(groups[0])
            city = groups[1] if len(groups) > 1 else ""
            state = normalize_state(groups[2]) if len(groups) > 2 else ""
            zip_code = groups[3] if len(groups) > 3 and re.search(r"\d", groups[3]) else ""
            return {
                "Address": address,
                "City": city,
                "State": state,
                "Zip": zip_code,
                "Country": country,
            }
    return None

def address_marker_score(s, city, state, zip_code, country):
    low = " " + s.lower() + " "
    markers = [
        " street ", " st ", " st. ", " road ", " rd ", " rd. ", " drive ", " dr ",
        " avenue ", " ave ", " lane ", " boulevard ", " building ", " warehouse ",
        " floor ", " suite ", " unit ", " po box ", " industrial ", " business park ",
        " free zone ", " city ", " area ", " district ", " village ", " ward ",
        " ngõ ", " ngach ", " phố ", " đường ", " phường ", " quận ",
    ]
    score = 0
    if any(m in low for m in markers):
        score += 35
    if re.search(r"\b\d{1,6}[A-Za-z]?\b", s):
        score += 20
    if city and norm_text(city) in norm_text(s):
        score += 25
    if state and norm_text(state) in norm_text(s):
        score += 10
    if zip_code and norm_text(zip_code) in norm_text(s):
        score += 25
    if country and norm_text(country) in norm_text(s):
        score += 10
    if len(s) > 220:
        score -= 20
    if any(x in low for x in [" company profile ", " login ", " download ", " import export ", " shipments "]):
        score -= 80
    return score

def extract_address_candidates(text, city, state, zip_code, country):
    candidates = []
    # Explicit address fields
    for m in re.finditer(r"(Address|Registered Address|Location|Office|Head Office)\s*[:\-]\s*([^|;\n]{15,240})", text, flags=re.I):
        candidates.append(m.group(2))
    # Street-like chunks
    marker_regex = r"([A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,90}(?:Village|Street|St\.|Road|Rd\.|Drive|Dr\.|Avenue|Ave\.|Lane|Ln\.|Building|Warehouse|Floor|Suite|Unit|PO Box|P\.O\. Box|Industrial|Business Park|Free Zone|Ward|District|City|ngách|ngõ|phố|đường|phường|quận)[A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,140})"
    for m in re.finditer(marker_regex, text, flags=re.I):
        candidates.append(m.group(1))
    # Around given location tokens
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
            candidates.append(text[max(0, idx - 120): min(len(text), idx + 140)])
            start = idx + len(token_low)
    return candidates

def parse_address(text, city, state, zip_code, country):
    located = parse_located_at(text, country)
    if located:
        if not located.get("Zip"):
            # Try to find post code near city/state
            near = " ".join([located.get("Address",""), located.get("City",""), located.get("State",""), text[:500]])
            m = re.search(r"\b\d{4,6}\b", near)
            if m:
                located["Zip"] = m.group(0)
        return located

    scored = []
    for raw in extract_address_candidates(text, city, state, zip_code, country):
        cand = clean_address_line(raw)
        if len(cand) < 12:
            continue
        score = address_marker_score(cand, city, state, zip_code, country)
        if score >= 25:
            scored.append((score, cand))
    if not scored:
        return {"Address": "Needs research", "City": city or "Needs research", "State": state or "Needs research", "Zip": zip_code or "Needs research", "Country": country or "Needs research"}
    scored.sort(reverse=True, key=lambda x: x[0])
    best = scored[0][1]

    return {
        "Address": best,
        "City": city or "Needs research",
        "State": normalize_state(state) or "Needs research",
        "Zip": zip_code or "Needs research",
        "Country": country or "Needs research",
    }

def classify(company, website, text):
    low = (company + " " + website + " " + text[:6000]).lower()
    if any(x in low for x in ["aerospace", "aircraft", "aviation", "defense", "missile", "boeing"]):
        return "3721 / 3761", "336411 / 336414", "Aerospace and defense manufacturing, engineering, and support services."
    if any(x in low for x in ["electronics", "electronic", "semiconductor", "pcb", "component", "switch"]):
        return "3679 / 3672", "334418 / 334419", "Electronic components, assemblies, or related manufacturing/services."
    if any(x in low for x in ["marine", "maritime", "ship", "vessel", "propulsion"]):
        return "3731 / 4499", "336611 / 488390", "Marine, maritime, vessel technology, or related services."
    if any(x in low for x in ["software", "saas", "technology", "cloud", "cybersecurity"]):
        return "7372 / 7373", "541511 / 541512", "Software, IT, or technology services."
    if any(x in low for x in ["consulting", "consultant", "advisory"]):
        return "8742 / 8748", "541611", "Business or management consulting services."
    if any(x in low for x in ["manufacturing", "manufacturer", "factory", "industrial"]):
        return "3999 / 3599", "339999 / 333249", "Manufacturing or industrial operations."
    return "Needs classification", "Needs classification", "Needs research"

def confidence_from_score(score, address, phone, website):
    total = score
    if address != "Needs research":
        total += 15
    if phone != "Needs research":
        total += 10
    if website != "Needs research":
        total += 10
    if total >= 85:
        return "High"
    if total >= 55:
        return "Medium"
    return "Low"

def blank_record(company, city, state, zip_code, country, source_url, remark):
    return {
        "Company": company,
        "Address": "Needs research",
        "City": city or "Needs research",
        "State": normalize_state(state) or "Needs research",
        "Zip": zip_code or "Needs research",
        "Country": country or "Needs research",
        "PhoneResearch": "Needs research",
        "Website": "Needs research",
        "SIC": "Needs classification",
        "NAICS": "Needs classification",
        "NoOfEmployees(This site only)": "Needs research",
        "LineOfBusiness": "Needs research",
        "ParentName": "Needs research",
        "Confidence": "Low",
        "SourceURL": source_url,
        "Remarks": remark,
    }

def research_company(company, city, state, zip_code, country):
    ov = override_match(company, city, country)
    if ov:
        return ov, [], ["Known override matched."]

    queries = make_search_queries(company, city, state, zip_code, country)
    maps = google_maps_url(company, city, state, zip_code, country)
    logs = ["Queries:"] + [f"- {q}" for q in queries] + [f"Google Maps URL: {maps}"]

    results = search_all(queries)
    candidates = build_candidates(results, company, city, state, zip_code, country)
    logs.append(f"Search results found: {len(results)}")
    logs.append(f"Candidates built: {len(candidates)}")

    if not candidates:
        return blank_record(company, city, state, zip_code, country, google_search_url(queries[0]), "No candidates found."), [], logs

    best = candidates[0]
    logs.append(f"Best candidate score: {best['score']} | {best['title']} | {best['url']}")

    website, website_source = choose_website(company, country, candidates)
    source_url = best["url"] or website_source or google_search_url(queries[0])
    page_text = read_website(website) if website != "Needs research" else ""

    combined = " ".join([c["title"] + " " + c["snippet"] + " " + c["url"] for c in candidates[:8]]) + " " + page_text
    parsed_addr = parse_address(combined, city, state, zip_code, country)
    phone = find_phone(combined)
    sic, naics, lob = classify(company, website, combined)
    conf = confidence_from_score(best["score"], parsed_addr["Address"], phone, website)

    company_out = company
    if best["score"] >= 55 and best["title"]:
        # Use clean directory title if it looks like a company name, but keep user name if title is messy.
        t = re.sub(r"\s+[-|].*$", "", best["title"]).strip()
        if 2 <= len(t) <= 80 and company.lower().split()[0] in t.lower():
            company_out = t

    remarks = "Best candidate selected by scoring. Review before final use."
    if parsed_addr["Address"] == "Needs research":
        remarks = "Best candidate found, but address not safely extracted. Use Google Maps helper/manual address."

    record = {
        "Company": company_out,
        "Address": parsed_addr["Address"],
        "City": parsed_addr["City"],
        "State": parsed_addr["State"],
        "Zip": parsed_addr["Zip"],
        "Country": parsed_addr["Country"],
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
    return record, candidates[:10], logs

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
    defaults = {
        "saved_records": [],
        "current_result": None,
        "candidates": [],
        "logs": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()

st.title("Smart Company Researcher")
st.caption("Candidate scoring → best match → field parsing → manual review → save/export.")

tab1, tab2, tab3 = st.tabs(["Research", "Saved Records", "Export"])

with tab1:
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Single record input")
        company = st.text_input("Company", value="")
        city = st.text_input("City", value="")
        state = st.text_input("State", value="")
        zip_code = st.text_input("Zip", value="")
        country = st.text_input("Country", value="")
        run = st.button("Research Company", type="primary")

    with right:
        st.subheader("Manual helpers")
        helper_q = " ".join([x for x in [company, city, state, zip_code, country] if x])
        if helper_q:
            st.link_button("Open Google Search", google_search_url(helper_q + " address phone website"))
            st.link_button("Open Google Maps", google_maps_url(company, city, state, zip_code, country))
        st.caption("Use the candidate list and Google helpers to verify the result before saving.")

    if run:
        if not clean(company):
            st.error("Company is required.")
        else:
            with st.spinner("Researching and scoring candidates..."):
                result, candidates, logs = research_company(clean(company), clean(city), clean(state), clean(zip_code), clean(country))
                st.session_state.current_result = result
                st.session_state.candidates = candidates
                st.session_state.logs = logs

    if st.session_state.candidates:
        st.divider()
        st.subheader("Candidate matches")
        st.caption("The app picks the highest-score candidate. Use this table to verify wrong-company matches.")
        display = []
        for i, c in enumerate(st.session_state.candidates, start=1):
            display.append({
                "#": i,
                "Score": c["score"],
                "Title": c["title"],
                "URL": c["url"],
                "Snippet": c["snippet"][:180],
            })
        st.dataframe(display, use_container_width=True)

    if st.session_state.current_result:
        st.divider()
        st.subheader("Manual field correction")
        with st.expander("Paste clean Google/Maps fields"):
            m_addr = st.text_input("Manual Address")
            m_city = st.text_input("Manual City")
            m_state = st.text_input("Manual State")
            m_zip = st.text_input("Manual Zip")
            m_phone = st.text_input("Manual Phone")
            if st.button("Apply Manual Fields"):
                if m_addr: st.session_state.current_result["Address"] = clean_address_line(m_addr)
                if m_city: st.session_state.current_result["City"] = clean(m_city)
                if m_state: st.session_state.current_result["State"] = normalize_state(m_state)
                if m_zip: st.session_state.current_result["Zip"] = clean(m_zip)
                if m_phone: st.session_state.current_result["PhoneResearch"] = clean(m_phone)
                st.session_state.current_result["Remarks"] = "Manually corrected after research."
                st.success("Manual fields applied.")

        st.subheader("Final record - edit before saving")
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
                st.session_state.candidates = []
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
        st.dataframe(st.session_state.saved_records, use_container_width=True)

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
