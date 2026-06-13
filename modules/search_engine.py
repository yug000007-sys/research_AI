import html
import re
import requests
from urllib.parse import quote_plus, urlparse, parse_qs, unquote

def clean(value):
    return str(value or "").strip()

def google_search_url(query):
    return "https://www.google.com/search?q=" + quote_plus(query)

def google_maps_url(company, address, city, state, zip_code, country):
    query = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    return "https://www.google.com/maps/search/" + quote_plus(query)

def unwrap_url(url):
    url = html.unescape(clean(url))
    if url.startswith("//"):
        url = "https:" + url
    try:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs and qs["uddg"]:
            return unquote(qs["uddg"][0])
        if "url" in qs and qs["url"]:
            return unquote(qs["url"][0])
    except Exception:
        pass
    return url

def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())

def http_get(url, timeout=4):
    try:
        r = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            allow_redirects=True,
        )
        if r.status_code < 400:
            return r.text or ""
    except Exception:
        return ""
    return ""

def ddg_search(query):
    url = "https://duckduckgo.com/html/?q=" + quote_plus(query)
    text = http_get(url, timeout=4)
    results = []

    links = re.findall(
        r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>',
        text,
        flags=re.S,
    )

    snippets = re.findall(
        r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>',
        text,
        flags=re.S,
    )

    for i, (href, title_html) in enumerate(links[:5]):
        snippet = ""
        if i < len(snippets):
            snippet = snippets[i][0] or snippets[i][1]

        results.append({
            "title": strip_html(title_html),
            "url": unwrap_url(href),
            "snippet": strip_html(snippet),
            "engine": "ddg",
            "query": query,
        })

    return results

def make_queries(company, address, city, state, zip_code, country):
    base = " ".join([x for x in [company, address, city, state, zip_code, country] if x])
    queries = []

    if company and city and country:
        queries.append(f'"{company}" "{city}" "{country}" address phone')

    if company and address and country:
        queries.append(f'"{company}" "{address}" "{country}"')

    queries.append(f"{base} address phone website")

    return list(dict.fromkeys([q for q in queries if q.strip()]))

def search_all(company, address, city, state, zip_code, country):
    queries = make_queries(company, address, city, state, zip_code, country)
    logs = ["Fast search mode enabled."] + [f"Query: {q}" for q in queries]

    results = []
    for query in queries[:2]:
        results.extend(ddg_search(query))

    seen = set()
    final = []
    for item in results:
        key = item.get("url") or item.get("title")
        if key and key not in seen:
            seen.add(key)
            final.append(item)

    logs.append(f"Results found: {len(final)}")
    return final[:10], logs
