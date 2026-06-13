from modules.formatters import normalize_record
from modules.address_parser import parse_address
from modules.phone_extractor import find_phone
from modules.classifier import classify_business


def candidate_to_record(
    candidate,
    candidates,
    input_company,
    input_address,
    input_city,
    input_state,
    input_zip,
    input_country,
):
    """
    Convert selected candidate into final record.
    No website crawling.
    No external page reading.
    Fast and stable.
    """

    company = input_company or candidate.get("company", "Needs research")

    address = candidate.get("address", "Needs research")
    city = candidate.get("city", "Needs research")
    state = candidate.get("state", "Needs research")
    zip_code = candidate.get("zip", "Needs research")
    country = candidate.get("country", input_country or "Needs research")

    if input_address:
        address = input_address

    if input_city:
        city = input_city

    if input_state:
        state = input_state

    if input_zip:
        zip_code = input_zip

    if input_country:
        country = input_country

    address, city, state, zip_code, country = parse_address(
        address,
        address,
        city,
        state,
        zip_code,
        country,
    )

    phone = candidate.get("phone", "Needs research")

    if phone == "Needs research":
        combined_text = (
            str(candidate.get("title", ""))
            + " "
            + str(candidate.get("snippet", ""))
        )

        phone = find_phone(combined_text, country)

    website = candidate.get("website", "Needs research")

    sic, naics, lob = classify_business(
        company,
        website,
        candidate.get("snippet", ""),
    )

    score = candidate.get("score", 0)

    if score >= 85:
        confidence = "High"
    elif score >= 55:
        confidence = "Medium"
    else:
        confidence = "Low"

    record = {
        "Company": company,
        "Address": address,
        "City": city,
        "State": state,
        "Zip": zip_code,
        "Country": country,
        "PhoneResearch": phone,
        "Website": website,
        "SIC": sic,
        "NAICS": naics,
        "NoOfEmployees(This site only)": "Not publicly disclosed",
        "LineOfBusiness": lob,
        "ParentName": "Needs research",
        "Confidence": confidence,
        "SourceURL": candidate.get("source_url", ""),
        "Remarks": "Candidate selected. Review before saving.",
    }

    return normalize_record(record)
