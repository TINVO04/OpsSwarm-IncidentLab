def run(n,e):
    s=n.get('service'); c=n.get('scenario_id'); m=e.get('metrics',{}).get(s,{})
    if c=='C03' or (s=='payment' and m.get('version')=='v2.1'):
        action={'type':'rollback','service':'payment','target_version':'v2.0'}; reason='bad/recent payment deployment'
    elif c=='C12':
        action={'type':'partial_recovery','service':s}; reason='intentional false-recovery test'
    else:
        action={'type':'reset_faults','service':s}; reason='reset injected sandbox fault'
    return {'steps':['freeze changes','notify owner','collect evidence','request approval','execute recovery','verify recovery'],'recommended_action':action,'reason':reason,'approval_required':True}
