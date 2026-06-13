import re
from modules.formatters import clean, norm, clean_address, format_state

def parse_blob(text, country):
    text = clean(text)
    town = re.search(r'Town\s*:\s*([^:]+?)(?:Country|State|Zip|$)', text, re.I)
    state = re.search(r'State\s*:\s*([^:]+?)(?:Zip|Town|Country|$)', text, re.I)
    zip_code = re.search(r'Zip(?:code)?\s*:\s*([A-Z0-9\-\s]{3,12})', text, re.I)
    ctry = re.search(r'Country\s*:\s*([^:]+?)(?:State|Zip|Town|$)', text, re.I)
    city = clean(town.group(1).replace(',','')) if town else ''
    st = clean(state.group(1)) if state else ''
    z = clean(zip_code.group(1)) if zip_code else ''
    c = clean(ctry.group(1)) if ctry else country
    before = re.split(r'\bState\s*:|\bZipcode\s*:|\bTown\s*:|\bCountry\s*:', text, flags=re.I)[0]
    m = re.search(r'(.+?)\s+([A-Za-z .\'-]+),?\s+([A-Z]{2}|[A-Za-z ]+)\s+([A-Z0-9][A-Z0-9 -]{2,12})', before)
    if m:
        return clean_address(m.group(1)), city or clean(m.group(2)), format_state(st or clean(m.group(3)), c), z or clean(m.group(4)), c
    return clean_address(before), city, format_state(st,c), z, c

def parse_located_at(text,country):
    patterns = [r'located at\s+(.{3,90}?)\s+in\s+([A-Za-z .\'-]+),\s+([A-Za-z .\'-]+)\s+(\d{3,10})', r'located at\s+(.{3,90}?)\s+in\s+([A-Za-z .\'-]+),\s+([A-Za-z .\'-]+)', r'Address\s*[:\-]\s*(.{3,90}?),\s*([A-Za-z .\'-]+),\s*([A-Za-z .\'-]+)\s*(\d{3,10})?']
    for p in patterns:
        m = re.search(p, text, flags=re.I)
        if m:
            g = [clean(x) for x in m.groups() if x]
            return clean_address(g[0]) if len(g)>0 else 'Needs research', g[1] if len(g)>1 else 'Needs research', format_state(g[2], country) if len(g)>2 else 'Needs research', g[3] if len(g)>3 else 'Needs research', country
    return None

def extract_candidates(text):
    cands=[]
    for m in re.finditer(r'(Address|Registered Address|Location|Office|Head Office)\s*[:\-]\s*([^|;\n]{15,240})', text, flags=re.I): cands.append(m.group(2))
    marker_regex = r'([A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,90}(?:Village|Street|St\.|Road|Rd\.|Drive|Dr\.|Avenue|Ave\.|Lane|Ln\.|Boulevard|Blvd\.|Building|Warehouse|Floor|Suite|Unit|PO Box|P\.O\. Box|Industrial|Business Park|Free Zone|Ward|District|City|Via|Viale|Piazza|Corso|Strada|ngách|ngõ|phố|đường|phường|quận)[A-Za-zÀ-ỹ0-9#,&\.\-/\s]{0,140})'
    for m in re.finditer(marker_regex, text, flags=re.I): cands.append(m.group(1))
    return cands

def score_address(address,city,state,zip_code,country):
    low = ' ' + address.lower() + ' '
    markers = [' street ',' st ',' st. ',' road ',' rd ',' rd. ',' drive ',' dr ',' avenue ',' ave ',' lane ',' boulevard ',' building ',' suite ',' unit ',' po box ',' industrial ',' business park ',' village ',' ward ',' district ',' via ',' viale ',' piazza ',' corso ',' strada ',' ngõ ',' phố ',' đường ']
    score = 35 if any(m in low for m in markers) else 0
    if re.search(r'\b\d{1,6}[A-Za-z]?\b', address): score += 20
    if city and norm(city) in norm(address): score += 25
    if state and norm(state) in norm(address): score += 10
    if zip_code and norm(zip_code) in norm(address): score += 25
    if country and norm(country) in norm(address): score += 10
    if any(x in low for x in [' company profile ',' login ',' download ',' import export ',' shipments ']): score -= 80
    if len(address) > 220: score -= 20
    return score

def parse_address(text,input_address,city,state,zip_code,country):
    if input_address:
        return clean_address(input_address), city or 'Needs research', format_state(state,country) or 'Needs research', zip_code or 'Needs research', country or 'Needs research'
    text = clean(text)
    if any(x in text.lower() for x in ['state :','zipcode :','town :','country :']): return parse_blob(text,country)
    located = parse_located_at(text,country)
    if located: return located
    scored=[]
    for raw in extract_candidates(text):
        cand = clean_address(raw)
        if len(cand) < 12: continue
        score = score_address(cand,city,state,zip_code,country)
        if score >= 25: scored.append((score,cand))
    if scored:
        scored.sort(reverse=True, key=lambda x:x[0])
        return scored[0][1], city or 'Needs research', format_state(state,country) or 'Needs research', zip_code or 'Needs research', country or 'Needs research'
    return 'Needs research', city or 'Needs research', format_state(state,country) or 'Needs research', zip_code or 'Needs research', country or 'Needs research'
