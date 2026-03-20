# Dashboard ร้องเรียน

## วิธี Deploy บน Railway

1. สมัคร [railway.app](https://railway.app) ด้วย GitHub
2. กด **New Project** → **Deploy from GitHub repo**
3. เลือก repo ที่อัปโหลดไฟล์เหล่านี้
4. Railway จะ deploy อัตโนมัติ — ได้ URL ทันที

## ไฟล์ในโปรเจกต์

| ไฟล์ | หน้าที่ |
|------|---------|
| `complain_server.py` | Server หลัก |
| `requirements.txt` | Python packages |
| `Procfile` | คำสั่งรัน |

## รันบนเครื่องตัวเอง

```bash
pip install requests
python complain_server.py
```

เปิด http://localhost:8765
