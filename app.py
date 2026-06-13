import csv
import html
import io
import streamlit as st

st.set_page_config(page_title="Company Enrichment Tool", layout="wide")

st.title("Company Enrichment Tool")
st.success("App loaded successfully.")
st.write("Fastest Streamlit Cloud version: no pandas, no openpyxl, no heavy packages.")

INPUT_COLUMNS = ["Company", "City", "State", "Zip", "Country"]

OUTPUT_COLUMNS = [
    "Company",
    "Address",
    "City",
    "State",
    "Zip",
    "Country",
    "PhoneResearch",
    "Website",
    "SIC",
    "NAICS",
    "NoOfEmployees(This site only)",
    "LineOfBusiness",
    "ParentName",
    "Confidence",
    "SourceURL",
    "Remarks",
]

def clean(value):
    return str(value or "").strip()

def normalize_key(key):
    return str(key or "").strip().lower().replace(" ", "").replace("_", "")

def get_value(row, target):
    aliases = {
        "Company": ["company", "companyname", "name"],
        "City": ["city", "town"],
        "State": ["state", "province", "region"],
        "Zip": ["zip", "zipcode", "postal", "postalcode", "postcode"],
        "Country": ["country", "nation"],
    }
    wanted = aliases.get(target, [target.lower()])
    for k, v in row.items():
        if normalize_key(k) in wanted:
            return clean(v)
    return ""

def create_output_row(row):
    company = get_value(row, "Company")
    city = get_value(row, "City")
    state = get_value(row, "State")
    zip_code = get_value(row, "Zip")
    country = get_value(row, "Country")

    query_parts = [company, city, state, zip_code, country, "official address phone website"]
    search_query = "+".join([p.replace(" ", "+") for p in query_parts if p])

    return {
        "Company": company,
        "Address": "Needs research",
        "City": city or "Needs research",
        "State": state or "Needs research",
        "Zip": zip_code or "Needs research",
        "Country": country or "Needs research",
        "PhoneResearch": "Needs research",
        "Website": "Needs research",
        "SIC": "Needs classification",
        "NAICS": "Needs classification",
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": "Needs research",
        "ParentName": "Needs research",
        "Confidence": "Low",
        "SourceURL": "https://www.google.com/search?q=" + search_query,
        "Remarks": "Fast stable version. Auto-research will be added after deployment is confirmed working.",
    }

def rows_to_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=OUTPUT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")

def rows_to_excel_html(rows):
    # Excel can open this .xls HTML table without openpyxl.
    table = ['<html><head><meta charset="utf-8"></head><body><table border="1">']
    table.append("<tr>" + "".join(f"<th>{html.escape(c)}</th>" for c in OUTPUT_COLUMNS) + "</tr>")
    for row in rows:
        table.append("<tr>" + "".join(f"<td>{html.escape(clean(row.get(c, '')))}</td>" for c in OUTPUT_COLUMNS) + "</tr>")
    table.append("</table></body></html>")
    return "\n".join(table).encode("utf-8")

sample_csv = "Company,City,State,Zip,Country\nBoeing,Tanner,AL,35671,USA\nBOEL,Osaka-Shi,,,Japan\n"

uploaded = st.file_uploader("Upload CSV file only", type=["csv"])

if uploaded is None:
    st.subheader("Sample CSV format")
    st.code(sample_csv)
    st.download_button(
        "Download sample CSV",
        data=sample_csv.encode("utf-8"),
        file_name="sample_input.csv",
        mime="text/csv",
    )
else:
    try:
        content = uploaded.read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(content))
        input_rows = list(reader)

        if not input_rows:
            st.error("CSV is empty or headers are missing.")
            st.stop()

        st.write(f"Rows loaded: {len(input_rows)}")

        rows_to_process = st.number_input(
            "Rows to process",
            min_value=1,
            max_value=len(input_rows),
            value=min(len(input_rows), 100),
            step=1,
        )

        preview = input_rows[:10]
        st.subheader("Input preview")
        st.table(preview)

        if st.button("Generate output"):
            output_rows = [create_output_row(r) for r in input_rows[:rows_to_process]]

            st.subheader("Output preview")
            st.table(output_rows[:10])

            st.download_button(
                "Download CSV",
                data=rows_to_csv(output_rows),
                file_name="company_enrichment_output.csv",
                mime="text/csv",
            )

            st.download_button(
                "Download Excel-openable XLS",
                data=rows_to_excel_html(output_rows),
                file_name="company_enrichment_output.xls",
                mime="application/vnd.ms-excel",
            )

    except Exception as e:
        st.error("Error processing CSV")
        st.exception(e)

st.info("This version is designed to prove deployment works. It avoids pandas/openpyxl to prevent Streamlit Cloud build delays.")
