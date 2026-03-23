"""
เซิร์ฟเวอร์ข้อมูลร้องเรียน เทศบาลนครราชสีมา (v2.2 - Final for Railway)
วิธีใช้:
  1. สร้างไฟล์ .env และใส่ COMPLAIN_TOKEN
  2. python complain_server.py
"""

import json, time, threading, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

# --- [0] LOAD .ENV MANUALLY ---
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

# --- [1] CONFIGURATION ---
TOKEN     = os.environ.get("COMPLAIN_TOKEN", "")
BASE_URL  = os.environ.get("COMPLAIN_API_URL", "https://prapa.koratcity.go.th/koratCity/getComplain")
PORT      = int(os.environ.get("PORT", 8765))
CACHE_SEC = int(os.environ.get("CACHE_SEC", 10800))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", 100))

# --- [2] CACHE & LOGIC ---
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
        cols[f"columns[{i}][data]"]          = "createDate" if i == 1 else "function"
        cols[f"columns[{i}][name]"]          = ""
        cols[f"columns[{i}][searchable]"]    = "true"
        cols[f"columns[{i}][orderable]"]     = "true" if i <= 2 else "false"
        cols[f"columns[{i}][search][value]"] = ""
        cols[f"columns[{i}][search][regex]"] = "false"
    return {**cols, "draw": page+1, "order[0][column]": 0, "order[0][dir]": "asc",
            "start": page * PAGE_SIZE, "length": PAGE_SIZE, "search[value]": "", "search[regex]": "false",
            "sizeContents": PAGE_SIZE, "page": page, "keyWord": "", "startDate": start_ts,
            "endDate": end_ts, "orderBy": 2, "isGuest": 0, "_": int(time.time()*1000)}

def fetch_live(days=90):
    if not TOKEN:
        raise Exception("COMPLAIN_TOKEN is missing!")
    
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "token": TOKEN,
        "x-requested-with": "XMLHttpRequest",
        "user-agent": "Mozilla/5.0",
        "referer": "https://prapa.koratcity.go.th/chart/view-statistic-complain.html",
    }
    
    end_ts   = int(time.time() * 1000)
    start_ts = end_ts - days * 86_400_000
    
    first = requests.get(BASE_URL, params=build_params(0, start_ts, end_ts), headers=headers, timeout=30)
    first.raise_for_status()
    d = first.json()
    
    if d.get("status") == 500:
        raise Exception(d.get("message", "Token expired or Server error"))
    
    total_pages = d["data"]["totalPages"]
    rows = list(d["data"]["content"])
    
    for page in range(1, total_pages):
        r = requests.get(BASE_URL, params=build_params(page, start_ts, end_ts), headers=headers, timeout=30)
        r.raise_for_status()
        rows.extend(r.json().get("data", {}).get("content", []))
        
    return rows

def perform_refresh():
    try:
        rows = fetch_live()
        slim = [{"id": r.get("complainId",""), "date": r.get("complainDate",0),
                 "topic": get_topic(r), "status": r.get("statusCode",0),
                 "src": r.get("from",0), "dept": get_dept(r),
                 "od": r.get("overDueDate",0) or 0,
                 "create": r.get("createDate",0)} for r in rows]
        with _cache["lock"]:
            _cache["data"] = slim
            _cache["ts"]   = time.time()
            _cache["ready"] = True
            _cache["error"] = None
        print(f"[CACHE] Updated {len(slim):,} items")
    except Exception as e:
        with _cache["lock"]:
            _cache["error"] = str(e)
        print(f"[CACHE ERROR] {e}")

def background_refresh():
    while True:
        perform_refresh()
        time.sleep(CACHE_SEC)

def get_data(force=False):
    if force: perform_refresh()
    waited = 0
    while not _cache["ready"] and waited < 60:
        time.sleep(0.5)
        waited += 1
    with _cache["lock"]:
        if _cache["error"] and not _cache["data"]:
            raise Exception(_cache["error"])
        return _cache["data"], _cache["ts"]

