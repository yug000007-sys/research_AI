import re
from modules.formatters import norm

def validate_record(record):
    issues=[]; fail=[]
    address = str(record.get('Address','') or '')
    website = str(record.get('Website','') or '')
    phone = str(record.get('PhoneResearch','') or '')
    state = str(record.get('State','') or '')
    country = str(record.get('Country','') or '')
    if any(term in address.lower() for term in ['http','www','duckduckgo','google','state :','zipcode :','town :','country :','login','download']): fail.append('Address contains raw snippet/URL text')
    if not address or address == 'Needs research': issues.append('Address missing')
    if website != 'Needs research' and not website.startswith('www.'): fail.append('Website must be formatted as www.domain.com')
    c = norm(country)
    if c in ['usa','united states','canada'] and phone != 'Needs research' and not re.match(r'^\d{3}-\d{3}-\d{4}$',phone): fail.append('USA/Canada phone must be xxx-xxx-xxxx')
    if c in ['usa','united states','united states of america','canada'] and state and state != 'Needs research' and not re.match(r'^[A-Z]{2}$',state): fail.append('USA/Canada state/province must be abbreviation')
    if phone == 'Needs research': issues.append('Phone missing')
    if website == 'Needs research': issues.append('Website missing')
    if fail: return {'status':'FAIL','issues':fail+issues}
    if issues: return {'status':'WARN','issues':issues}
    return {'status':'PASS','issues':[]}
