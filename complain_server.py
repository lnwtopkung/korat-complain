"""
เซิร์ฟเวอร์ข้อมูลร้องเรียน เทศบาลนครโคราช
วิธีใช้:
  pip install requests
  python complain_server.py
เปิดเบราว์เซอร์: http://localhost:8765
"""

import json, time, threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

TOKEN    = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJrb3JhdENpdHkiLCJleHAiOjE3NzY1MTY2NzAsImlhdCI6MTc3MzkyNDY3MCwia2V5IjoiNWRmMDY1NzA0NmUwZmIwMDAxNmRiMmUwIn0.kxQ9bKD2hdwE1mKKqwgzl_kYr1jXLCKPb0zYyzzjNic"
BASE_URL = "https://prapa.koratcity.go.th/koratCity/getComplain"
import os
PORT = int(os.environ.get("PORT", 8765))

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "token": TOKEN,
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0",
    "referer": "https://prapa.koratcity.go.th/chart/view-statistic-complain.html",
}

_cache = {"data": [], "ts": 0, "lock": threading.Lock()}
CACHE_SEC = 10800


def build_params(page, start_ts, end_ts):
    cols = {}
    for i in range(7):
        cols[f"columns[{i}][data]"]          = "createDate" if i == 1 else "function"
        cols[f"columns[{i}][name]"]          = ""
        cols[f"columns[{i}][searchable]"]    = "true"
        cols[f"columns[{i}][orderable]"]     = "true" if i <= 2 else "false"
        cols[f"columns[{i}][search][value]"] = ""
        cols[f"columns[{i}][search][regex]"] = "false"
    return {**cols, "draw": page+1, "order[0][column]": 0, "order[0][dir]": "asc",
            "start": page*5, "length": 5, "search[value]": "", "search[regex]": "false",
            "sizeContents": 5, "page": page, "keyWord": "", "startDate": start_ts,
            "endDate": end_ts, "orderBy": 2, "isGuest": 0, "_": int(time.time()*1000)}


def get_dept(r):
    aa = r.get("assignAdmins", [])
    if aa and aa[0].get("categoryProfile", {}).get("categoryName"):
        return aa[0]["categoryProfile"]["categoryName"]
    return "ไม่ระบุ"


def get_topic(r):
    tc = r.get("typeComplains", [])
    if tc and tc[0].get("typeComplainName"):
        return tc[0]["typeComplainName"]
    return r.get("title", "ไม่ระบุ")


def fetch_live(days=90):
    end_ts   = int(time.time() * 1000)
    start_ts = end_ts - days * 86_400_000
    print(f"[API] กำลังดึงข้อมูล...")
    first = requests.get(BASE_URL, params=build_params(0, start_ts, end_ts), headers=HEADERS, timeout=30)
    first.raise_for_status()
    d = first.json()
    if d.get("status") == 500:
        raise Exception(d.get("message", "Token หมดอายุ"))
    total_pages = d["data"]["totalPages"]
    total_el    = d["data"]["totalElements"]
    rows = list(d["data"]["content"])
    for page in range(1, total_pages):
        r = requests.get(BASE_URL, params=build_params(page, start_ts, end_ts), headers=HEADERS, timeout=30)
        r.raise_for_status()
        rows.extend(r.json().get("data", {}).get("content", []))
        if page % 20 == 0:
            print(f"[API]   {len(rows)}/{total_el} ...")
    print(f"[API] สำเร็จ: {len(rows):,} รายการ")
    return rows


