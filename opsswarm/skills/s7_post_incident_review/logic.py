def run(i):
    return {'incident_id':i['id'],'service':i['service'],'severity':i['severity'],'status':i['status'],'timeline':i.get('timeline',[]),'evidence_summary':i.get('evidence',{}).get('anomalies',[]),'recovery':i.get('recovery'),'follow_up_actions':['review trigger','validate thresholds','review approval evidence','add regression test']}
