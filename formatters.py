import re, html
from urllib.parse import urlparse, parse_qs, unquote

US_STATES = {'alabama':'AL','alaska':'AK','arizona':'AZ','arkansas':'AR','california':'CA','colorado':'CO','connecticut':'CT','delaware':'DE','florida':'FL','georgia':'GA','hawaii':'HI','idaho':'ID','illinois':'IL','indiana':'IN','iowa':'IA','kansas':'KS','kentucky':'KY','louisiana':'LA','maine':'ME','maryland':'MD','massachusetts':'MA','michigan':'MI','minnesota':'MN','mississippi':'MS','missouri':'MO','montana':'MT','nebraska':'NE','nevada':'NV','new hampshire':'NH','new jersey':'NJ','new mexico':'NM','new york':'NY','north carolina':'NC','north dakota':'ND','ohio':'OH','oklahoma':'OK','oregon':'OR','pennsylvania':'PA','rhode island':'RI','south carolina':'SC','south dakota':'SD','tennessee':'TN','texas':'TX','utah':'UT','vermont':'VT','virginia':'VA','washington':'WA','west virginia':'WV','wisconsin':'WI','wyoming':'WY'}
CA_PROV = {'alberta':'AB','british columbia':'BC','manitoba':'MB','new brunswick':'NB','newfoundland and labrador':'NL','nova scotia':'NS','ontario':'ON','prince edward island':'PE','quebec':'QC','québec':'QC','saskatchewan':'SK','northwest territories':'NT','nunavut':'NU','yukon':'YT'}
AU_STATES = {'new south wales':'NSW','nsw':'NSW','queensland':'QLD','qld':'QLD','victoria':'VIC','vic':'VIC','south australia':'SA','western australia':'WA','tasmania':'TAS','northern territory':'NT','australian capital territory':'ACT'}
DIAL = {'usa':'+1','united states':'+1','united states of america':'+1','canada':'+1','italy':'+39','australia':'+61','japan':'+81','vietnam':'+84','viet nam':'+84','uae':'+971','united arab emirates':'+971','germany':'+49','france':'+33','uk':'+44','united kingdom':'+44','china':'+86','india':'+91','spain':'+34','netherlands':'+31','singapore':'+65','south korea':'+82','mexico':'+52','brazil':'+55'}

def clean(v): return str(v or '').strip()
def norm(v): return re.sub(r'[^a-z0-9]+',' ',clean(v).lower()).strip()
def digits(v): return re.sub(r'\D+','',clean(v))

def unwrap_url(url):
    url = html.unescape(clean(url))
    if url.startswith('//'): url = 'https:' + url
    try:
        qs = parse_qs(urlparse(url).query)
        if qs.get('uddg'): return unquote(qs['uddg'][0])
        if qs.get('url'): return unquote(qs['url'][0])
    except Exception: pass
    return url

def domain(url):
    try: return urlparse(unwrap_url(url)).netloc.lower().replace('www.','')
    except Exception: return ''

def format_website(url):
    url = unwrap_url(clean(url))
    if not url or url == 'Needs research': return 'Needs research'
    if not url.startswith(('http://','https://')): url = 'https://' + url
    d = domain(url)
    if not d or 'duckduckgo' in d or 'google' in d: return 'Needs research'
    return 'www.' + d

def format_country(country):
    n = norm(country); c = clean(country)
    if n in ['united states','united states of america','usa','us']: return 'USA'
    if n == 'viet nam': return 'Vietnam'
    return c or 'Needs research'

def format_state(state, country):
    state = clean(state)
    if not state or state == 'Needs research': return state or 'Needs research'
    c = norm(country); up = state.upper().replace('.','')
    if c in ['usa','united states','united states of america']:
        return up if up in US_STATES.values() else US_STATES.get(state.lower(), state)
    if c == 'canada': return up if up in CA_PROV.values() else CA_PROV.get(state.lower(), state)
    if c == 'australia': return AU_STATES.get(state.lower(), state)
    return state

def format_phone(phone, country):
    phone = clean(phone)
    if not phone or phone == 'Needs research': return 'Needs research'
    c = norm(country); d = digits(phone)
    if c in ['usa','united states','united states of america','canada']:
        if len(d) == 11 and d.startswith('1'): d = d[1:]
        if len(d) >= 10:
            d = d[-10:]
            return f'{d[:3]}-{d[3:6]}-{d[6:10]}'
        return phone
    code = DIAL.get(c,'')
    if phone.startswith('+'): return re.sub(r'\s+',' ',phone)
    if code:
        local = d; cd = digits(code)
        if local.startswith(cd): return '+' + local[:len(cd)] + ' ' + local[len(cd):]
        if local.startswith('0'): local = local[1:]
        return code + ' ' + local if local else phone
    return phone

def clean_address(address):
    address = html.unescape(clean(address))
    if not address or address == 'Needs research': return 'Needs research'
    address = re.sub(r'\s+',' ',address)
    address = re.sub(r'^[A-Z0-9&.,\-\s]{2,100}\s+-\s+[a-z0-9.\-]+\s+','',address,flags=re.I)
    address = re.split(r'\bPhone\b|\bTel\b|\bEmail\b|\bWebsite\b|\bState\s*:|\bZipcode\s*:|\bTown\s*:|\bCountry\s*:',address,flags=re.I)[0]
    address = address.strip(' ,;-')
    return address[:160] if address else 'Needs research'

def normalize_record(record):
    r = dict(record)
    r['Country'] = format_country(r.get('Country',''))
    r['State'] = format_state(r.get('State',''), r.get('Country',''))
    r['PhoneResearch'] = format_phone(r.get('PhoneResearch',''), r.get('Country',''))
    r['Website'] = format_website(r.get('Website',''))
    r['Address'] = clean_address(r.get('Address',''))
    return r
