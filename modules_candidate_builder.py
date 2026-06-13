def classify_business(company,website,text):
    low = (str(company)+' '+str(website)+' '+str(text[:6000])).lower()
    if any(x in low for x in ['aerospace','aircraft','aviation','defense','missile','boeing']): return '3721 / 3761','336411 / 336414','Aerospace and defense services.'
    if any(x in low for x in ['electronics','electronic','component','switch','pcb','semiconductor']): return '3679 / 3672','334418 / 334419','Electronic components/services.'
    if any(x in low for x in ['heating','thermal','chromalox','heater']): return '3567','333414','Industrial heating, thermal systems, and related services.'
    if any(x in low for x in ['marine','maritime','ship','vessel','propulsion']): return '3731 / 4499','336611 / 488390','Marine, maritime, vessel technology, or related services.'
    if any(x in low for x in ['software','saas','technology','cloud','cybersecurity']): return '7372 / 7373','541511 / 541512','Software/IT services.'
    if any(x in low for x in ['consulting','consultant','advisory']): return '8742 / 8748','541611','Business or management consulting services.'
    if any(x in low for x in ['manufacturing','manufacturer','factory','industrial']): return '3999 / 3599','339999 / 333249','Manufacturing or industrial operations.'
    return 'Needs classification','Needs classification','Needs research'
