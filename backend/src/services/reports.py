import time, os, csv, io, hashlib, json, logging
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from src.models import Job, Report, Delivery
from src.config.settings import ARTIFACT_DIR
# 单次 tick 每个计划最多补登记的期数；剩余漏期下个 tick 继续，避免长时间停机后单次补齐拖垮 worker。
CATCHUP_LIMIT = 200
PENDING_LIMIT = 20
def create(db, data):
    j=db.get(Job,data.job_id)
    if not j or j.status!='completed' or not j.approved:
        raise HTTPException(409,'请先选择已完成且获批准的分析结果')
    r=Report(name=data.name, job_id=j.id, destination=data.destination, interval_seconds=data.interval_seconds, next_run=time.time()+data.delay_seconds, enabled=True)
    db.add(r); db.flush()
    return r
def snapshot_for(report, job):
    # 当次批准结果与接收组固定进归档快照；之后任务变更或缺损修复都以此为准。
    return {'job_id':job.id, 'job':job.name, 'params':job.params or {}, 'result':job.result or {}, 'destination':report.destination}
def _register_one(db, r, due, now, snapshot):
    """登记一个到期时点；同一时点已存在则忽略，返回是否新登记。"""
    values=dict(report_id=r.id, scheduled_at=due, created_at=now, status='pending', error='', checksum='', meta_checksum='', filename=f'report-{r.id}-{int(due*1000)}.csv', destination=r.destination, snapshot=snapshot)
    dialect=db.get_bind().dialect.name
    if dialect=='sqlite':
        return db.execute(sqlite_insert(Delivery).values(**values).on_conflict_do_nothing(index_elements=['report_id','scheduled_at'])).rowcount
    if dialect=='postgresql':
        return db.execute(pg_insert(Delivery).values(**values).on_conflict_do_nothing(index_elements=['report_id','scheduled_at'])).rowcount
    if db.scalar(select(Delivery.id).where(Delivery.report_id==r.id,Delivery.scheduled_at==due)):
        return 0
    db.add(Delivery(**values)); db.flush()
    return 1
def register_due(db, now=None):
    """按计划的每个到期时点登记一条待分发归档（含停机期间的漏期），并按期推进 next_run。

    (report_id, scheduled_at) 唯一约束保证重试与并发执行只认一份。
    """
    now=time.time() if now is None else now
    count=0
    due_reports=db.scalars(select(Report).where(Report.enabled==True,Report.next_run<=now).with_for_update()).all()
    for r in due_reports:
        j=db.get(Job,r.job_id)
        if not j or not j.approved:
            continue # 结果未获批准：不登记，next_run 保持原时点，批准恢复后补齐
        due=r.next_run; caught=0
        snapshot=snapshot_for(r,j)
        while due<=now and caught<CATCHUP_LIMIT:
            count+=_register_one(db,r,due,now,snapshot)
            due+=r.interval_seconds; caught+=1
        r.next_run=due
    return count
def _source(db, d):
    if d.snapshot: return d.snapshot
    r=db.get(Report,d.report_id)
    j=db.get(Job,r.job_id) if r else None
    if not j: raise ValueError('缺少当次快照且原分析结果不存在，无法重建')
    return {'job':j.name, 'params':j.params or {}, 'result':j.result or {}, 'destination':d.destination}
def _csv_bytes(result):
    out=io.StringIO()
    out.write('\ufeff')
    table=result.get('table',{})
    cols=table.get('columns',[])
    writer=csv.writer(out)
    def safe(v):
        if isinstance(v,(int,float)) and not isinstance(v,bool): return v
        text=str(v)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([safe(row.get(c['key'],'')) for c in cols])
    return out.getvalue().encode('utf-8')
def _atomic_write(path, data):
    tmp=path+'.tmp'
    with open(tmp,'wb') as f: f.write(data)
    os.replace(tmp,path) # 同目录原子替换，中途停机只留 .tmp 残件，不会截断正式归档
def write_archive(db, d):
    """按快照生成表格与说明两份文件，齐全且校验通过后才允许置为 ready。"""
    src=_source(db,d)
    result=src.get('result') or {}
    if not d.filename: d.filename=f'report-{d.report_id}-delivery-{d.id}.csv'
    data=_csv_bytes(result)
    meta=json.dumps({'job':src.get('job'), 'params':src.get('params'), 'result':result, 'destination':src.get('destination'), 'scheduled_at':d.scheduled_at, 'checksum':hashlib.sha256(data).hexdigest()}, ensure_ascii=False, allow_nan=False).encode('utf-8')
    os.makedirs(ARTIFACT_DIR,exist_ok=True)
    csv_path=os.path.join(ARTIFACT_DIR,d.filename)
    json_path=csv_path+'.json'
    _atomic_write(csv_path,data)
    _atomic_write(json_path,meta)
    # 回读校验：两份文件齐全、SHA256 一致、说明可解析，才开放下载
    for path,raw in ((csv_path,data),(json_path,meta)):
        if not os.path.exists(path): raise IOError('归档文件未写全：'+os.path.basename(path))
        with open(path,'rb') as f:
            if hashlib.sha256(f.read()).hexdigest()!=hashlib.sha256(raw).hexdigest(): raise IOError('归档校验失败：'+os.path.basename(path))
    with open(json_path,encoding='utf-8') as f: json.load(f)
    d.checksum=hashlib.sha256(data).hexdigest()
    d.meta_checksum=hashlib.sha256(meta).hexdigest()
def process_pending(db, limit=PENDING_LIMIT):
    """生成已登记待分发的归档；暂停中的计划不补发。返回处理过的归档。"""
    rows=db.scalars(select(Delivery).join(Report,Delivery.report_id==Report.id).where(Delivery.status=='pending',Report.enabled==True).order_by(Delivery.scheduled_at).limit(limit)).all()
    for d in rows:
        try:
            write_archive(db,d)
            d.status='ready'; d.error=''
        except Exception as e:
            logging.exception('Delivery %s failed',d.id)
            d.status='failed'; d.error=str(e)[:990]
    return rows
def repair(db, d):
    """修复缺损或失败归档：沿用当次快照中的批准结果与接收组重建两份文件。"""
    write_archive(db,d)
    d.status='ready'; d.error=''
    return d
