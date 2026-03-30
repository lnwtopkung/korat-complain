import json, time, threading, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    parts = line.strip().split("=", 1)
                    if len(parts) == 2:
                        key, val = parts
                        os.environ[key] = val.strip('"').strip("'")
load_dotenv()

TOKEN = os.environ.get("COMPLAIN_TOKEN", "")
BASE_URL = os.environ.get("COMPLAIN_API_URL", "https://prapa.koratcity.go.th/koratCity/getComplain")
PORT = int(os.environ.get("PORT", 8765))
CACHE_SEC = int(os.environ.get("CACHE_SEC", 10800))
PAGE_SIZE = 100
# 1 ตุลาคม 2568 00:00:00 ICT = 1759251600000 ms
START_DATE_LIMIT = 1759251600000 

_cache = {"data": [], "ts": 0, "lock": threading.Lock(), "ready": False, "error": None}

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

def build_params(page, start_ts, end_ts):
    cols = {}
    for i in range(7):
        cols[f"columns[{i}][data]"] = "createDate" if i == 1 else "function"
        cols[f"columns[{i}][name]"] = ""
        cols[f"columns[{i}][searchable]"] = "true"
        cols[f"columns[{i}][orderable]"] = "true" if i <= 2 else "false"
        cols[f"columns[{i}][search][value]"] = ""
        cols[f"columns[{i}][search][regex]"] = "false"
    # เปลี่ยนจาก order[0][column]: 0 (function) เป็น 1 (createDate)
    return {**cols, "draw": page+1, "order[0][column]": 1, "order[0][dir]": "asc",
            "start": page * PAGE_SIZE, "length": PAGE_SIZE, "search[value]": "", "search[regex]": "false",
            "sizeContents": PAGE_SIZE, "page": page, "keyWord": "", "startDate": start_ts,
            "endDate": end_ts, "orderBy": 2, "isGuest": 0, "_": int(time.time()*1000)}

def fetch_live(days=730):
    if not TOKEN: raise Exception("Missing COMPLAIN_TOKEN")
    headers = {"accept": "application/json", "content-type": "application/json", "token": TOKEN,
               "x-requested-with": "XMLHttpRequest", "user-agent": "Mozilla/5.0",
               "referer": "https://prapa.koratcity.go.th/chart/view-statistic-complain.html"}
    end_ts = int(time.time() * 1000)
    # เริ่มดึงข้อมูลถอยหลังไป 1 วัน (30 ก.ย.) เพื่อกันข้อมูลตกหล่นจาก Timezone
    fetch_start_ts = START_DATE_LIMIT - 86400000 
    
    first = requests.get(BASE_URL, params=build_params(0, fetch_start_ts, end_ts), headers=headers, timeout=30)
    first.raise_for_status()
    d = first.json()
    if d.get("status") == 500: raise Exception(d.get("message"))
    
    total_pages = d.get("data", {}).get("totalPages", 0)
    rows = list(d.get("data", {}).get("content", []))
    
    # ดึงข้อมูลให้ครบทุกหน้าโดยไม่ break กลางคัน
    for page in range(1, total_pages):
        r = requests.get(BASE_URL, params=build_params(page, fetch_start_ts, end_ts), headers=headers, timeout=30)
        r.raise_for_status()
        content = r.json().get("data", {}).get("content", [])
        if not content: break
        rows.extend(content)
    return rows

