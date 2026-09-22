def run(i,severity,service):
    return {'technical':f'{i} {severity}: {service} under investigation','operations':f'{i}: evidence collected; awaiting approved recovery','executive':f'{i}: business-impacting incident; controlled response active'}
