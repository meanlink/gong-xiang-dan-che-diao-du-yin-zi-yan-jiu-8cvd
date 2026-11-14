import hashlib, json
def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()
def dataset_dict(d):
    return {'id':d.id, 'name':d.name, 'source':d.source, 'rows':len(d.records), 'checksum':d.checksum, 'created_at':d.created_at}
def job_dict(j):
    return {k:getattr(j,k) for k in ['id','name','dataset_id','params','status','result','error','approved','created_at','finished_at']}
def report_dict(r):
    return {k:getattr(r,k) for k in ['id','name','job_id','destination','interval_seconds','next_run','enabled']}
def delivery_dict(d):
    data={k:getattr(d,k) for k in ['id','report_id','scheduled_at','created_at','status','error','checksum','filename','destination']}
    if not data['status']:data['status']='ready' # 既有归档无状态字段，按已归档展示
    if data['scheduled_at'] is None:data['scheduled_at']=data['created_at']
    return data