def perform_refresh():
    try:
        rows = fetch_live()
        slim = []
        display_limit = START_DATE_LIMIT - 3600000 
        for r in rows:
            cid = r.get("complainId", 0)
            # Debug Log สำหรับตรวจสอบ ID ที่ต้องการ
            if str(cid) == "2510003":
                print(f"[DEBUG] Found target ID: {cid}, Date: {r.get('complainDate')}")
            
            dt = r.get("complainDate", 0)
            if dt >= display_limit:
                slim.append({"id": int(cid), "date": dt,
                             "topic": get_topic(r), "status": r.get("statusCode",0),
                             "src": r.get("from",0), "dept": get_dept(r),
                             "od": r.get("overDueDate",0) or 0,
                             "create": r.get("createDate",0)})
        with _cache["lock"]:
            _cache["data"] = sorted(slim, key=lambda x: x["date"], reverse=True)
            _cache["ts"] = time.time()
            _cache["ready"] = True
            _cache["error"] = None
        print(f"[CACHE] Success: {len(slim)} items")
    except Exception as e:
        with _cache["lock"]: _cache["error"] = str(e)
        print(f"[CACHE ERROR] {e}")

def background_refresh():
    while True:
        perform_refresh()
        time.sleep(CACHE_SEC)

def get_data(force=False):
    if force: threading.Thread(target=perform_refresh).start()
    waited = 0
    while not _cache["ready"] and waited < 40:
        with _cache["lock"]:
            if _cache["error"] and not _cache["data"]: break
        time.sleep(0.5)
        waited += 1
    with _cache["lock"]:
        if _cache["error"] and not _cache["data"]: raise Exception(_cache["error"])
        return _cache["data"], _cache["ts"]

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard ร้องเรียน — เทศบาลนครราชสีมา</title>
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Sarabun',sans-serif;background:#f4f6fb;color:#222;font-size:14px;}
.bar{background:#14532d;color:#fff;padding:0 20px;height:52px;display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:99;}
.bar h1{font-size:16px;font-weight:700;flex:1;}
#upd{font-size:12px;opacity:.75;}
.tbtn{padding:6px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.15);color:#fff;cursor:pointer;font-size:13px;}
#pbar{height:3px;background:#3b82f6;width:0%;transition:width .3s;position:fixed;top:52px;left:0;right:0;z-index:98;}
.nav{background:#fff;border-bottom:1px solid #e5e7eb;display:flex;padding:0 20px;}
.nav-btn{padding:14px 20px;font-size:14px;font-weight:500;color:#6b7280;cursor:pointer;border-bottom:2px solid transparent;background:none;border:none;}
.nav-btn.active{color:#2563eb;border-bottom-color:#2563eb;}
.page{display:none;}.page.show{display:block;}
.con{max-width:1200px;margin:0 auto;padding:16px 20px;}
.met{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:20px;}
.m{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.ml{font-size:11px;color:#888;margin-bottom:4px;}.mv{font-size:22px;font-weight:700;}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;}
.card{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.card h3{font-size:13px;font-weight:600;color:#6b7280;margin-bottom:14px;}
.chart-wrap{position:relative;width:100%;height:240px;}
.tc{background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06);}
table{width:100%;border-collapse:collapse;font-size:13px;}
th{background:#f9fafb;padding:12px;text-align:left;font-weight:600;color:#6b7280;border-bottom:1px solid #f0f0f0;}
td{padding:10px 12px;border-bottom:1px solid #f5f5f5;}
.badge{display:inline-block;font-size:11px;padding:2px 8px;border-radius:99px;font-weight:600;}
.b0{background:#dbeafe;color:#1d4ed8;}.b1{background:#fef3c7;color:#92400e;}.b3{background:#dcfce7;color:#166534;}.b5{background:#f3f4f6;color:#374151;}.b8{background:#fee2e2;color:#dc2626;}
.od{color:#dc2626;font-size:10px;font-weight:700;margin-left:3px;}
.pag{display:flex;gap:5px;padding:15px;justify-content:center;align-items:center;}
.pb{padding:5px 12px;border:1px solid #ddd;background:#fff;cursor:pointer;border-radius:4px;font-size:13px;}
.pb.active{background:#2563eb;color:#fff;border-color:#2563eb;}
.mfil{display:flex;gap:8px;margin-bottom:16px;align-items:center;flex-wrap:wrap;}
.mfil select{padding:8px 12px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:13px;}
@media(max-width:700px){.chart-grid{grid-template-columns:1fr;}}
</style></head><body>
<div class="bar"><h1>📊 Dashboard ร้องเรียน (ตั้งแต่ 1 ต.ค. 68)</h1><span id="upd">กำลังโหลด...</span><button class="tbtn" onclick="loadData(true)">↻ รีเฟรช</button></div>
<div id="pbar"></div>
<div class="nav"><button class="nav-btn active" onclick="showPage('dash')">📊 Dashboard</button><button class="nav-btn" onclick="showPage('monthly')">📅 รายเดือน</button><button class="nav-btn" onclick="showPage('list')">📋 รายการ</button></div>
<div class="page show" id="page-dash"><div class="con">
  <div class="met">
    <div class="m"><div class="ml">ทั้งหมด</div><div class="mv" id="m0" style="color:#2563eb">—</div></div>
    <div class="m"><div class="ml">เสร็จสิ้น</div><div class="mv" id="m1" style="color:#16a34a">—</div></div>
    <div class="m"><div class="ml">ระหว่างดำเนินการ</div><div class="mv" id="m2" style="color:#d97706">—</div></div>
    <div class="m"><div class="ml">รับเรื่อง</div><div class="mv" id="m3" style="color:#6366f1">—</div></div>
  </div>
  <div class="chart-grid">
    <div class="card"><h3>แนวโน้มรายเดือน</h3><div class="chart-wrap"><canvas id="c-trend"></canvas></div></div>
    <div class="card"><h3>สัดส่วนสถานะ</h3><div class="chart-wrap"><canvas id="c-status"></canvas></div></div>
  </div>
  <div class="chart-grid">
    <div class="card"><h3>หัวข้อร้องเรียนสูงสุด 10 อันดับ</h3><div class="chart-wrap" style="height:260px"><canvas id="c-topic"></canvas></div></div>
    <div class="card"><h3>หน่วยงานรับผิดชอบ</h3><div class="chart-wrap" style="height:260px"><canvas id="c-dept"></canvas></div></div>
  </div>
  <div class="chart-grid">
    <div class="card"><h3>แหล่งที่มา</h3><div class="chart-wrap" style="height:240px"><canvas id="c-src"></canvas></div></div>
    <div class="card"><h3>รายวัน (30 วันล่าสุด)</h3><div class="chart-wrap" style="height:240px"><canvas id="c-daily"></canvas></div></div>
  </div>
</div></div>
<div class="page" id="page-monthly"><div class="con">
  <div class="mfil"><label>เดือน:</label><select id="sel-month" onchange="renderMonthly()"></select><label>หน่วยงาน:</label><select id="sel-mdept" onchange="renderMonthly()"></select></div>
  <div id="m-met" class="met"></div>
  <div class="chart-grid"><div class="card"><h3>จำนวนรายเดือน</h3><div class="chart-wrap"><canvas id="c-mbar"></canvas></div></div><div class="card"><h3>สถานะรายเดือน (Stacked)</h3><div class="chart-wrap"><canvas id="c-mstack"></canvas></div></div></div>
  <div class="chart-grid"><div class="card"><h3>หัวข้อยอดนิยม</h3><div class="chart-wrap" style="height:260px"><canvas id="c-mtopic"></canvas></div></div><div class="card"><h3>หน่วยงานรับผิดชอบ</h3><div class="chart-wrap" style="height:260px"><canvas id="c-mdept"></canvas></div></div></div>
</div></div>
<div class="page" id="page-list"><div class="con">
  <div class="fil" style="margin-bottom:15px;display:flex;gap:10px;flex-wrap:wrap;">
    <input id="q" type="text" placeholder="🔍 ค้นหา ID / หัวข้อ..." style="flex:1;min-width:200px;padding:8px 12px;border-radius:8px;border:1.5px solid #e5e7eb" oninput="applyFilter()">
    <select id="fs" onchange="applyFilter()" style="padding:8px;border-radius:8px;border:1.5px solid #e5e7eb"><option value="">ทุกสถานะ</option><option value="3">เสร็จสิ้น</option><option value="1">ระหว่างดำเนิน</option><option value="0">รับเรื่อง</option><option value="5">ยกเลิก</option><option value="8">ไม่อยู่ในอำนาจหน้าที่</option></select>
    <select id="fl-dept" onchange="applyFilter()" style="padding:8px;border-radius:8px;border:1.5px solid #e5e7eb"><option value="">ทุกหน่วยงาน</option></select>
    <select id="fl-src" onchange="applyFilter()" style="padding:8px;border-radius:8px;border:1.5px solid #e5e7eb"><option value="">ทุกช่องทาง</option></select>
  </div>
  <div id="list-summary" style="margin-bottom:10px;font-size:13px;color:#666;font-weight:500;"></div>
  <div class="tc"><table><thead><tr><th>ลำดับ</th><th>ID</th><th>วันที่</th><th>หัวข้อ</th><th>สถานะ</th><th>แหล่งที่มา</th><th>หน่วยงาน</th></tr></thead><tbody id="tbody"></tbody></table><div id="pag-controls" class="pag"></div></div>
</div></div>
<script>
let ALL=[],FILT=[],PG=1,PER=10,charts={};
const SM={0:'รับเรื่อง',1:'ระหว่างดำเนินการ',3:'เสร็จสิ้น',4:'ส่งกลับ',5:'ยกเลิก',8:'ไม่อยู่ในอำนาจหน้าที่รับผิดชอบ'},SC={0:'b0',1:'b1',3:'b3',5:'b5',8:'b8'},COLORS=['#378ADD','#1D9E75','#D85A30','#7F77DD','#D4537E','#BA7517','#888780','#E24B4A','#639922','#0F6E56'];
const FM={0:'แอปพลิเคชัน', 1:'เข้ามาโดยตรง', 2:'โทรศัพท์', 3:'เว็บไซต์เทศบาล', 4:'เฟสบุ๊ค', 5:'ไลน์', 7:'หนังสือ', 10:'traffy fondue'};
function fmtD(ts){return ts?new Date(ts).toLocaleDateString('th-TH',{year:'2-digit',month:'short',day:'numeric'}):'-';}
function monthKey(ts){if(!ts)return null;const d=new Date(ts);return d.getFullYear()+'-'+(d.getMonth()+1).toString().padStart(2,'0');}
function monthLabel(k){if(!k)return'';const[y,m]=k.split('-');const mn=['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];return mn[parseInt(m)-1]+' '+(parseInt(y)+543);}
function countBy(arr,fn){const m={};arr.forEach(r=>{const k=fn(r);if(k)m[k]=(m[k]||0)+1;});return m;}
function destroyChart(id){if(charts[id]){charts[id].destroy();delete charts[id];}}
function showPage(n){document.querySelectorAll('.page').forEach(p=>p.classList.remove('show'));document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));document.getElementById('page-'+n).classList.add('show');if(event && event.target)event.target.classList.add('active');if(n==='monthly')renderMonthly();}
async function loadData(f=false){
  document.getElementById('upd').textContent='กำลังโหลด...';document.getElementById('pbar').style.width='30%';
  try{
    const r=await fetch('/api/data'+(f?'?force=1':''));const d=await r.json();if(d.error)throw new Error(d.error);
    ALL=d.data;updMetrics();renderDashCharts();populateMonthFilter();applyFilter();
    document.getElementById('upd').textContent='อัปเดต: '+new Date(d.ts*1000).toLocaleTimeString();
    document.getElementById('pbar').style.width='100%';setTimeout(()=>document.getElementById('pbar').style.width='0',500);
  }catch(e){document.getElementById('upd').textContent='Error: '+e.message;document.getElementById('pbar').style.width='0';}
}
function updMetrics(){
  document.getElementById('m0').textContent=ALL.length.toLocaleString();
  document.getElementById('m1').textContent=ALL.filter(r=>r.status===3).length.toLocaleString();
  document.getElementById('m2').textContent=ALL.filter(r=>r.status===1).length.toLocaleString();
  document.getElementById('m3').textContent=ALL.filter(r=>r.status===0).length.toLocaleString();
}
function applyFilter(){
  const q=document.getElementById('q').value.toLowerCase(),fs=document.getElementById('fs').value,fd=document.getElementById('fl-dept').value,fsrc=document.getElementById('fl-src').value;
  FILT=ALL.filter(r=>(!q||String(r.id).includes(q)||r.topic.toLowerCase().includes(q))&&(fs===''||String(r.status)===fs)&&(!fd||r.dept===fd)&&(!fsrc||String(r.src)===fsrc));
  PG=1;renderList();
}
function getSrcName(v){if(typeof v==='string' && isNaN(v)) return v; return FM[v] || 'อื่นๆ ('+v+')';}
function renderList(){
  const s=(PG-1)*PER,sl=FILT.slice(s,s+PER),total=Math.ceil(FILT.length/PER);
  document.getElementById('list-summary').textContent = `พบข้อมูลทั้งหมด ${FILT.length.toLocaleString()} รายการ (หน้าที่ ${PG}/${total || 1})`;
  document.getElementById('tbody').innerHTML=sl.map((r,i)=>`<tr><td style="color:#888">${s+i+1}</td><td><b>${r.id}</b></td><td>${fmtD(r.date)}</td><td>${r.topic}</td><td><span class="badge ${SC[r.status]||''}">${SM[r.status]||r.status}</span></td><td>${getSrcName(r.src)}</td><td>${r.dept}</td></tr>`).join('');
  let h=`<button class="pb" onclick="goPG(1)" ${PG==1?'disabled':''}>«</button><button class="pb" onclick="goPG(${PG-1})" ${PG==1?'disabled':''}>‹</button>`;
  let start=Math.max(1,PG-2),end=Math.min(total,start+4);if(end-start<4)start=Math.max(1,end-4);
  for(let i=start;i<=end;i++)h+=`<button class="pb ${i==PG?'active':''}" onclick="goPG(${i})">${i}</button>`;
  h+=`<button class="pb" onclick="goPG(${PG+1})" ${PG==total?'disabled':''}>›</button><button class="pb" onclick="goPG(${total})" ${PG==total?'disabled':''}>»</button>`;
  document.getElementById('pag-controls').innerHTML=FILT.length?h:`ไม่พบข้อมูล`;
}
function goPG(p){PG=p;renderList();window.scrollTo(0,0);}
function renderDashCharts(){
  const mCnt=countBy(ALL,r=>monthKey(r.date)),mKeys=Object.keys(mCnt).sort();
  destroyChart('trend');charts['trend']=new Chart(document.getElementById('c-trend'),{type:'line',data:{labels:mKeys.map(monthLabel),datasets:[{label:'จำนวน',data:mKeys.map(k=>mCnt[k]),borderColor:'#2563eb',fill:true,backgroundColor:'rgba(37,99,235,.1)',tension:0.3}]},options:{maintainAspectRatio:false}});
  const sCnt={0:0,1:0,3:0,5:0};ALL.forEach(r=>{if(r.status in sCnt)sCnt[r.status]++});
  destroyChart('status');charts['status']=new Chart(document.getElementById('c-status'),{type:'doughnut',data:{labels:['รับเรื่อง','ระหว่างดำเนินการ','เสร็จสิ้น','ยกเลิก'],datasets:[{data:[sCnt[0],sCnt[1],sCnt[3],sCnt[5]],backgroundColor:['#6366f1','#f59e0b','#22c55e','#9ca3af']}]},options:{maintainAspectRatio:false,plugins:{legend:{position:'right'}}}});
  const tCnt=countBy(ALL,r=>r.topic),tTop=Object.entries(tCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('topic');charts['topic']=new Chart(document.getElementById('c-topic'),{type:'bar',data:{labels:tTop.map(e=>e[0]),datasets:[{data:tTop.map(e=>e[1]),backgroundColor:COLORS}]},options:{indexAxis:'y',maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const dCnt=countBy(ALL,r=>r.dept),dTop=Object.entries(dCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('dept');charts['dept']=new Chart(document.getElementById('c-dept'),{type:'bar',data:{labels:dTop.map(e=>e[0]),datasets:[{data:dTop.map(e=>e[1]),backgroundColor:COLORS}]},options:{indexAxis:'y',maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const srcCnt=countBy(ALL,r=>getSrcName(r.src)),srcE=Object.entries(srcCnt).sort((a,b)=>b[1]-a[1]);
  destroyChart('src');charts['src']=new Chart(document.getElementById('c-src'),{type:'doughnut',data:{labels:srcE.map(e=>e[0]),datasets:[{data:srcE.map(e=>e[1]),backgroundColor:COLORS}]},options:{maintainAspectRatio:false,plugins:{legend:{position:'right'}}}});
  const now=Date.now(),day=86400000,dMap={};
  for(let i=29;i>=0;i--){const k=new Date(now-i*day).toISOString().slice(0,10);dMap[k]=0;}
  ALL.forEach(r=>{if(r.date){const k=new Date(r.date).toISOString().slice(0,10);if(k in dMap)dMap[k]++;}});
  destroyChart('daily');charts['daily']=new Chart(document.getElementById('c-daily'),{type:'bar',data:{labels:Object.keys(dMap).map(k=>k.split('-').slice(1).reverse().join('/')),datasets:[{label:'จำนวน',data:Object.values(dMap),backgroundColor:'rgba(37,99,235,.6)',borderRadius:3}]},options:{maintainAspectRatio:false,plugins:{legend:{display:false}}}});
}
function populateMonthFilter(){
  const s=document.getElementById('sel-month'),mths=[...new Set(ALL.map(r=>monthKey(r.date)).filter(Boolean))].sort();
  s.innerHTML='<option value="">-- ทุกเดือน --</option>';mths.forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=monthLabel(k);s.appendChild(o);});
  if(mths.length > 0) s.value = mths[mths.length - 1];
  const ds=document.getElementById('sel-mdept'),depts=[...new Set(ALL.map(r=>r.dept))].sort();
  ds.innerHTML='<option value="">ทุกหน่วยงาน</option>';depts.forEach(d=>{const o=document.createElement('option');o.value=d;o.textContent=d;ds.appendChild(o);});
  const lds=document.getElementById('fl-dept');
  if(lds){lds.innerHTML='<option value="">ทุกหน่วยงาน</option>';depts.forEach(d=>{const o=document.createElement('option');o.value=d;o.textContent=d;lds.appendChild(o);});}
  const lsrc=document.getElementById('fl-src');
  if(lsrc){
    const srcs=[...new Set(ALL.map(r=>r.src))].sort();
    lsrc.innerHTML='<option value="">ทุกช่องทาง</option>';
    srcs.forEach(v=>{const o=document.createElement('option');o.value=v;o.textContent=getSrcName(v);lsrc.appendChild(o);});
  }
}
function renderMonthly(){
  const selM=document.getElementById('sel-month').value,selD=document.getElementById('sel-mdept').value;
  let data=ALL; if(selD) data=data.filter(r=>r.dept===selD);
  const months=[...new Set(ALL.map(r=>monthKey(r.date)).filter(Boolean))].sort();
  let mData=selM? data.filter(r=>monthKey(r.date)===selM) : data;
  const done=mData.filter(r=>r.status===3).length,proc=mData.filter(r=>r.status===1).length,wait=mData.filter(r=>r.status===0).length,od=mData.filter(r=>r.od>0).length;
  const successRate = mData.length ? Math.round((done / mData.length) * 100) : 0;
  document.getElementById('m-met').innerHTML=`<div class="m"><div class="ml">ทั้งหมด</div><div class="mv" style="color:#2563eb">${mData.length.toLocaleString()}</div></div><div class="m"><div class="ml">เสร็จสิ้น</div><div class="mv" style="color:#16a34a">${done.toLocaleString()}</div></div><div class="m"><div class="ml">ระหว่างดำเนินการ</div><div class="mv" style="color:#d97706">${proc.toLocaleString()}</div></div><div class="m"><div class="ml">รับเรื่อง</div><div class="mv" style="color:#6366f1">${wait.toLocaleString()}</div></div><div class="m"><div class="ml">อัตราสำเร็จ</div><div class="mv" style="color:#16a34a">${successRate}%</div></div><div class="m"><div class="ml">เกินกำหนด</div><div class="mv" style="color:#dc2626">${od.toLocaleString()}</div></div>`;
  const mCount=countBy(data,r=>monthKey(r.date));
  destroyChart('mbar');charts['mbar']=new Chart(document.getElementById('c-mbar'),{type:'bar',data:{labels:months.map(monthLabel),datasets:[{label:'จำนวน',data:months.map(k=>mCount[k]||0),backgroundColor:months.map(k=>k==selM?'#2563eb':'rgba(37,99,235,0.4)')}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const s3=months.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===3).length),s1=months.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===1).length),s0=months.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===0).length),s5=months.map(k=>data.filter(r=>monthKey(r.date)===k&&r.status===5).length);
  destroyChart('mstack');charts['mstack']=new Chart(document.getElementById('c-mstack'),{type:'bar',data:{labels:months.map(monthLabel),datasets:[{label:'เสร็จสิ้น',data:s3,backgroundColor:'#22c55e'},{label:'ระหว่างดำเนินการ',data:s1,backgroundColor:'#f59e0b'},{label:'รับเรื่อง',data:s0,backgroundColor:'#6366f1'},{label:'ยกเลิก',data:s5,backgroundColor:'#9ca3af'}]},options:{responsive:true,maintainAspectRatio:false,scales:{x:{stacked:true},y:{stacked:true}}}});
  const tCnt=countBy(mData,r=>r.topic),tTop=Object.entries(tCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('mtopic');charts['mtopic']=new Chart(document.getElementById('c-mtopic'),{type:'bar',data:{labels:tTop.map(e=>e[0]),datasets:[{data:tTop.map(e=>e[1]),backgroundColor:COLORS}]},options:{indexAxis:'y',maintainAspectRatio:false,plugins:{legend:{display:false}}}});
  const dCnt=countBy(mData,r=>r.dept),dTop=Object.entries(dCnt).sort((a,b)=>b[1]-a[1]).slice(0,10);
  destroyChart('mdept');charts['mdept']=new Chart(document.getElementById('c-mdept'),{type:'bar',data:{labels:dTop.map(e=>e[0]),datasets:[{data:dTop.map(e=>e[1]),backgroundColor:COLORS}]},options:{indexAxis:'y',maintainAspectRatio:false,plugins:{legend:{display:false}}}});
}
loadData();
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        parsed = urlparse(self.path); qs = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/data":
            try:
                data, ts = get_data(force="force" in qs)
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                self.wfile.write(json.dumps({"data": data, "ts": ts}).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(json.dumps({"error": str(e)}).encode())
        else: self.send_response(404); self.end_headers()

def main():
    print(f"Server starting on port {PORT}..."); threading.Thread(target=background_refresh, daemon=True).start()
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()

if __name__ == "__main__":
    main()