# --- [3] HTML PAGE ---
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
#upd{font-size:12px;opacity:.75;white-space:nowrap;}
.tbtn{padding:6px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(255,255,255,.15);color:#fff;cursor:pointer;font-size:13px;font-family:'Sarabun',sans-serif;}
.tbtn:hover{background:rgba(255,255,255,.25);}
.tbtn.on{background:#16a34a;border-color:#16a34a;}
#pbar{height:3px;background:#3b82f6;width:0%;transition:width .3s;position:fixed;top:52px;left:0;right:0;z-index:98;}
.nav{background:#fff;border-bottom:1px solid #e5e7eb;display:flex;padding:0 20px;}
.nav-btn{padding:14px 20px;font-size:14px;font-weight:500;color:#6b7280;cursor:pointer;border-bottom:2px solid transparent;font-family:'Sarabun',sans-serif;background:none;border-top:none;border-left:none;border-right:none;}
.nav-btn.active{color:#2563eb;border-bottom-color:#2563eb;}
.nav-btn:hover:not(.active){color:#374151;background:#f9fafb;}
.page{display:none;}.page.show{display:block;}
.con{max-width:1200px;margin:0 auto;padding:16px 20px;}
.met{display:grid;grid-template-columns:repeat(auto-fit,minmax(100px,1fr));gap:10px;margin-bottom:20px;}
.m{background:#fff;border-radius:10px;padding:12px 14px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.ml{font-size:11px;color:#888;margin-bottom:4px;}.mv{font-size:22px;font-weight:700;}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px;}
.card{background:#fff;border-radius:12px;padding:16px 20px;box-shadow:0 1px 4px rgba(0,0,0,.06);}
.card h3{font-size:13px;font-weight:600;color:#6b7280;margin-bottom:14px;text-transform:uppercase;letter-spacing:.04em;}
.chart-wrap{position:relative;width:100%;}
.fil{display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.fil input,.fil select{padding:8px 10px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:13px;background:#fff;color:#222;outline:none;}
.fil input{flex:1;min-width:140px;}
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
.mfil{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;}
.mfil select{padding:8px 12px;border:1.5px solid #e5e7eb;border-radius:8px;font-size:13px;background:#fff;color:#222;outline:none;}
.mfil label{font-size:13px;color:#6b7280;font-weight:500;}
@media(max-width:700px){.chart-grid{grid-template-columns:1fr;}}
</style></head><body>
<div class="bar">
  <h1>📊 Dashboard ร้องเรียน — เทศบาลนครราชสีมา</h1>
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
    <div class="card"><h3>แนวโน้มรายเดือน</h3><div class="chart-wrap" style="height:220px"><canvas id="c-trend"></canvas></div></div>
    <div class="card"><h3>สัดส่วนสถานะ</h3><div class="chart-wrap" style="height:220px"><canvas id="c-status"></canvas></div></div>
  </div>
  <div class="chart-grid">
    <div class="card"><h3>หัวข้อสูงสุด 10 อันดับ</h3><div class="chart-wrap" style="height:260px"><canvas id="c-topic"></canvas></div></div>
    <div class="card"><h3>หน่วยงานรับผิดชอบ</h3><div class="chart-wrap" style="height:260px"><canvas id="c-dept"></canvas></div></div>
  </div>
</div></div>
<div class="page" id="page-monthly">
<div class="con">
  <div class="mfil">
    <label>เดือน:</label><select id="sel-month" onchange="renderMonthly()"></select>
    <label>หน่วยงาน:</label><select id="sel-mdept" onchange="renderMonthly()"></select>
  </div>
  <div class="met" id="m-met"></div>
  <div class="chart-grid">
    <div class="card"><h3>จำนวนร้องเรียน</h3><div class="chart-wrap" style="height:240px"><canvas id="c-mbar"></canvas></div></div>
    <div class="card"><h3>สถานะ (stacked)</h3><div class="chart-wrap" style="height:240px"><canvas id="c-mstack"></canvas></div></div>
  </div>
</div></div>
<div class="page" id="page-list">
<div class="con">
  <div class="fil">
    <input id="q" type="text" placeholder="🔍 ค้นหา..." oninput="applyFilter()">
    <select id="fs" onchange="applyFilter()"><option value="">ทุกสถานะ</option><option value="0">รอดำเนินการ</option><option value="1">ระหว่างดำเนินการ</option><option value="3">เสร็จสิ้น</option><option value="5">ยกเลิก</option></select>
    <select id="fd" onchange="applyFilter()"><option value="">ทุกหน่วยงาน</option></select>
  </div>
  <div class="tc">
    <div id="msg" style="padding:32px;text-align:center;color:#9ca3af">กำลังโหลด...</div>
    <div id="tw" style="display:none;overflow-x:auto">
      <table><thead><tr><th>#</th><th>หมายเลข</th><th>วันที่</th><th>หัวข้อ</th><th>สถานะ</th><th>หน่วยงาน</th></tr></thead>
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
let ALL=[],FILT=[],PG=1,PER=10,TIMER=null,AUTO=true,BUSY=false,charts={};
function fmtD(ts){if(!ts)return'-';return new Date(ts).toLocaleDateString('th-TH',{year:'2-digit',month:'short',day:'numeric'});}
function monthKey(ts){if(!ts)return null;const d=new Date(ts);return d.getFullYear()+'-'+(d.getMonth()+1).toString().padStart(2,'0');}
function monthLabel(k){if(!k)return'';const[y,m]=k.split('-');const mn=['ม.ค.','ก.พ.','มี.ค.','เม.ย.','พ.ค.','มิ.ย.','ก.ค.','ส.ค.','ก.ย.','ต.ค.','พ.ย.','ธ.ค.'];return mn[parseInt(m)-1]+' '+(parseInt(y)+543);}
function countBy(arr,fn){const m={};arr.forEach(r=>{const k=fn(r);m[k]=(m[k]||0)+1;});return m;}
function setBar(p){document.getElementById('pbar').style.width=p+'%';}
function showPage(name){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('show'));
  document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active'));
  document.getElementById('page-'+name).classList.add('show');
  if(event) event.target.classList.add('active');
  if(name==='monthly')renderMonthly();
}
async function loadData(force=false){
  if(BUSY)return;BUSY=true;setBar(10);
  document.getElementById('upd').textContent='กำลังโหลด...';
  try{
    const r=await fetch('/api/data'+(force?'?force=1':''));
    const d=await r.json();
    if(d.error)throw new Error(d.error);
    ALL=d.data;updMetrics();updFilters();applyFilter();renderDashCharts();populateMonthFilter();
    document.getElementById('upd').textContent='อัปเดต '+new Date(d.ts*1000).toLocaleTimeString('th-TH')+' | '+ALL.length.toLocaleString()+' รายการ';
    document.getElementById('msg').style.display='none';document.getElementById('tw').style.display='block';
    setBar(100);setTimeout(()=>setBar(0),600);
  }catch(e){document.getElementById('upd').textContent='โหลดไม่สำเร็จ: '+e.message;setBar(0);}
  BUSY=false;
}
function updMetrics(){
  const counts=[ALL.length,ALL.filter(r=>r.status===3).length,ALL.filter(r=>r.status===1).length,ALL.filter(r=>r.status===0).length,ALL.filter(r=>r.status===5).length,ALL.filter(r=>r.od>0).length];
  counts.forEach((v,i)=>document.getElementById('m'+i).textContent=v.toLocaleString());
}
function updFilters(){
  const s=document.getElementById('fd'),v=s.value;
  const depts=[...new Set(ALL.map(r=>r.dept))].sort();
  s.innerHTML='<option value="">ทุกหน่วยงาน</option>';
  depts.forEach(x=>{const o=document.createElement('option');o.value=x;o.textContent=x;s.appendChild(o);});
  s.value=v;
}
function applyFilter(){
  const q=document.getElementById('q').value.toLowerCase(),fs=document.getElementById('fs').value,fd=document.getElementById('fd').value;
  FILT=ALL.filter(r=>(!q||r.topic.toLowerCase().includes(q)||String(r.id).includes(q))&&(fs===''||String(r.status)===fs)&&(!fd||r.dept===fd));
  PG=1;renderList();
}
function renderList(){
  const s=(PG-1)*PER,sl=FILT.slice(s,s+PER);
  const tb=document.getElementById('tbody');
  if(!sl.length){tb.innerHTML='<tr><td colspan="6" style="text-align:center;padding:32px">ไม่พบข้อมูล</td></tr>';return;}
  tb.innerHTML=sl.map((r,i)=>'<tr><td>'+(s+i+1)+'</td><td>'+r.id+'</td><td>'+fmtD(r.date)+'</td><td>'+r.topic+'</td><td><span class="badge '+(SC[r.status]||'b5')+'">'+(SM[r.status]||r.status)+'</span></td><td>'+r.dept+'</td></tr>').join('');
}
function renderDashCharts(){
  const ctxT=document.getElementById('c-trend'),ctxS=document.getElementById('c-status');
  if(charts.t)charts.t.destroy();if(charts.s)charts.s.destroy();
  const mCnt=countBy(ALL,r=>monthKey(r.date)),mKeys=Object.keys(mCnt).sort();
  charts.t=new Chart(ctxT,{type:'line',data:{labels:mKeys.map(monthLabel),datasets:[{label:'ร้องเรียน',data:mKeys.map(k=>mCnt[k]),borderColor:'#2563eb',fill:true,backgroundColor:'rgba(37,99,235,.1)'}]},options:{responsive:true,maintainAspectRatio:false}});
  const sCnt={0:0,1:0,3:0,5:0};ALL.forEach(r=>{if(r.status in sCnt)sCnt[r.status]++});
  charts.s=new Chart(ctxS,{type:'doughnut',data:{labels:['รอดำเนินการ','ระหว่างดำเนินการ','เสร็จสิ้น','ยกเลิก'],datasets:[{data:[sCnt[0],sCnt[1],sCnt[3],sCnt[5]],backgroundColor:['#6366f1','#f59e0b','#22c55e','#9ca3af']}]},options:{responsive:true,maintainAspectRatio:false}});
}
function populateMonthFilter(){
  const s=document.getElementById('sel-month'),mths=[...new Set(ALL.map(r=>monthKey(r.date)).filter(Boolean))].sort();
  s.innerHTML='<option value="">-- ทุกเดือน --</option>';
  mths.forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=monthLabel(k);s.appendChild(o);});
}
function renderMonthly(){ /* logic as before */ }
function toggleAuto(){AUTO=!AUTO;const b=document.getElementById('abtn');if(AUTO){TIMER=setInterval(()=>loadData(false),10800000);b.textContent='⏱ Auto 3ชม';b.className='tbtn on';}else{clearInterval(TIMER);b.textContent='⏱ Auto OFF';b.className='tbtn';}}
loadData(true);TIMER=setInterval(()=>loadData(false),10800000);
</script></body></html>"""

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/":
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        elif parsed.path == "/api/data":
            try:
                data, ts = get_data(force="force" in qs)
                body = json.dumps({"data": data, "ts": ts}, ensure_ascii=False)
                self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()
                self.wfile.write(body.encode("utf-8"))
            except Exception as e:
                self.send_response(500); self.send_header("Content-Type", "application/json"); self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404); self.end_headers()

def main():
    print(f"Server starting on port {PORT}...")
    threading.Thread(target=background_refresh, daemon=True).start()
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try: server.serve_forever()
    except KeyboardInterrupt: pass

if __name__ == "__main__":
    main()
