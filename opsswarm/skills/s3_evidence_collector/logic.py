def run(metrics):
    a=[]
    for s,m in metrics.items():
        if m.get('healthy') is False: a.append(f'{s}:unhealthy')
        if m.get('error_rate',0) and m.get('error_rate',0)>=0.03: a.append(f"{s}:error_rate={m.get('error_rate')}")
        if m.get('latency_ms',0)>=1000: a.append(f"{s}:latency={m.get('latency_ms')}ms")
        if m.get('cpu_percent',0)>=90: a.append(f"{s}:cpu={m.get('cpu_percent')}%")
        if m.get('memory_percent',0)>=90: a.append(f"{s}:memory={m.get('memory_percent')}%")
        if 'error_rate' not in m: a.append(f'{s}:telemetry_missing')
    return {'metrics':metrics,'anomalies':a}
