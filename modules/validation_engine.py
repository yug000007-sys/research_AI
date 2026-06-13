import re
from modules.address_parser import parse_address
from modules.phone_extractor import find_phone
from modules.formatters import normalize_record, clean

def parse_manual_blob_into_record(blob,current_record,input_country=''):
    r = dict(current_record)
    country = r.get('Country') if r.get('Country') and r.get('Country') != 'Needs research' else input_country
    address, city, state, zip_code, country = parse_address(blob,'',r.get('City',''),r.get('State',''),r.get('Zip',''),country)
    if address != 'Needs research': r['Address'] = address
    if city != 'Needs research': r['City'] = city
    if state != 'Needs research': r['State'] = state
    if zip_code != 'Needs research': r['Zip'] = zip_code
    if country != 'Needs research': r['Country'] = country
    phone = find_phone(blob,r.get('Country',''))
    if phone != 'Needs research': r['PhoneResearch'] = phone
    m = re.search(r'(https?://[^\s]+|www\.[A-Za-z0-9.-]+\.[A-Za-z]{2,})', blob)
    if m: r['Website'] = clean(m.group(1))
    r['Remarks'] = 'Manual pasted text parsed and normalized.'
    return normalize_record(r)
