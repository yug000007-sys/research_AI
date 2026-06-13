import html, re, requests
from urllib.parse import quote_plus
from modules.formatters import clean, unwrap_url

def google_search_url(query): return 'https://www.google.com/search?q=' + quote_plus(query)
def google_maps_url(company,address,city,state,zip_code,country):
    q = ' '.join([x for x in [company,address,city,state,zip_code,country] if x])
    return 'https://www.google.com/maps/search/' + quote_plus(q)

def http_get(url, timeout=10):
    try:
        r = requests.get(url, headers={'User-Agent':'Mozilla/5.0','Accept-Language':'en-US,en;q=0.9'}, timeout=timeout, allow_redirects=True)
        if r.status_code < 400: return r.text or ''
    except Exception: return ''
    return ''

def strip_html(text):
    text = re.sub(r'<script.*?</script>',' ',text,flags=re.S|re.I)
    text = re.sub(r'<style.*?</style>',' ',text,flags=re.S|re.I)
    text = re.sub(r'<[^>]+>',' ',text)
    return ' '.join(html.unescape(text).split())

def make_queries(company,address,city,state,zip_code,country):
    full = ' '.join([x for x in [company,address,city,state,zip_code,country] if x])
    qs = [f'"{company}" "{city}" "{country}" address phone', f'"{company}" "{address}" "{country}"', f'{full} official website address phone', f'{full} business directory address phone', f'{company} {country} company profile address phone']
    return list(dict.fromkeys([q for q in qs if q.strip()]))

def jina_search(query):
    text = http_get('https://s.jina.ai/?q=' + quote_plus(query), 12)
    out=[]
    if not text: return out
    urls = re.findall(r'https?://[^\s\)\]\}<>"\']+', text)
    titles = re.findall(r'Title:\s*(.+)', text)
    descs = re.findall(r'Description:\s*(.+)', text)
    seen=set()
    for i,u in enumerate(urls):
        u = unwrap_url(u.rstrip('.,)'))
        if u in seen: continue
        seen.add(u)
        out.append({'title':clean(titles[i]) if i < len(titles) else '', 'url':u, 'snippet':clean(descs[i]) if i < len(descs) else '', 'engine':'jina', 'query':query})
        if len(out)>=10: break
    return out

def ddg_search(query):
    text = http_get('https://duckduckgo.com/html/?q=' + quote_plus(query), 10)
    out=[]
    if not text: return out
    links = re.findall(r'<a rel="nofollow" class="result__a" href="(.*?)">(.*?)</a>', text, flags=re.S)
    snippets = re.findall(r'<a class="result__snippet".*?>(.*?)</a>|<div class="result__snippet".*?>(.*?)</div>', text, flags=re.S)
    for i,(url,title_html) in enumerate(links[:8]):
        sn=''
        if i < len(snippets): sn = snippets[i][0] or snippets[i][1]
        out.append({'title':strip_html(title_html),'url':unwrap_url(url),'snippet':strip_html(sn),'engine':'ddg','query':query})
    return out

def search_all(company,address,city,state,zip_code,country):
    queries = make_queries(company,address,city,state,zip_code,country)
    logs = ['Queries:'] + [f'- {q}' for q in queries]
    results=[]
    for q in queries:
        found = jina_search(q)
        if len(found) < 2: found += ddg_search(q)
        results += found
    seen=set(); dedup=[]
    for item in results:
        key = item.get('url') or (item.get('title','')+item.get('snippet',''))
        if key and key not in seen:
            seen.add(key); dedup.append(item)
    logs.append(f'Raw results: {len(results)}')
    logs.append(f'Deduped results: {len(dedup)}')
    return dedup[:25], logs
