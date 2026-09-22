import hashlib

def run(alert, seen):
    canonical=f"{alert.get('service')}|{alert.get('kind')}|{alert.get('scenario_id','')}"
    fp=hashlib.sha256(canonical.encode()).hexdigest()[:16]
    dup=fp in seen
    if not dup: seen.add(fp)
    return {'fingerprint':fp,'duplicate':dup,'normalized':alert}
