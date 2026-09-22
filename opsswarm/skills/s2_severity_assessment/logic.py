def run(n):
    o=n.get('observed',{}); e=o.get('error_rate'); h=o.get('healthy',True)
    if n.get('service')=='payment' and e is not None and e>=0.30: return {'severity':'SEV1','rationale':'payment error rate >=30%'}
    if h is False: return {'severity':'SEV1','rationale':'service unhealthy'}
    if e is not None and e>=0.10: return {'severity':'SEV2','rationale':'error rate >=10%'}
    return {'severity':'SEV3','rationale':'minor/unknown degradation'}
