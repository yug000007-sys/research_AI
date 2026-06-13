import streamlit as st
from modules.search_engine import google_search_url, google_maps_url, search_all
from modules.candidate_builder import build_candidates
from modules.candidate_parser import candidate_to_record
from modules.formatters import normalize_record
from modules.manual_parser import parse_manual_blob_into_record
from modules.validation_engine import validate_record
from modules.export_engine import export_csv, export_xls, FIELDS

st.set_page_config(page_title='Company Research Workstation', layout='wide')

for key, default in {'saved_records': [], 'current_record': None, 'candidates': [], 'logs': []}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title('Company Research Workstation v3')
st.caption('Find candidates -> choose correct row -> normalize -> validate -> save/export')

tab_research, tab_saved, tab_export = st.tabs(['Research','Saved Records','Export'])

with tab_research:
    left, right = st.columns([1,1])
    with left:
        st.subheader('Input')
        company = st.text_input('Company')
        address = st.text_input('Address')
        city = st.text_input('City')
        state = st.text_input('State')
        zip_code = st.text_input('Zip')
        country = st.text_input('Country')
        run = st.button('Find Candidates', type='primary')
    with right:
        st.subheader('Research helpers')
        q = ' '.join([x for x in [company,address,city,state,zip_code,country] if x])
        if q:
            st.link_button('Open Google Search', google_search_url(q + ' address phone website'))
            st.link_button('Open Google Maps', google_maps_url(company,address,city,state,zip_code,country))
        st.info('Use the candidate table. Click Use to overwrite final fields.')

    if run:
        if not company.strip():
            st.error('Company is required.')
        else:
            with st.spinner('Searching and building candidates...'):
                results, logs = search_all(company,address,city,state,zip_code,country)
                candidates = build_candidates(results,company,address,city,state,zip_code,country)
                st.session_state.candidates = candidates[:10]
                st.session_state.logs = logs
                if st.session_state.candidates:
                    st.session_state.current_record = candidate_to_record(st.session_state.candidates[0], st.session_state.candidates, company, address, city, state, zip_code, country)
                    st.session_state.current_record = normalize_record(st.session_state.current_record)
                else:
                    st.session_state.current_record = None

    if st.session_state.candidates:
        st.divider(); st.subheader('Candidate Finder')
        st.caption('Choose the row that matches your intended company/location.')
        header = st.columns([0.45,0.75,2,2,1.2,1,0.8,1,1.3,1.4,0.9])
        labels = ['#','Score','Company','Address','City','State','Zip','Country','Phone','Website','Action']
        for col,label in zip(header,labels): col.markdown(f'**{label}**')
        for idx,cand in enumerate(st.session_state.candidates):
            cols = st.columns([0.45,0.75,2,2,1.2,1,0.8,1,1.3,1.4,0.9])
            cols[0].write(idx+1); cols[1].write(cand.get('score',0)); cols[2].write(cand.get('company','')[:60]); cols[3].write(cand.get('address','')[:70]); cols[4].write(cand.get('city','')); cols[5].write(cand.get('state','')); cols[6].write(cand.get('zip','')); cols[7].write(cand.get('country','')); cols[8].write(cand.get('phone','')); cols[9].write(cand.get('website',''))
            if cols[10].button('Use', key=f'use_candidate_{idx}'):
                st.session_state.current_record = candidate_to_record(cand, st.session_state.candidates, company, address, city, state, zip_code, country)
                st.session_state.current_record = normalize_record(st.session_state.current_record)
                st.success(f'Candidate {idx+1} applied.')
        with st.expander('Candidate details / sources'):
            for i,cand in enumerate(st.session_state.candidates, start=1):
                st.markdown(f"**Candidate {i} - Score {cand.get('score',0)}**")
                st.write('Title:', cand.get('title',''))
                st.write('Source type:', cand.get('source_type',''))
                st.write('URL:', cand.get('source_url',''))
                st.write('Snippet:', cand.get('snippet',''))
                st.divider()

    st.divider(); st.subheader('Manual Paste Parser')
    paste = st.text_area('Paste Google/Maps/directory text here')
    if st.button('Parse Paste Into Final Fields'):
        if not st.session_state.current_record:
            st.session_state.current_record = {field:'' for field in FIELDS}
            st.session_state.current_record['Company'] = company
            st.session_state.current_record['Country'] = country
        st.session_state.current_record = parse_manual_blob_into_record(paste, st.session_state.current_record, input_country=country)
        st.session_state.current_record = normalize_record(st.session_state.current_record)
        st.success('Pasted text parsed and normalized.')

    if st.session_state.current_record:
        st.divider(); st.subheader('Final Record')
        validation = validate_record(st.session_state.current_record)
        if validation['status'] == 'PASS': st.success('Quality Gate: PASS')
        elif validation['status'] == 'WARN': st.warning('Quality Gate: WARNING - ' + '; '.join(validation['issues']))
        else: st.error('Quality Gate: FAIL - ' + '; '.join(validation['issues']))
        edited = {}
        for field in FIELDS:
            value = str(st.session_state.current_record.get(field,'') or '')
            edited[field] = st.text_area(field, value=value, height=75) if field in ['Address','LineOfBusiness','Remarks'] else st.text_input(field, value=value)
        c1,c2,c3,c4 = st.columns(4)
        if c1.button('Normalize'):
            st.session_state.current_record = normalize_record(edited.copy()); st.rerun()
        if c2.button('Save'):
            record = normalize_record(edited.copy()); val = validate_record(record)
            if val['status'] == 'FAIL': st.error('Cannot save. Fix failed fields or use Save Anyway.')
            else:
                st.session_state.saved_records.append(record); st.success('Saved.')
        if c3.button('Save Anyway'):
            st.session_state.saved_records.append(normalize_record(edited.copy())); st.warning('Saved despite quality warnings.')
        if c4.button('Clear'):
            st.session_state.current_record = None; st.session_state.candidates = []; st.session_state.logs = []; st.rerun()
        with st.expander('Search logs'):
            st.write('\n'.join(st.session_state.logs))

with tab_saved:
    st.subheader('Saved Records')
    if not st.session_state.saved_records: st.info('No saved records yet.')
    else:
        st.dataframe(st.session_state.saved_records, use_container_width=True)
        delete_index = st.number_input('Delete record number', min_value=1, max_value=len(st.session_state.saved_records), value=1)
        if st.button('Delete Selected'):
            st.session_state.saved_records.pop(delete_index-1); st.rerun()
        if st.button('Clear All Saved'):
            st.session_state.saved_records = []; st.rerun()

with tab_export:
    st.subheader('Export')
    if not st.session_state.saved_records: st.info('No saved records yet.')
    else:
        st.download_button('Download CSV', export_csv(st.session_state.saved_records), 'company_records.csv', 'text/csv')
        st.download_button('Download Excel-openable XLS', export_xls(st.session_state.saved_records), 'company_records.xls', 'application/vnd.ms-excel')
