"""
เซิร์ฟเวอร์ข้อมูลร้องเรียน เทศบาลนครราชสีมา (v2.1 - .env support)
วิธีใช้:
  1. สร้างไฟล์ .env และใส่ COMPLAIN_TOKEN
  2. python complain_server.py
"""

import json, time, threading, os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests

# --- [0] LOAD .ENV MANUALLY (Simple) ---
def load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    key, val = line.strip().split("=", 1)
                    os.environ[key] = val.strip('"').strip("'")

load_dotenv() # โหลดค่าจาก .env เข้า os.environ

# --- [1] CONFIGURATION ---
TOKEN     = os.environ.get("COMPLAIN_TOKEN", "")
BASE_URL  = os.environ.get("COMPLAIN_API_URL", "https://prapa.koratcity.go.th/koratCity/getComplain")
PORT      = int(os.environ.get("PORT", 8765))
CACHE_SEC = int(os.environ.get("CACHE_SEC", 10800))
PAGE_SIZE = int(os.environ.get("PAGE_SIZE", 100))

if not TOKEN:
    print("❌ ERROR: ไม่พบ COMPLAIN_TOKEN ในไฟล์ .env หรือ Environment Variables!")
    # ให้ใส่ Token สำรองกรณีต้องการรันแบบด่วน
    # TOKEN = "..." 

HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "token": TOKEN,
    "x-requested-with": "XMLHttpRequest",
    "user-agent": "Mozilla/5.0",
    "referer": "https://prapa.koratcity.go.th/chart/view-statistic-complain.html",
}

_cache = {"data": [], "ts": 0, "lock": threading.Lock(), "ready": False, "error": None}

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
        print(f"[CACHE] อัปเดตสำเร็จ {len(slim):,} รายการ")
        return True
    except Exception as e:
        err_msg = str(e)
        with _cache["lock"]:
            _cache["error"] = err_msg
        print(f"[CACHE ERROR] {err_msg}")
        return False

def background_refresh():
    while True:
        perform_refresh()
        time.sleep(CACHE_SEC)

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
    print(f"[API] กำลังดึงข้อมูล (ครั้งละ {PAGE_SIZE} รายการ)...")
    
    first = requests.get(BASE_URL, params=build_params(0, start_ts, end_ts), headers=HEADERS, timeout=30)
    first.raise_for_status()
    d = first.json()
    
    if d.get("status") == 500:
        raise Exception(d.get("message", "Token หมดอายุ หรือเซิร์ฟเวอร์ปลายทางขัดข้อง"))
    
    total_pages = d["data"]["totalPages"]
    total_el    = d["data"]["totalElements"]
    rows = list(d["data"]["content"])
    
    print(f"[API] พบข้อมูลทั้งหมด {total_el:,} รายการ ({total_pages} หน้า)")
    
    for page in range(1, total_pages):
        r = requests.get(BASE_URL, params=build_params(page, start_ts, end_ts), headers=HEADERS, timeout=30)
        r.raise_for_status()
        res_data = r.json()
        content = res_data.get("data", {}).get("content", [])
        rows.extend(content)
        if page % 5 == 0 or page == total_pages - 1:
            print(f"[API]   ดึงแล้ว {len(rows):,}/{total_el:,} ...")
            
    print(f"[API] สำเร็จ: {len(rows):,} รายการ")
    return rows

def get_data(force=False):
    if force:
        print("[API] กำลังรีเฟรชข้อมูลตามคำขอ (Force Refresh)...")
        perform_refresh()
    
    waited = 0
    while not _cache["ready"] and waited < 60:
        time.sleep(0.5)
        waited += 1
        
    with _cache["lock"]:
        if _cache["error"] and not _cache["data"]:
            raise Exception(_cache["error"])
        return _cache["data"], _cache["ts"]

# --- HTML_PAGE (Same as before) ---
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="th"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dashboard ร้องเรียน — เทศบาลนครราชสีมา</title>
<link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@400;500;600;700&display=swap" rel="stylesheet">
... (rest of HTML) ...
"""

# ... (rest of the server code same as before) ...

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
    print("=" * 60)
    print("  Dashboard ร้องเรียน เทศบาลนครราชสีมา (v2.1 .env Support)")
    print("=" * 60)
    print(f"  Port: {PORT}")
    print(f"  Page Size: {PAGE_SIZE} items/call")
    print("-" * 60)
    
    t = threading.Thread(target=background_refresh, daemon=True)
    t.start()
    
    waited = 0
    while not _cache["ready"] and waited < 30:
        time.sleep(1)
        waited += 1
        if waited % 5 == 0:
            print(f"  รอข้อมูลเบื้องต้น... {waited}s")
            
    print(f"\n  เปิดเบราว์เซอร์: http://localhost:{PORT}")
    print(f"  กด Ctrl+C เพื่อหยุด")
    print("=" * 60)
    
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nหยุดการทำงานเรียบร้อย")

if __name__ == "__main__":
    main()
