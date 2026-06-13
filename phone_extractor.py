import re
from modules.formatters import clean, digits, format_phone

def find_phone(text,country):
    patterns = [r'\+\d{1,3}[\s\-.]?\(?\d{1,5}\)?[\s\-.]?\d{2,5}[\s\-.]?\d{2,5}[\s\-.]?\d{2,6}', r'\(?\d{3}\)?[\s\-.]\d{3}[\s\-.]\d{4}', r'\d{2,5}[\s\-.]\d{2,5}[\s\-.]\d{3,5}']
    for p in patterns:
        m = re.search(p,text)
        if m:
            phone = clean(m.group(0))
            if len(digits(phone)) >= 7: return format_phone(phone,country)
    return 'Needs research'
