import streamlit as st

st.set_page_config(page_title="Research AI", layout="wide")

st.title("Research AI")
st.success("App is loading correctly now.")

company = st.text_input("Company")
address = st.text_input("Address")
city = st.text_input("City")
state = st.text_input("State")
zip_code = st.text_input("Zip")
country = st.text_input("Country")

if st.button("Test"):
    st.write({
        "Company": company,
        "Address": address,
        "City": city,
        "State": state,
        "Zip": zip_code,
        "Country": country,
    })
