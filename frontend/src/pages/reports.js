import {jobs,reports} from '../api/entities.js';
import {download} from '../api/client.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {deliveryStatus} from '../components/common/status.js';
import {esc,date,notify} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
function deliveryItem(d){
 const ready=d.status==='ready';
 return '<div class="delivery"><div><strong>'+esc(d.filename||('归档 #'+d.id))+'</strong> '+deliveryStatus(d.status)
 +'<p>期次 '+date(d.scheduled_at)+' · 登记 '+date(d.created_at)+' · '+esc(d.destination)+'</p>'
 +(d.status==='failed'?'<small class="failure">失败原因：'+esc(d.error||'未知原因')+'</small>':d.checksum?'<small>SHA256 '+esc(d.checksum.slice(0,24))+'…</small>':'<small>等待后台生成表格与说明文件</small>')
 +'</div><div><button class="text-button" data-download="'+d.id+'" data-format="csv" '+(ready?'':'disabled')+'>CSV ↓</button><button class="text-button" data-download="'+d.id+'" data-format="json" '+(ready?'':'disabled')+'>JSON ↓</button>'
 +(!ready&&session.user.role==='admin'?'<button class="text-button" data-repair="'+d.id+'">按快照修复</button>':'')
 +'</div></div>';
}
export async function reportPage(){
 const [list,deliveries,allJobs]=await Promise.all([reports.list(),reports.deliveries(),jobs.list()]);workspace.reports=list;
 const approved=allJobs.filter(j=>j.approved&&j.status==='completed');
 const failed=deliveries.filter(d=>d.status==='failed').length;
 return heading('05 / DISTRIBUTION','定时分发与归档','把批准后的结果交付到本地业务收件箱。每份 CSV 与 JSON 留有时间、目标组和校验指纹；两份文件齐全且校验通过才开放下载。','<button class="button" id="refresh-reports">刷新收件箱 ↻</button>')+'<div class="report-grid"><section class="panel"><div class="section-title"><h2>创建分发计划</h2></div><form id="report-form"><label>简报名称<input name="name" required minlength="2" value="日间业务复核简报"></label><label>已批准分析<select name="job_id" required>'+approved.map(j=>'<option value="'+j.id+'">'+esc(j.name)+'</option>').join('')+'</select></label><label>业务接收组<input name="destination" value="业务复核组 · 本地收件箱" required></label><div class="parameter-grid"><label>分发周期<select name="interval_seconds"><option value="86400">每日</option><option value="604800">每周</option><option value="60">每分钟（验收）</option></select></label><label>首次执行<select name="delay_seconds"><option value="0">立即</option><option value="60">1 分钟后</option><option value="3600">1 小时后</option></select></label></div><button type="submit" class="primary" '+(session.user.role!=='admin'||!approved.length?'disabled':'')+'>保存分发计划</button></form><p class="hint">后台 worker 按每个到期时点登记归档，停机恢复后按原时点补齐漏期；暂停期间不补发，重新启用自新时点起算。仅负责人可创建、暂停或修复；接收组为本地标签。</p></section><section><div class="section-title"><h2>运行中的计划</h2><span>'+list.filter(r=>r.enabled).length+' 条已启用</span></div><div class="schedule-list">'+list.map(r=>'<article><div><strong>'+esc(r.name)+'</strong><p>'+esc(r.destination)+'</p><small>下次 '+date(r.next_run)+' · 周期 '+r.interval_seconds+' 秒'+(r.enabled?'':' · 已暂停')+'</small></div><button class="button small" data-toggle="'+r.id+'" '+(session.user.role!=='admin'?'disabled':'')+'>'+(r.enabled?'暂停':'启用')+'</button></article>').join('')+'</div><section class="panel inbox"><div class="section-title"><h2>本地收件箱</h2><span>'+deliveries.length+' 份归档'+(failed?' · '+failed+' 份失败':'')+'</span></div>'+deliveries.map(deliveryItem).join('')+(!deliveries.length?'<p class="empty">计划执行后，文件会出现在此处。等待片刻后刷新。</p>':'')+'</section></section></div>';
}
export function bindReports(refresh){document.querySelector('#refresh-reports').onclick=refresh;submit(document.querySelector('#report-form'),async f=>{await reports.create({name:f.get('name'),job_id:Number(f.get('job_id')),destination:f.get('destination'),interval_seconds:Number(f.get('interval_seconds')),delay_seconds:Number(f.get('delay_seconds'))});notify('计划已保存，后台将按到期时间归档');await refresh();});document.querySelectorAll('[data-toggle]').forEach(b=>b.onclick=async()=>{try{await reports.toggle(b.dataset.toggle);await refresh();}catch(e){notify(e.message,true);}});document.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>download(b.dataset.download,b.dataset.format).catch(e=>notify(e.message,true)));document.querySelectorAll('[data-repair]').forEach(b=>b.onclick=async()=>{try{await reports.repair(b.dataset.repair);notify('已沿用当次批准结果与接收组重建归档');await refresh();}catch(e){notify(e.message,true);}});}
