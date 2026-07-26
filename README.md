# FiveM Farming Macro

มาโครฟาร์มแบบ Background สำหรับ FiveM ความละเอียดภายในเกม 1600×900

## ติดตั้งเครื่องฟาร์ม

1. ดาวน์โหลด `FiveM-Farming-Launcher.exe` จากหน้า Releases
2. วางไว้บน Desktop แล้วเปิดไฟล์
3. Launcher จะบังคับตรวจสอบ GitHub ดาวน์โหลดเวอร์ชันล่าสุด ตรวจ SHA-256 และเปิดมาโคร
4. ไฟล์โปรแกรมจริงติดตั้งที่ `%LOCALAPPDATA%\FiveM-Farming`

ต้องตั้ง FiveM เป็น Windowed Borderless 1600×900 และ Windows Display Scale 100%

## ออกอัปเดตใหม่

1. แก้ `gui_macro.py`, `config.json` หรือรูปใน `templates_b64`
2. เปลี่ยนเลขใน `version.json` เช่น `1.0.0` เป็น `1.0.1` เป็นขั้นตอนสุดท้าย
3. GitHub Actions จะสร้าง Release ใหม่ให้อัตโนมัติ
4. ครั้งถัดไปที่ Launcher บนเครื่องฟาร์มถูกเปิด จะบังคับอัปเดตก่อนเปิดมาโคร

## กฎการอัปเดต

Launcher ไม่เปิดมาโครเวอร์ชันเก่าหากเช็ก GitHub ดาวน์โหลดแพ็กเกจ หรือตรวจ SHA-256 ไม่สำเร็จ เพื่อให้เครื่องฟาร์มทุกเครื่องใช้เวอร์ชันเดียวกัน
