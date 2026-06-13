from urllib.parse import urljoin
from modules.search_engine import http_get, strip_html
from modules.formatters import format_website, normalize_record
from modules.address_parser import parse_address
from modules.phone_extractor import find_phone
from modules.classifier import classify_business

def read_website(website):
    if not website or website == 'Needs research': return ''
    base = 'https://' + website if not website.startswith('http') else website
    chunks=[]
    for page in [base, urljoin(base,'/contact'), urljoin(base,'/contact-us'), urljoin(base,'/about'), urljoin(base,'/locations')]:
        text = strip_html(http_get(page, timeout=8))
        if text: chunks.append(text)
        if len(' '.join(chunks)) > 30000: break
    return ' '.join(chunks)[:35000]

def choose_website(company,candidates):
    for c in candidates:
        w = c.get('website','')
        if w and w != 'Needs research': return w
    for c in candidates:
        if c.get('source_type') == 'Website': return format_website(c.get('source_url',''))
    return 'Needs research'

def candidate_to_record(candidate,candidates,input_company,input_address,input_city,input_state,input_zip,input_country):
    website = choose_website(input_company,candidates)
    website_text = read_website(website)
    combined = ' '.join([candidate.get('title',''), candidate.get('snippet',''), candidate.get('source_url',''), website_text])
    address, city, state, zip_code, country = parse_address(combined, input_address or (candidate.get('address') if candidate.get('address') != 'Needs research' else ''), input_city or candidate.get('city',''), input_state or candidate.get('state',''), input_zip or candidate.get('zip',''), input_country or candidate.get('country',''))
    phone = find_phone(combined,country)
    if phone == 'Needs research': phone = candidate.get('phone','Needs research')
    sic, naics, lob = classify_business(input_company, website, combined)
    confidence = 'High' if candidate.get('score',0) >= 85 and address != 'Needs research' else 'Medium' if candidate.get('score',0) >= 55 else 'Low'
    return normalize_record({'Company':input_company or candidate.get('company',''),'Address':address,'City':city,'State':state,'Zip':zip_code,'Country':country,'PhoneResearch':phone,'Website':website,'SIC':sic,'NAICS':naics,'NoOfEmployees(This site only)':'Not publicly disclosed','LineOfBusiness':lob,'ParentName':'Needs research','Confidence':confidence,'SourceURL':candidate.get('source_url',''),'Remarks':'Candidate selected and normalized. Review before saving.'})
