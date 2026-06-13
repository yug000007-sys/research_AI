from modules.formatters import clean, norm, unwrap_url, format_website, format_phone, format_state, clean_address, domain
from modules.address_parser import parse_address
from modules.phone_extractor import find_phone

BAD_DOMAINS = ['duckduckgo','google','facebook','linkedin','instagram','youtube','bloomberg','zoominfo','dnb','apollo','rocketreach','signalhire','volza','panjiva','importgenius']
GOOD_SOURCES = ['chamberofcommerce','kompass','yellowpages','opencorporates','masothue','business-directory']

def source_type(url):
    d = domain(url)
    if any(x in d for x in GOOD_SOURCES): return 'Directory'
    if any(x in d for x in BAD_DOMAINS): return 'Weak'
    return 'Website'

def company_score(company,text):
    c = norm(company); t = norm(text)
    if c and c in t: return 45
    toks = [x for x in c.split() if len(x)>1 and x not in ['co','ltd','llc','inc','company','limited','srl','spa']]
    if not toks: return 0
    hits = sum(1 for token in toks if token in t)
    return int(35*(hits/len(toks)))

def score_result(result,company,address,city,state,zip_code,country):
    text = result.get('title','')+' '+result.get('snippet','')+' '+result.get('url','')
    t = norm(text); score = company_score(company,text)
    if address and norm(address) in t: score += 25
    if city and norm(city) in t: score += 20
    if state and norm(state) in t: score += 10
    if zip_code and norm(zip_code) in t: score += 15
    if country and norm(country) in t: score += 20
    st = source_type(result.get('url',''))
    if st == 'Website': score += 10
    elif st == 'Directory': score += 8
    else: score -= 15
    if any(x in t for x in ['login required','download','import shipments','followers']): score -= 25
    return score

def build_candidates(results,company,address,city,state,zip_code,country):
    candidates=[]
    for result in results:
        url = unwrap_url(result.get('url',''))
        text = result.get('title','')+' '+result.get('snippet','')+' '+url
        pa, pc, ps, pz, pco = parse_address(text,'',city,state,zip_code,country)
        phone = find_phone(text,country)
        website = format_website(url) if source_type(url) == 'Website' else 'Needs research'
        score = score_result(result,company,address,city,state,zip_code,country)
        cname = clean(result.get('title',''))
        if ' - ' in cname: cname = cname.split(' - ')[0].strip()
        if ' | ' in cname: cname = cname.split(' | ')[0].strip()
        if not cname: cname = company
        candidates.append({'score':score,'company':cname or company,'address':pa,'city':pc,'state':format_state(ps,pco),'zip':pz,'country':pco,'phone':phone,'website':website,'source_url':url,'source_type':source_type(url),'title':result.get('title',''),'snippet':result.get('snippet',''),'query':result.get('query','')})
    candidates.sort(key=lambda x:x.get('score',0), reverse=True)
    return candidates
