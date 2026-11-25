"""إعدادات السيرفر + قراءة ملف .env (بدون مكتبات إضافية)."""
import os, sys, secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT = BACKEND_DIR.parent
ML_DIR = ROOT / "ml"
FRONTEND_DIR = ROOT / "frontend"

_env = BACKEND_DIR / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

DB_PATH = os.environ.get("HOMEOPS_DB", str(BACKEND_DIR / "homeops.db"))
DEV_OTP = os.environ.get("HOMEOPS_DEV_OTP", "1") == "1"
SEED_EMAIL = os.environ.get("HOMEOPS_SEED_EMAIL", "").strip().lower()
SEED_PASSWORD = os.environ.get("HOMEOPS_SEED_PASSWORD", "")
SEED_ACCOUNTS = [("admin", "الأدمن"), ("finance", "المحاسب"), ("call", "موظف الكول سنتر"), ("tech", "فني (حساب تجريبي)")]


def _secret() -> str:
    s = os.environ.get("HOMEOPS_SECRET", "").strip()
    if s:
        return s
    f = BACKEND_DIR / ".secret"          # مفتاح بيتحفظ عشان الجلسات ما تموتش مع كل إعادة تشغيل
    try:
        if f.exists() and f.read_text().strip():
            return f.read_text().strip()
        s = secrets.token_hex(32)
        f.write_text(s)
        return s
    except OSError:
        return secrets.token_hex(32)


SECRET = _secret()

if str(ML_DIR) not in sys.path:          # predictor.py بيعمل import لـ common
    sys.path.insert(0, str(ML_DIR))
