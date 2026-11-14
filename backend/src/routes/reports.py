import os, time, hashlib
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from src.config.database import get_db
from src.config.settings import ARTIFACT_DIR
from src.models import Report, Delivery
from src.schemas.report import ReportInput
from src.middlewares.auth import current_user, admin_only
from src.services import reports
from src.services.audit import record
from src.utils.serialization import report_dict, delivery_dict
router=APIRouter()
@router.get('/reports')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [report_dict(r) for r in db.scalars(select(Report).order_by(Report.id.desc()))]
@router.post('/reports',status_code=201)
def create(data:ReportInput,db=Depends(get_db),u=Depends(admin_only)):
    r=reports.create(db,data); record(db,u.email,'report.schedule',{'id':r.id,'destination':r.destination}); db.commit()
    return report_dict(r)
@router.post('/reports/{id}/toggle')
def toggle(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=db.get(Report,id)
    if not r:raise HTTPException(404,'分发计划不存在')
    r.enabled=not r.enabled
    if r.enabled:r.next_run=time.time()+r.interval_seconds # 重新启用从新时点起算，暂停期间不补发
    record(db,u.email,'report.toggle',{'id':id,'enabled':r.enabled});db.commit()
    return report_dict(r)
@router.get('/deliveries')
def deliveries(db=Depends(get_db),u=Depends(current_user)):
    return [delivery_dict(d) for d in db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(100))]
@router.post('/deliveries/{id}/repair')
def repair(id:int,db=Depends(get_db),u=Depends(admin_only)):
    d=db.get(Delivery,id)
    if not d:raise HTTPException(404,'归档不存在')
    try:
        reports.repair(db,d)
    except Exception as e:
        d.status='failed'; d.error=str(e)[:990]
        record(db,u.email,'delivery.repair_failed',{'id':id,'error':d.error}); db.commit()
        raise HTTPException(409,'修复失败：'+d.error)
    record(db,u.email,'delivery.repaired',{'id':id,'scheduled_at':d.scheduled_at}); db.commit()
    return delivery_dict(d)
@router.get('/deliveries/{id}/download')
def download(id:int,format:str='csv',db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Delivery,id)
    if not d:raise HTTPException(404,'归档不存在')
    if format not in ('csv','json'):raise HTTPException(422,'支持 CSV 或 JSON')
    status=d.status or 'ready' # 既有归档无状态字段，按已归档处理
    if status=='pending':raise HTTPException(409,'该期简报正在归档，请稍后重试')
    if status=='failed':raise HTTPException(409,'该期简报归档失败：'+(d.error or '未知原因')+'，请修复后再下载')
    filename=d.filename+('.json' if format=='json' else '')
    p=os.path.join(ARTIFACT_DIR,filename)
    if not os.path.exists(p):raise HTTPException(409,'归档文件缺损，请使用修复重建')
    expect=d.meta_checksum if format=='json' else d.checksum
    if expect:
        with open(p,'rb') as f: digest=hashlib.sha256(f.read()).hexdigest()
        if digest!=expect:raise HTTPException(409,'归档校验未通过，请使用修复重建')
    return FileResponse(p,filename=filename,media_type='application/json' if format=='json' else 'text/csv; charset=utf-8')
