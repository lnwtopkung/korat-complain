# Complain Dashboard — Korat City Municipal 📊

Dashboard แสดงข้อมูลการร้องเรียนแบบ Real-time ดึงข้อมูลผ่าน API โดยตรง มีระบบแสดงผลแบบกราฟ (Chart.js) และตารางข้อมูลที่ค้นหาได้

## 🚀 วิธีเริ่มใช้งาน
1.  ติดตั้ง Python 3.x
2.  ติดตั้งไลบรารีที่จำเป็น:
    ```bash
    pip install requests
    ```
3.  รันเซิร์ฟเวอร์:
    ```bash
    python complain_server.py
    ```
4.  เปิดเบราว์เซอร์ไปที่: `http://localhost:8765`

## ✨ ฟีเจอร์หลัก
*   **Performance:** ดึงข้อมูลรวดเร็วด้วยการเรียก API แบบ Batch (100 items/call)
*   **Caching:** มีระบบ Cache ข้อมูลในหน่วยความจำ อัปเดตทุก 3 ชั่วโมง
*   **Visualization:** แสดงแนวโน้มสถานะการร้องเรียน, หัวข้อที่พบมากที่สุด และหน่วยงานรับผิดชอบ
*   **Filtering:** ค้นหาข้อมูลตามสถานะ หน่วยงาน และหัวข้อได้แบบละเอียด

## ⚠️ ความปลอดภัย
ค่า Token ปัจจุบันถูก Hardcoded ไว้ในไฟล์ หากต้องการเปลี่ยนสามารถตั้งค่าผ่าน Environment Variables ได้:
*   `COMPLAIN_TOKEN`: สำหรับ API Token
*   `PORT`: พอร์ตสำหรับรันเซิร์ฟเวอร์ (ค่าเริ่มต้น 8765)
