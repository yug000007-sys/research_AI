# Smart Company Researcher

A single-record company enrichment app for Streamlit Cloud.

## What this version does

- Researches one company at a time
- Uses multiple search queries
- Builds candidate company matches
- Scores candidates by:
  - company match
  - city/country match
  - zip/state match
  - source/domain quality
- Selects best candidate
- Extracts:
  - Address
  - City
  - State
  - Zip
  - Country
  - Phone
  - Website
  - SIC/NAICS estimate
  - Line of business
- Shows candidate table for review
- Supports manual correction
- Saves records
- Exports CSV or Excel-openable XLS

## Deploy on Streamlit Cloud

Upload only these files to the GitHub repo root:

- app.py
- requirements.txt
- README.md

Main file path:

app.py

## Important

This is a free-source enrichment helper, not a guaranteed database. Always review candidate matches before saving.
