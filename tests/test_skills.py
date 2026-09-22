from opsswarm.skills.s1_incident_intake.logic import run as s1
from opsswarm.skills.s2_severity_assessment.logic import run as s2
from opsswarm.skills.s4_response_orchestrator.logic import run as s4
from opsswarm.skills.s6_recovery_verification.logic import run as s6

def test_core_flow():
    a={'service':'payment','kind':'error_rate','scenario_id':'C03','observed':{'healthy':True,'error_rate':0.43,'version':'v2.1'}}
    seen=set(); i=s1(a,seen); assert not i['duplicate']; assert s1(a,seen)['duplicate']
    assert s2(i['normalized'])['severity']=='SEV1'
    p=s4(i['normalized'],{'metrics':{'payment':a['observed']}}); assert p['recommended_action']['type']=='rollback'
    assert s6('payment',{'healthy':True,'error_rate':0.0,'success_rate':0.995})['verified']
    assert not s6('payment',{'healthy':True,'error_rate':0.08,'success_rate':0.92})['verified']
