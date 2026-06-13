import csv, html, io
from modules.formatters import normalize_record, clean

FIELDS = ['Company','Address','City','State','Zip','Country','PhoneResearch','Website','SIC','NAICS','NoOfEmployees(This site only)','LineOfBusiness','ParentName','Confidence','SourceURL','Remarks']

def export_csv(rows):
    normalized = [normalize_record(dict(row)) for row in rows]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader(); writer.writerows(normalized)
    return output.getvalue().encode('utf-8')

def export_xls(rows):
    normalized = [normalize_record(dict(row)) for row in rows]
    table = ['<html><head><meta charset="utf-8"></head><body><table border="1">']
    table.append('<tr>' + ''.join(f'<th>{html.escape(f)}</th>' for f in FIELDS) + '</tr>')
    for row in normalized:
        table.append('<tr>' + ''.join(f'<td>{html.escape(clean(row.get(f, "")))}</td>' for f in FIELDS) + '</tr>')
    table.append('</table></body></html>')
    return '\n'.join(table).encode('utf-8')
