# speckle_arc

โปรเจกต์ตั้งต้นสำหรับพัฒนา `speckle_arc`

## สิ่งที่มีในโครงนี้

- โครงสร้างแบบ `src/`
- แพ็กเกจ Python เริ่มต้น
- จุดเริ่มต้นสำหรับ CLI
- โฟลเดอร์ `tests/` สำหรับขยายการทดสอบ
- `.gitignore` สำหรับงาน Python ทั่วไป

## โครงสร้างไฟล์

```text
speckle_arc/
|- src/
|  \- speckle_arc/
|     |- __init__.py
|     \- main.py
|- tests/
|  \- __init__.py
|- .gitignore
|- pyproject.toml
|\- README.md
```

## เริ่มต้นใช้งาน

1. สร้าง virtual environment
2. ติดตั้งโปรเจกต์แบบ editable
3. รันคำสั่งตัวอย่าง

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
speckle-arc
```

หรือรันผ่านโมดูลโดยตรง

```powershell
python -m speckle_arc.main
```

## สิ่งที่ควรทำต่อ

- เพิ่ม dependencies ที่จำเป็นใน `pyproject.toml`
- เริ่มแยก logic จริงไว้ใน `src/speckle_arc/`
- เพิ่ม unit tests ใน `tests/`
- อัปเดต README ให้ตรงกับเป้าหมายของโปรเจกต์

## หมายเหตุ

ตอนนี้ repo ต้นทางยังเป็น repo ว่าง ผมจึงตั้งโครงเริ่มต้นแบบทั่วไปให้ก่อนเพื่อให้พัฒนาต่อได้ทันที