def get_data(force=False):
    with _cache["lock"]:
        if force or (time.time() - _cache["ts"]) > CACHE_SEC:
            try:
                rows = fetch_live()
                slim = [{"id": r.get("complainId",""), "date": r.get("complainDate",0),
                         "topic": get_topic(r), "status": r.get("statusCode",0),
                         "src": r.get("from",0), "dept": get_dept(r),
                         "od": r.get("overDueDate",0) or 0,
                         "create": r.get("createDate",0)} for r in rows]
                _cache["data"] = slim
                _cache["ts"]   = time.time()
            except Exception as e:
                print(f"[ERROR] {e}")
        return _cache["data"], _cache["ts"]


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard ร้องเรียน — เทศบาลนครโคราช</title>
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Sarabun',sans-serif;background:#f4f6fb;color:#222;font-size:14px;}
.bar{background:#1e3a8a;color:#fff;padding:0 20px;height:52px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:99;}
.bar h1{font-size:16px;font-weight:700;flex:1;}
#upd{font-size:12px;opacity:.75;white-space:nowrap;}
.tbtn{padding:6px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.15);color:#fff;cursor:pointer;font-size:13px;font-family:'Sarabun',sans-serif;}
.tbtn:hover{background:rgba(255,255,255,.25);}
.tbtn.on{background:#16a34a;border-color:#16a34a;}
#pbar{height:3px;background:#3b82f6;width:0%;transition:width .3s;position:fixed;top:52px;left:0;right:0;z-index:98;}
/* nav */
.nav{background:#fff;border-bottom:1px solid #e5e7eb;display:flex;padding:0 20px;}
.nav-btn{padding:14px 20px;font-size:14px;font-weight:500;color:#6b7280;cursor:pointer;border-bottom:2px solid transparent;font-family:'Sarabun',sans-serif;background:none;border-top:none;border-left:none;border-right:none;}
.nav-btn.active{color:#2563eb;border-bottom-color:#2563eb;}
.nav-btn:hover:not(.active){color:#374151;background:#f9fafb;}
/* pages */
.page{display:none;}.page.show{display:block;}
.con{max-width:1200px;margin:0 auto;padding:16px 20px;}
/* metrics */
.met{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:20px;}
.m{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.ml{font-size:11px;color:#888;margin-bottom:4px;}.mv{font-size:22px;font-weight:700;}
/* charts */
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;}
.chart-grid-3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:20px;}
.card{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.card h3{font-size:13px;font-weight:600;color:#6b7280;margin-bottom:14px;text-transform:uppercase;letter-spacing:.04em;}
.chart-wrap{position:relative;width:100%;}
/* filter */
.fil{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.fil input,.fil select{padding:8px 10px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:13px;background:#fff;color:#222;outline:none;}
.fil input{flex:1;min-width:140px;}
/* table */
.tc{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{background:#f9fafb;padding:9px 12px;text-align:left;font-weight:600;color:#6b7280;border-bottom:1px solid #f0f0f0;white-space:nowrap;font-size:11px;}
td{padding:8px 12px;border-bottom:1px solid #f5f5f5;vertical-align:middle;}
tr:hover td{background:#fafafa;}tr:last-child td{border-bottom:none;}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;font-weight:600;white-space:nowrap;}
.b0{background:#dbeafe;color:#1d4ed8;}.b1{background:#fef3c7;color:#92400e;}
.b3{background:#dcfce7;color:#166534;}.b4{background:#fce7f3;color:#9d174d;}.b5{background:#f3f4f6;color:#374151;}
.od{color:#dc2626;font-size:10px;font-weight:700;margin-left:3px;}
.nt{background:#fef3c7;color:#92400e;font-size:10px;padding:1px 5px;border-radius:4px;margin-left:4px;font-weight:600;}
.pag{display:flex;gap:4px;align-items:center;padding:10px 14px;flex-wrap:wrap;}
.pi{flex:1;font-size:12px;color:#9ca3af;}
.pb{padding:5px 10px;border-radius:7px;border:1px solid #e5e7eb;background:#fff;color:#333;cursor:pointer;font-size:12px;}
.pb.a{background:#2563eb;color:#fff;border-color:#2563eb;}.pb:hover:not(.a){background:#f3f4f6;}
/* month filter */
.mfil{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;}
.mfil select{padding:8px 12px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:13px;background:#fff;color:#222;outline:none;}
.mfil label{font-size:13px;color:#6b7280;font-weight:500;}
@media(max-width:700px){.chart-grid,.chart-grid-3{grid-template-columns:1fr;}}
</style></head><body>

<div class="bar">
  <h1>📊 Dashboard ร้องเรียน — เทศบาลนครโคราช</h1>
  <span id="upd">กำลังโหลด...</span>
  <button class="tbtn on" id="abtn" onclick="toggleAuto()">⏱ Auto 3ชม</button>
  <button class="tbtn" onclick="loadData(true)">↻ รีเฟรช</button>
</div>
<div id="pbar"></div>

<div class="nav">
  <button class="nav-btn active" onclick="showPage('dash')">📊 Dashboard</button>
  <button class="nav-btn" onclick="showPage('monthly')">📅 รายเดือน</button>
  <button class="nav-btn" onclick="showPage('list')">📋 รายการ</button>
</div>

<!-- PAGE: DASHBOARD -->
<div class="page show" id="page-dash">
<div class="con">
  <div class="met">
    <div class="m"><div class="ml">ทั้งหมด</div><div class="mv" style="color:#2563eb" id="m0">—</div></div>
    <div class="m"><div class="ml">เสร็จสิ้น</div><div class="mv" style="color:#16a34a" id="m1">—</div></div>
    <div class="m"><div class="ml">ระหว่างดำเนินการ</div><div class="mv" style="color:#d97706" id="m2">—</div></div>
    <div class="m"><div class="ml">รอดำเนินการ</div><div class="mv" style="color:#6366f1" id="m3">—</div></div>
    <div class="m"><div class="ml">ยกเลิก</div><div class="mv" style="color:#6b7280" id="m4">—</div></div>
    <div class="m"><div class="ml">เกินกำหนด</div><div class="mv" style="color:#dc2626" id="m5">—</div></div>
  </div>
  <div class="chart-grid">
    <div class="card">
      <h3>แนวโน้มรายเดือน</h3>
      <div class="chart-wrap" style="height:220px"><canvas id="c-trend"></canvas></div>
    </div>
    <div class="card">
      <h3>สัดส่วนสถานะ</h3>
      <div class="chart-wrap" style="height:220px"><canvas id="c-status"></canvas></div>
    </div>
  </div>
  <div class="chart-grid">
    <div class="card">
      <h3>หัวข้อร้องเรียนสูงสุด 10 อันดับ</h3>
      <div class="chart-wrap" style="height:260px"><canvas id="c-topic"></canvas></div>
    </div>
    <div class="card">
      <h3>หน่วยงานรับผิดชอบ</h3>
      <div class="chart-wrap" style="height:260px"><canvas id="c-dept"></canvas></div>
    </div>
  </div>
  <div class="chart-grid">
    <div class="card">
      <h3>แหล่งที่มา</h3>
      <div class="chart-wrap" style="height:200px"><canvas id="c-src"></canvas></div>
    </div>
    <div class="card">
      <h3>รายวัน (30 วันล่าสุด)</h3>
      <div class="chart-wrap" style="height:200px"><canvas id="c-daily"></canvas></div>
    </div>
  </div>
</div></div>

<!-- PAGE: MONTHLY -->
<div class="page" id="page-monthly">
<div class="con">
  <div class="mfil">
    <label>เดือน:</label>
    <select id="sel-month" onchange="renderMonthly()"><option value="">-- ทุกเดือน --</option></select>
    <label>หน่วยงาน:</label>
    <select id="sel-mdept" onchange="renderMonthly()"><option value="">ทุกหน่วยงาน</option></select>
  </div>
  <div class="met" id="m-met"></div>
  <div class="chart-grid">
    <div class="card">
      <h3>จำนวนร้องเรียนแต่ละเดือน</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="c-mbar"></canvas></div>
    </div>
    <div class="card">
      <h3>สถานะแต่ละเดือน (stacked)</h3>
      <div class="chart-wrap" style="height:240px"><canvas id="c-mstack"></canvas></div>
    </div>
  </div>
  <div class="chart-grid">
    <div class="card">
      <h3>หัวข้อยอดนิยมในเดือนที่เลือก</h3>
      <div class="chart-wrap" style="height:260px"><canvas id="c-mtopic"></canvas></div>
    </div>
    <div class="card">
      <h3>หน่วยงานในเดือนที่เลือก</h3>
      <div class="chart-wrap" style="height:260px"><canvas id="c-mdept"></canvas></div>
    </div>
  </div>
</div></div>

<!-- PAGE: LIST -->
<div class="page" id="page-list">
<div class="con">
  <div class="fil">
    <input id="q" type="text" placeholder="🔍 ค้นหาหมายเลข / หัวข้อ..." oninput="applyFilter()">
    <select id="fs" onchange="applyFilter()"><option value="">ทุกสถานะ</option><option value="0">รอดำเนินการ</option><option value="1">ระหว่างดำเนินการ</option><option value="3">เสร็จสิ้น</option><option value="5">ยกเลิก</option></select>
    <select id="fd" onchange="applyFilter()"><option value="">ทุกหน่วยงาน</option></select>
    <select id="ft" onchange="applyFilter()"><option value="">ทุกหัวข้อ</option></select>
  </div>
  <div class="tc">
    <div id="msg" style="padding:32px;text-align:center;color:#9ca3af">กำลังโหลด...</div>
    <div id="tw" style="display:none;overflow-x:auto">
      <table><thead><tr><th>#</th><th>หมายเลข</th><th>วันที่</th><th>หัวข้อ</th><th>สถานะ</th><th>แหล่งที่มา</th><th>หน่วยงาน</th></tr></thead>
      <tbody id="tbody"></tbody></table>
    </div>
    <div class="pag" id="pag"></div>
  </div>
</div></div>

<script>
const SM={0:'รอดำเนินการ',1:'ระหว่างดำเนินการ',3:'เสร็จสิ้น',4:'ส่งกลับ',5:'ยกเลิก',8:'อื่นๆ'};
const SC={0:'b0',1:'b1',3:'b3',4:'b4',5:'b5'};
const FM={0:'ไลน์ OA',1:'แอป',2:'เว็บ',3:'โทรศัพท์',4:'เดินเรื่อง',5:'ไลน์'};
const COLORS=['#378ADD','#1D9E75','#D85A30','#7F77DD','#D4537E','#BA7517','#888780','#E24B4A','#639922','#0F6E56'];
const STATUS_COLORS={0:'#6366f1',1:'#f59e0b',3:'#22c55e',5:'#9ca3af'};
let ALL=[],FILT=[],PG=1,PER=10,TIMER=null,AUTO=true,BUSY=false;
let charts={};

// ---- Utils ----
function fmtD(ts){if(!ts)return'-';return new Date(ts).toLocaleDateString('th-TH',{year:'2-digit',month:'short',day:'numeric'});}
function monthKey(ts){if(!ts)return null;const d=new Date(ts);return d.getFullYear()+'-'+(d.getMonth()+1).toString().padStart(2,'0');}
function monthLabel(k){if(!k)return'';const[y,m]=k.split('-');const mn=['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];return mn[parseInt(m)-1]+' '+(parseInt(y)+543);}
function countBy(arr,fn){const m={};arr.forEach(r=>{const k=fn(r);m[k]=(m[k]||0)+1;});return m;}
function badge(c){return'<span class="badge '+(SC[c]||'b5')+'">'+(SM[c]||c)+'</span>';}
function setBar(p){document.getElementById('pbar').style.width=p+'%';}
function destroyChart(id){if(charts[id]){charts[id].destroy();delete charts[id];}}

// ---- Nav ----
function showPage(name){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('show'));
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('page-'+name).classList.add('show');
  event.target.classList.add('active');
  if(name==='monthly')renderMonthly();
}

// ---- Load Data ----
async function loadData(force=false){
  if(BUSY)return;BUSY=true;
  setBar(10);
  document.getElementById('upd').textContent='กำลังดึงข้อมูล...';
  try{
    const r=await fetch('/api/data'+(force?'?force=1':''));
    setBar(60);
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    ALL=d.data;
    setBar(90);
    updMetrics();updFilters();applyFilter();
    renderDashCharts();
    populateMonthFilter();
    const t=new Date(d.ts*1000).toLocaleTimeString('th-TH');
    document.getElementById('upd').textContent='อัปเดต '+t+' | '+ALL.length.toLocaleString()+' รายการ';
    document.getElementById('msg').style.display='none';
    document.getElementById('tw').style.display='block';
    setBar(100);setTimeout(()=>setBar(0),600);
  }catch(e){
    document.getElementById('upd').textContent='โหลดไม่สำเร็จ: '+e.message;
    setBar(0);
  }
  BUSY=false;
}

// ---- Metrics ----
function updMetrics(){
  const done=ALL.filter(r=>r.status===3).length,proc=ALL.filter(r=>r.status===1).length;
  const wait=ALL.filter(r=>r.status===0).length,can=ALL.filter(r=>r.status===5).length;
  const od=ALL.filter(r=>r.od>0).length;
  [ALL.length,done,proc,wait,can,od].forEach((v,i)=>document.getElementById('m'+i).textContent=v.toLocaleString());
}

// ---- Filters (list page) ----
let _d=new Set(),_t=new Set();
function updFilters(){
  const nd=new Set(ALL.map(r=>r.dept)),nt=new Set(ALL.map(r=>r.topic));
  if(nd.size!==_d.size){_d=nd;const s=document.getElementById('fd'),v=s.value;s.innerHTML='<option value="">ทุกหน่วยงาน</option>';[...nd].sort().forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o);});s.value=v;}
  if(nt.size!==_t.size){_t=nt;const s=document.getElementById('ft'),v=s.value;s.innerHTML='<option value="">ทุกหัวข้อ</option>';[...nt].sort().forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o);});s.value=v;}
}
function applyFilter(){
  const q=document.getElementById('q').value.toLowerCase(),fs=document.getElementById('fs').value;
  const fd=document.getElementById('fd').value,ft=document.getElementById('ft').value;
  FILT=ALL.filter(r=>{
    if(q&&!r.topic.toLowerCase().includes(q)&&!String(r.id).includes(q))return false;
    if(fs!==''&&String(r.status)!==fs)return false;
    if(fd&&r.dept!==fd)return false;
    if(ft&&r.topic!==ft)return false;
    return true;
  });
  PG=1;renderList();
}
function goPage(p){PG=p;renderList();document.querySelector('.tc').scrollIntoView({behavior:'smooth'});}
function renderList(){
  const s=(PG-1)*PER,sl=FILT.slice(s,s+PER),now=Date.now();
  if(!sl.length){document.getElementById('tbody').innerHTML='<tr><td colspan="7" style="text-align:center;padding:32px;color:#9ca3af">ไม่พบข้อมูล</td></tr>';document.getElementById('pag').innerHTML='';return;}
  document.getElementById('tbody').innerHTML=sl.map((r,i)=>
    '<tr><td style="color:#9ca3af;font-size:12px">'+(s+i+1)+'</td>'
    +'<td style="font-weight:600">'+r.id+'</td>'
    +'<td style="white-space:nowrap;color:#6b7280;font-size:12px">'+fmtD(r.date)+'</td>'
    +'<td>'+r.topic+((now-r.create)<86400000?'<span class="nt">ใหม่</span>':'')+'</td>'
    +'<td>'+badge(r.status)+(r.od>0?'<span class="od">+'+r.od+'วัน</span>':'')+'</td>'
    +'<td style="color:#6b7280;font-size:12px">'+(FM[r.src]||r.src)+'</td>'
    +'<td style="font-size:12px">'+r.dept+'</td></tr>'
  ).join('');
  const tp=Math.ceil(FILT.length/PER),e=Math.min(s+PER,FILT.length);
  let ph='<span class="pi">แสดง '+(s+1)+'-'+e+' จาก '+FILT.length.toLocaleString()+' รายการ</span>';
  if(PG>1)ph+='<button class="pb" onclick="goPage(1)">«</button><button class="pb" onclick="goPage('+(PG-1)+')">‹</button>';
  for(let p=Math.max(1,PG-4);p<=Math.min(tp,PG+4);p++)ph+='<button class="pb'+(p===PG?' a':'')+'" onclick="goPage('+p+')">'+p+'</button>';
  if(PG<tp)ph+='<button class="pb" onclick="goPage('+(PG+1)+')">›</button><button class="pb" onclick="goPage('+tp+')">»</button>';
  document.getElementById('pag').innerHTML=ph;
}

// ---- Dashboard Charts ----
function renderDashCharts(){
  // Monthly trend
  const mCount=countBy(ALL,r=>monthKey(r.date));
  const mKeys=Object.keys(mCount).sort();
  destroyChart('trend');
  charts['trend']=new Chart(document.getElementById('c-trend'),{
    type:'line',
    data:{labels:mKeys.map(monthLabel),datasets:[{label:'จำนวนร้องเรียน',data:mKeys.map(k=>mCount[k]),borderColor:'#2563eb',backgroundColor:'rgba(37,99,235,.1)',fill:true,tension:.4,pointRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{ticks:{font:{size:11}}},y:{ticks:{font:{size:11}},grid:{color:'rgba(0,0,0,.05)'},beginAtZero:true}}}
  });

  // Status donut
  const sCnt={};[0,1,3,5].forEach(s=>sCnt[s]=ALL.filter(r=>r.status===s).length);
  destroyChart('status');
  charts['status']=new Chart(document.getElementById('c-status'),{
    type:'doughnut',
    data:{labels:['รอดำเนินการ','ระหว่างดำเนินการ','เสร็จสิ้น','ยกเลิก'],
          datasets:[{data:[sCnt[0],sCnt[1],sCnt[3],sCnt[5]],backgroundColor:['#6366f1','#f59e0b','#22c55e','#9ca3af'],borderWidth:2,borderColor:'#fff'}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'60%',
      plugins:{legend:{position:'right',labels:{font:{size:11},padding:8,boxWidth:12}},
               tooltip:{callbacks:{label:c=>` ${c.label}: ${c.raw} (${Math.round(c.raw/ALL.length*100)}%)`}}}}
  });

  // Top topics bar
  const tCnt=countBy(ALL,r=>r.topic);
  const tTop=Object.entries(tCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('topic');
  charts['topic']=new Chart(document.getElementById('c-topic'),{
    type:'bar',
    data:{labels:tTop.map(([k])=>k),datasets:[{data:tTop.map(([,v])=>v),backgroundColor:COLORS,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{font:{size:10}},grid:{color:'rgba(0,0,0,.05)'}},y:{ticks:{font:{size:11}}}}}
  });

  // Dept bar
  const dCnt=countBy(ALL,r=>r.dept);
  const dTop=Object.entries(dCnt).sort((a,b)=>b[1]-a[1]).slice(0,8);
  destroyChart('dept');
  charts['dept']=new Chart(document.getElementById('c-dept'),{
    type:'bar',
    data:{labels:dTop.map(([k])=>k),datasets:[{data:dTop.map(([,v])=>v),backgroundColor:COLORS,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{font:{size:10}}},y:{ticks:{font:{size:11}}}}}
  });

  // Source donut
  const srcCnt=countBy(ALL,r=>FM[r.src]||('รหัส '+r.src));
  const srcE=Object.entries(srcCnt).sort((a,b)=>b[1]-a[1]);
  destroyChart('src');
  charts['src']=new Chart(document.getElementById('c-src'),{
    type:'doughnut',
    data:{labels:srcE.map(([k])=>k),datasets:[{data:srcE.map(([,v])=>v),backgroundColor:COLORS,borderWidth:2,borderColor:'#fff'}]},
    options:{responsive:true,maintainAspectRatio:false,cutout:'55%',
      plugins:{legend:{position:'right',labels:{font:{size:11},padding:6,boxWidth:12}}}}
  });

  // Daily last 30
  const now=Date.now(),day=86400000;
  const dMap={};
  for(let i=29;i>=0;i--){const k=new Date(now-i*day).toISOString().slice(0,10);dMap[k]=0;}
  ALL.forEach(r=>{if(r.date){const k=new Date(r.date).toISOString().slice(0,10);if(k in dMap)dMap[k]++;}});
  destroyChart('daily');
  charts['daily']=new Chart(document.getElementById('c-daily'),{
    type:'bar',
    data:{labels:Object.keys(dMap).map(k=>{const d=new Date(k);return (d.getDate())+' '+ ['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'][d.getMonth()];}),
          datasets:[{data:Object.values(dMap),backgroundColor:'rgba(37,99,235,.6)',borderRadius:3}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{font:{size:9},maxRotation:45,autoSkip:true,maxTicksLimit:15}},y:{beginAtZero:true,ticks:{font:{size:10}},grid:{color:'rgba(0,0,0,.05)'}}}}
  });
}

// ---- Monthly Page ----
function populateMonthFilter(){
  const months=[...new Set(ALL.map(r=>monthKey(r.date)).filter(Boolean))].sort();
  const sel=document.getElementById('sel-month');
  const cur=sel.value;
  sel.innerHTML='<option value="">-- ทุกเดือน --</option>';
  months.forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=monthLabel(k);sel.appendChild(o);});
  sel.value=cur||months[months.length-1]||'';

  const depts=[...new Set(ALL.map(r=>r.dept))].sort();
  const dsel=document.getElementById('sel-mdept');
  const dcur=dsel.value;
  dsel.innerHTML='<option value="">ทุกหน่วยงาน</option>';
  depts.forEach(d=>{const o=document.createElement('option');o.value=d;o.textContent=d;dsel.appendChild(o);});
  dsel.value=dcur;
}

function renderMonthly(){
  const selM=document.getElementById('sel-month').value;
  const selD=document.getElementById('sel-mdept').value;

  // Filter data
  let data=ALL;
  if(selD) data=data.filter(r=>r.dept===selD);

  // Summary metrics
  const months=[...new Set(ALL.map(r=>monthKey(r.date)).filter(Boolean))].sort();
  let mData=selM? data.filter(r=>monthKey(r.date)===selM) : data;

  const done=mData.filter(r=>r.status===3).length;
  const proc=mData.filter(r=>r.status===1).length;
  const wait=mData.filter(r=>r.status===0).length;
  const od=mData.filter(r=>r.od>0).length;
  document.getElementById('m-met').innerHTML=`
    <div class="m"><div class="ml">${selM?monthLabel(selM):'ทุกเดือน'}</div><div class="mv" style="color:#2563eb">${mData.length.toLocaleString()}</div></div>
    <div class="m"><div class="ml">เสร็จสิ้น</div><div class="mv" style="color:#16a34a">${done.toLocaleString()}</div></div>
    <div class="m"><div class="ml">ระหว่างดำเนินการ</div><div class="mv" style="color:#d97706">${proc.toLocaleString()}</div></div>
    <div class="m"><div class="ml">รอดำเนินการ</div><div class="mv" style="color:#6366f1">${wait.toLocaleString()}</div></div>
    <div class="m"><div class="ml">อัตราสำเร็จ</div><div class="mv" style="color:#16a34a">${mData.length?Math.round(done/mData.length*100):0}%</div></div>
    <div class="m"><div class="ml">เกินกำหนด</div><div class="mv" style="color:#dc2626">${od.toLocaleString()}</div></div>`;

  // Monthly bar
  const mCount=countBy(data,r=>monthKey(r.date));
  const mKeys=months;
  destroyChart('mbar');
  charts['mbar']=new Chart(document.getElementById('c-mbar'),{
    type:'bar',
    data:{labels:mKeys.map(monthLabel),
          datasets:[{label:'จำนวน',data:mKeys.map(k=>mCount[k]||0),
            backgroundColor:mKeys.map(k=>k===selM?'#2563eb':'rgba(37,99,235,.45)'),borderRadius:5}]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{display:false},tooltip:{callbacks:{title:([c])=>monthLabel(mKeys[c.dataIndex])}}},
      scales:{x:{ticks:{font:{size:11}}},y:{beginAtZero:true,ticks:{font:{size:11}},grid:{color:'rgba(0,0,0,.05)'}}},
      onClick:(_,els)=>{if(els[0]){const k=mKeys[els[0].index];document.getElementById('sel-month').value=k;renderMonthly();}}}
  });

  // Stacked monthly
  const s0=mKeys.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===0).length);
  const s1=mKeys.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===1).length);
  const s3=mKeys.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===3).length);
  const s5=mKeys.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===5).length);
  destroyChart('mstack');
  charts['mstack']=new Chart(document.getElementById('c-mstack'),{
    type:'bar',
    data:{labels:mKeys.map(monthLabel),datasets:[
      {label:'เสร็จสิ้น',data:s3,backgroundColor:'#22c55e',borderRadius:0},
      {label:'ระหว่างดำเนินการ',data:s1,backgroundColor:'#f59e0b'},
      {label:'รอดำเนินการ',data:s0,backgroundColor:'#6366f1'},
      {label:'ยกเลิก',data:s5,backgroundColor:'#9ca3af'},
    ]},
    options:{responsive:true,maintainAspectRatio:false,
      plugins:{legend:{position:'bottom',labels:{font:{size:11},padding:8,boxWidth:12}}},
      scales:{x:{stacked:true,ticks:{font:{size:11}}},y:{stacked:true,ticks:{font:{size:11}},grid:{color:'rgba(0,0,0,.05)'}}}}
  });

  // Topic in selected month
  const tCnt=countBy(mData,r=>r.topic);
  const tTop=Object.entries(tCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('mtopic');
  charts['mtopic']=new Chart(document.getElementById('c-mtopic'),{
    type:'bar',
    data:{labels:tTop.map(([k])=>k),datasets:[{data:tTop.map(([,v])=>v),backgroundColor:COLORS,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{font:{size:10}}},y:{ticks:{font:{size:11}}}}}
  });

  // Dept in selected month
  const dCnt=countBy(mData,r=>r.dept);
  const dTop=Object.entries(dCnt).sort((a,b)=>b[1]-a[1]).slice(0,8);
  destroyChart('mdept');
  charts['mdept']=new Chart(document.getElementById('c-mdept'),{
    type:'bar',
    data:{labels:dTop.map(([k])=>k),datasets:[{data:dTop.map(([,v])=>v),backgroundColor:COLORS,borderRadius:4}]},
    options:{responsive:true,maintainAspectRatio:false,indexAxis:'y',
      plugins:{legend:{display:false}},
      scales:{x:{ticks:{font:{size:10}}},y:{ticks:{font:{size:11}}}}}
  });
}

// ---- Auto refresh ----
function toggleAuto(){
  AUTO=!AUTO;
  const btn=document.getElementById('abtn');
  if(AUTO){TIMER=setInterval(()=>loadData(false),10800000);btn.textContent='⏱ Auto 3ชม';btn.className='tbtn on';}
  else{clearInterval(TIMER);btn.textContent='⏱ Auto OFF';btn.className='tbtn';}
}

// Start
loadData(true);
TIMER=setInterval(()=>loadData(false),10800000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        qs     = parse_qs(parsed.query)

        if parsed.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))

        elif parsed.path == "/api/data":
            force = "force" in qs
            try:
                data, ts = get_data(force=force)
                body = json.dumps({"data": data, "ts": ts}, ensure_ascii=False)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))
            except Exception as e:
                body = json.dumps({"error": str(e)})
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    print("=" * 50)
    print("  Dashboard ร้องเรียน เทศบาลนครโคราช")
    print("=" * 50)
    print(f"  กำลังดึงข้อมูลครั้งแรก...")
    get_data(force=True)
    print(f"\n  เปิดเบราว์เซอร์: http://localhost:{PORT}")
    print(f"  กด Ctrl+C เพื่อหยุด")
    print("=" * 50)
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุดแล้ว")


if __name__ == "__main__":
    main()
