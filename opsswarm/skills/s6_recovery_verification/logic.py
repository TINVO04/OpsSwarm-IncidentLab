def run(service,m):
    if 'error_rate' not in m or 'success_rate' not in m: return {'verified':False,'reason':'required telemetry missing'}
    ok=(m.get('healthy') is True and m['error_rate']<=0.01 and m['success_rate']>=0.98)
    return {'verified':ok,'reason':'thresholds satisfied' if ok else f"not verified: {m}"}
