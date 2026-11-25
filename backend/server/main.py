"""HomeOps backend: FastAPI + SQLite + JWT. الفرونت بيتخدم من نفس السيرفر."""
import json, re, time, secrets, logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, db as dbm, security as sec

log = logging.getLogger("homeops")

SERVICES = ["plumb", "elec", "paint", "ac", "carp", "appl"]
DEFAULT_ENABLED = {"plumb": 1, "elec": 1, "paint": 1, "ac": 0, "carp": 0, "appl": 0}
PRIOS = {"emerg", "urgent", "mid", "norm"}
SYMC = {"leak", "nowater", "gas", "burn", "spark", "nopower", "noise", "broken", "crack", "lock", "request"}
SAFETY = {"gas", "burn", "spark"}                     # غاز/حريق/شرر = طوارئ دايماً
PAYM = ["فيزا", "فودافون كاش", "إنستا باي"]
EXPK = ["وقود وانتقالات", "قطع غيار ومخزون", "رواتب إدارية", "تسويق", "أخرى"]
RESULTS = ["وافق", "رفض", "مفيش رد"]
ASSIGNABLE = ("قيد المراجعة", "تم الإسناد")
OPEN_ASSIGNED = ("تم الإسناد", "إتمام محتمل")
VAT = 0.14
DEFAULT_RATE = 60

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo("Africa/Cairo")
except Exception:                                      # ويندوز من غير tzdata
    TZ = timezone(timedelta(hours=2))


def now_ms() -> int:
    return int(time.time() * 1000)


def fmt(ms, with_time=True) -> str:
    d = datetime.fromtimestamp((ms or 0) / 1000, TZ)
    return d.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def bad(code, msg):
    return HTTPException(code, msg)


# ---------------------------------------------------------------- الموديل
_predict = None


def load_model():
    global _predict
    try:
        from predictor import predict
        _predict = predict
        log.info("triage model loaded")
    except Exception as e:                             # السيرفر يشتغل حتى لو الموديل وقع
        _predict = None
        log.warning("triage model NOT loaded: %s", e)


# ---------------------------------------------------------------- قاعدة البيانات
def get_db():
    conn = dbm.connect()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed(conn):
    conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('enabled',?)", (json.dumps(DEFAULT_ENABLED),))
    conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES('rate',?)", (str(DEFAULT_RATE),))
    for n in ("order", "ticket"):
        conn.execute("INSERT OR IGNORE INTO counters(name,val) VALUES(?,0)", (n,))
    if not config.SEED_EMAIL or not config.SEED_PASSWORD:
        log.warning("HOMEOPS_SEED_EMAIL / HOMEOPS_SEED_PASSWORD مش موجودين في .env — مفيش حسابات موظفين اتعملت")
    else:
        for role, name in config.SEED_ACCOUNTS:
            r = conn.execute("SELECT * FROM users WHERE email=? AND role=?", (config.SEED_EMAIL, role)).fetchone()
            if not r:
                conn.execute("INSERT INTO users(role,name,email,phone,pass_hash,active,seeded,created) VALUES(?,?,?,?,?,1,1,?)",
                             (role, name, config.SEED_EMAIL, "", sec.hash_password(config.SEED_PASSWORD), now_ms()))
            elif not sec.verify_password(config.SEED_PASSWORD, r["pass_hash"]):   # غيّرتي كلمة السر في .env
                conn.execute("UPDATE users SET pass_hash=?, active=1 WHERE id=?", (sec.hash_password(config.SEED_PASSWORD), r["id"]))
    conn.commit()


@asynccontextmanager
async def lifespan(app):
    conn = dbm.connect()
    dbm.init(conn)
    seed(conn)
    conn.close()
    load_model()
    yield


app = FastAPI(title="HomeOps", lifespan=lifespan)


@app.middleware("http")
async def headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- مساعدات
def jl(s, default):
    try:
        return json.loads(s) if s else default
    except Exception:
        return default


def counter(conn, name, prefix, base):
    conn.execute("UPDATE counters SET val=val+1 WHERE name=?", (name,))
    return f"{prefix}-{base + conn.execute('SELECT val FROM counters WHERE name=?', (name,)).fetchone()[0]}"


def audit(conn, u, action):
    actor = f"{u['name']} ({ROLE_AR[u['role']]})" if u else ""
    conn.execute("INSERT INTO audit(ts,actor,action) VALUES(?,?,?)", (now_ms(), actor, action))


ROLE_AR = {"customer": "عميل", "tech": "فني", "call": "كول سنتر", "finance": "مالي", "admin": "أدمن"}


def setting(conn, key, default=None):
    r = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def enabled_map(conn):
    m = dict(DEFAULT_ENABLED)
    m.update(jl(setting(conn, "enabled"), {}))
    return m


def rate(conn):
    try:
        return float(setting(conn, "rate", DEFAULT_RATE))
    except ValueError:
        return float(DEFAULT_RATE)


def ok(conn, **extra):
    conn.commit()
    return {"ok": True, **extra}


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^(\+?20|0)?1[0125]\d{8}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_password_rules(p: str):
    if len(p) < 8 or len(p) > 128 or not re.search(r"[A-Za-z]", p) or not re.search(r"\d", p) or not re.search(r"[^A-Za-z0-9]", p):
        raise bad(422, "كلمة المرور لازم 8 حروف على الأقل وفيها حرف ورقم ورمز خاص")


def clean(s, n, label, required=False):
    s = (s or "").strip()
    if required and not s:
        raise bad(422, f"{label} مطلوب")
    if len(s) > n:
        raise bad(422, f"{label} طويل زيادة عن اللزوم")
    return s


def user_out(r):
    return {"id": r["id"], "role": r["role"], "name": r["name"], "email": r["email"], "phone": r["phone"] or "",
            "lang": r["lang"], "addrs": jl(r["addrs"], []), "active": bool(r["active"]), "seeded": bool(r["seeded"])}


def order_out(r, role):
    d = {"id": r["id"], "email": r["email"], "svc": r["svc"], "pr": r["pr"], "place": r["place"] or "",
         "syms": jl(r["syms"], []), "desc": r["descr"] or "", "date": r["date"] or "", "slot": r["slot"] or "",
         "status": r["status"], "tech": r["tech"] or "", "files": r["files"], "created": fmt(r["created"], False),
         "ts": r["created"], "inv": jl(r["inv"], None), "paidOut": bool(r["paid_out"]), "paidOutAt": r["paid_out_at"]}
    if role == "customer":
        d["tech"] = ""
    return d


def ticket_out(r):
    return {"id": r["id"], "email": r["email"] or "", "from": r["from_name"] or "", "type": r["type"], "pr": r["pr"],
            "text": r["text"] or "", "ord": r["ord"] or "", "actions": jl(r["actions"], []), "status": r["status"],
            "ts": r["ts"], "created": fmt(r["ts"], False), "log": jl(r["log"], [])}


def tlog(conn, tid, action):
    r = conn.execute("SELECT log FROM tickets WHERE id=?", (tid,)).fetchone()
    L = jl(r["log"], [])
    L.append({"t": fmt(now_ms()), "a": action})
    conn.execute("UPDATE tickets SET log=? WHERE id=?", (json.dumps(L, ensure_ascii=False), tid))


# ---------------------------------------------------------------- الدخول والصلاحيات
def current(request: Request, conn=Depends(get_db)):
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise bad(401, "سجّل دخول الأول")
    try:
        p = sec.read_token(h[7:].strip())
        uid = int(p["sub"])
    except Exception:
        raise bad(401, "الجلسة انتهت، سجّل دخول تاني")
    r = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not r or not r["active"] or r["role"] != p.get("role"):
        raise bad(401, "الحساب غير متاح")
    return r


def need(*roles):
    def dep(u=Depends(current)):
        if u["role"] not in roles:
            raise bad(403, "مش مسموح لك بالإجراء ده")
        return u
    return dep


_fails = {}


def rl_check(key):
    c, until = _fails.get(key, (0, 0))
    if until > time.time():
        raise bad(429, "محاولات كتير غلط، استني 5 دقايق وجرّب تاني")


def rl_fail(key):
    c, _ = _fails.get(key, (0, 0))
    c += 1
    _fails[key] = (c, time.time() + 300 if c >= 5 else 0)
    if len(_fails) > 5000:
        _fails.clear()


def ip(request: Request):
    return request.client.host if request.client else "?"


class LoginIn(BaseModel):
    role: str
    email: str
    password: str


@app.post("/api/auth/login")
def login(b: LoginIn, request: Request, conn=Depends(get_db)):
    if b.role not in ROLE_AR:
        raise bad(422, "نوع الحساب غلط")
    email = b.email.strip().lower()
    key = f"{email}|{ip(request)}"
    rl_check(key)
    r = conn.execute("SELECT * FROM users WHERE email=? AND role=?", (email, b.role)).fetchone()
    good = sec.verify_password(b.password, r["pass_hash"] if r else "pbkdf2$1$00$00")
    if not r or not good or not r["active"]:
        rl_fail(key)
        raise bad(401, "البريد أو كلمة المرور غلط" if b.role == "customer" else "بيانات الدخول غلط أو الحساب موقوف")
    _fails.pop(key, None)
    audit(conn, r, "تسجيل دخول")
    conn.commit()
    return {"token": sec.make_token(r["id"], r["role"]), "user": user_out(r)}


class AddrIn(BaseModel):
    city: str = ""
    district: str = ""
    street: str = ""
    bld: str = ""
    floor: str = ""


class RegIn(BaseModel):
    name: str
    phone: str
    email: str
    password: str
    lang: str = "ar"
    addr: AddrIn


@app.post("/api/auth/register")
def register(b: RegIn, conn=Depends(get_db)):
    name = clean(b.name, 80, "الاسم", True)
    email = b.email.strip().lower()
    phone = b.phone.replace(" ", "")
    if not EMAIL_RE.match(email):
        raise bad(422, "البريد الإلكتروني مش صحيح")
    if not PHONE_RE.match(phone):
        raise bad(422, "رقم الموبايل مش صحيح")
    check_password_rules(b.password)
    a = {k: clean(getattr(b.addr, k), 120, "العنوان") for k in ("city", "district", "street", "bld", "floor")}
    if not a["street"] or not a["district"]:
        raise bad(422, "كمّل بيانات العنوان")
    if conn.execute("SELECT 1 FROM users WHERE email=? AND role='customer'", (email,)).fetchone():
        raise bad(409, "البريد ده مسجل قبل كده")
    cur = conn.execute("INSERT INTO users(role,name,email,phone,pass_hash,lang,addrs,created) VALUES('customer',?,?,?,?,?,?,?)",
                       (name, email, b.phone.strip(), sec.hash_password(b.password), "en" if b.lang == "en" else "ar",
                        json.dumps([a], ensure_ascii=False), now_ms()))
    r = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
    audit(conn, r, "إنشاء حساب عميل")
    conn.commit()
    return {"token": sec.make_token(r["id"], r["role"]), "user": user_out(r)}


class EmailIn(BaseModel):
    email: str


@app.post("/api/auth/forgot")
def forgot(b: EmailIn, request: Request, conn=Depends(get_db)):
    email = b.email.strip().lower()
    key = f"otp|{email}|{ip(request)}"
    rl_check(key)
    rl_fail(key)                              # أي طلب بيتحسب، 5 طلبات = استنى 5 دقايق
    if conn.execute("SELECT 1 FROM users WHERE email=? AND role='customer'", (email,)).fetchone():
        code = f"{secrets.randbelow(10000):04d}"
        conn.execute("INSERT OR REPLACE INTO otps(email,code_hash,expires,tries) VALUES(?,?,?,0)",
                     (email, sec.code_hash(email, code), int(time.time()) + 600))
        conn.commit()
        if config.DEV_OTP:
            print(f"\n[OTP] رمز استعادة كلمة المرور لـ {email}: {code}\n", flush=True)
    return {"ok": True}                      # نفس الرد سواء الإيميل موجود أو لأ


class ResetIn(BaseModel):
    email: str
    code: str
    password: str


@app.post("/api/auth/reset")
def reset(b: ResetIn, conn=Depends(get_db)):
    email = b.email.strip().lower()
    check_password_rules(b.password)
    o = conn.execute("SELECT * FROM otps WHERE email=?", (email,)).fetchone()
    if not o or o["expires"] < time.time() or o["tries"] >= 5:
        raise bad(400, "رمز التحقق غلط أو انتهت صلاحيته، اطلبي رمز جديد")
    if not secrets.compare_digest(o["code_hash"], sec.code_hash(email, b.code.strip())):
        conn.execute("UPDATE otps SET tries=tries+1 WHERE email=?", (email,))
        conn.commit()
        raise bad(400, "رمز التحقق غلط")
    r = conn.execute("SELECT * FROM users WHERE email=? AND role='customer'", (email,)).fetchone()
    if not r:
        raise bad(400, "رمز التحقق غلط")
    conn.execute("UPDATE users SET pass_hash=? WHERE id=?", (sec.hash_password(b.password), r["id"]))
    conn.execute("DELETE FROM otps WHERE email=?", (email,))
    audit(conn, r, "استعادة كلمة المرور")
    conn.commit()
    return {"token": sec.make_token(r["id"], r["role"]), "user": user_out(r)}


class MeIn(BaseModel):
    name: str
    phone: str = ""
    lang: str = "ar"


@app.put("/api/me")
def update_me(b: MeIn, u=Depends(current), conn=Depends(get_db)):
    name = clean(b.name, 80, "الاسم", True)
    phone = b.phone.strip()
    if u["role"] == "customer" and phone and not PHONE_RE.match(phone.replace(" ", "")):
        raise bad(422, "رقم الموبايل مش صحيح")
    conn.execute("UPDATE users SET name=?, phone=?, lang=? WHERE id=?", (name, phone, "en" if b.lang == "en" else "ar", u["id"]))
    conn.commit()
    return user_out(conn.execute("SELECT * FROM users WHERE id=?", (u["id"],)).fetchone())


# ---------------------------------------------------------------- الحالة (كل دور بيشوف الجزء بتاعه بس)
@app.get("/api/state")
def state(u=Depends(current), conn=Depends(get_db)):
    role = u["role"]
    q = lambda sql, *a: conn.execute(sql, a).fetchall()
    out = {"enabled": enabled_map(conn), "rate": rate(conn), "users": [], "orders": [], "tickets": [], "calls": [],
           "audit": [], "staff": [], "expenses": []}
    techs = [user_out(r) for r in q("SELECT * FROM users WHERE role='tech' ORDER BY id")]

    def customers(rows, full):
        res = []
        for r in rows:
            d = user_out(r)
            if not full:
                d = {"email": d["email"], "name": d["name"], "role": "customer", "phone": "", "addrs": [], "lang": "ar"}
            res.append(d)
        return res

    if role == "customer":
        out["users"] = [user_out(u)]
        out["orders"] = [order_out(r, role) for r in q("SELECT * FROM orders WHERE email=? ORDER BY created", u["email"])]
        out["tickets"] = [ticket_out(r) for r in q("SELECT * FROM tickets WHERE email=? ORDER BY ts", u["email"])]
    elif role == "tech":
        rows = q("SELECT * FROM orders WHERE tech=? ORDER BY created", u["email"])
        out["orders"] = [order_out(r, role) for r in rows]
        emails = list({r["email"] for r in rows})
        if emails:
            ph = ",".join("?" * len(emails))
            out["users"] = customers(q(f"SELECT * FROM users WHERE role='customer' AND email IN ({ph})", *emails), True)
        out["staff"] = [user_out(u)]
    elif role == "call":
        out["orders"] = [order_out(r, role) for r in q("SELECT * FROM orders ORDER BY created")]
        out["tickets"] = [ticket_out(r) for r in q("SELECT * FROM tickets ORDER BY ts")]
        out["calls"] = [{"ts": r["ts"], "dir": r["dir"], "who": r["who"], "note": r["note"], "out": r["outcome"]}
                        for r in q("SELECT * FROM calls ORDER BY ts")]
        out["users"] = customers(q("SELECT * FROM users WHERE role='customer' ORDER BY id"), True)
        out["staff"] = techs
    elif role == "finance":
        out["orders"] = [order_out(r, role) for r in q("SELECT * FROM orders WHERE inv IS NOT NULL ORDER BY created")]
        out["users"] = customers(q("SELECT * FROM users WHERE role='customer' ORDER BY id"), False)
        out["staff"] = techs
        out["expenses"] = [{"ts": r["ts"], "d": r["descr"], "amt": r["amt"], "k": r["kind"]} for r in q("SELECT * FROM expenses ORDER BY ts")]
    else:  # admin
        out["orders"] = [order_out(r, role) for r in q("SELECT * FROM orders ORDER BY created")]
        out["users"] = customers(q("SELECT * FROM users WHERE role='customer' ORDER BY id"), True)
        out["staff"] = [user_out(r) for r in q("SELECT * FROM users WHERE role!='customer' ORDER BY id")]
        out["audit"] = [{"a": r["action"], "u": r["actor"], "t": fmt(r["ts"])} for r in q("SELECT * FROM audit ORDER BY id DESC LIMIT 200")]
    return out


# ---------------------------------------------------------------- الموديل
class PredictIn(BaseModel):
    description: Optional[str] = ""
    location: Optional[str] = None
    symptoms: Optional[List[str]] = []
    onset: Optional[str] = None
    vulnerable: Optional[bool] = False


@app.post("/api/predict")
def predict_route(b: PredictIn, u=Depends(current)):
    if _predict is None:
        raise bad(503, "موديل الفرز مش متاح دلوقتي")
    syms = [s for s in (b.symptoms or [])[:20] if s in SYMC]
    return _predict(description=(b.description or "")[:2000], location=(b.location or None), symptoms=syms,
                    onset=(b.onset or None), vulnerable=bool(b.vulnerable))


# ---------------------------------------------------------------- الطلبات
class OrderIn(BaseModel):
    svc: str
    pr: str
    place: str = ""
    syms: List[str] = []
    symc: List[str] = []
    desc: str = ""
    date: str
    slot: str = ""
    addr: int = 0
    files: int = 0
    vulnerable: bool = False


@app.post("/api/orders")
def create_order(b: OrderIn, u=Depends(need("customer")), conn=Depends(get_db)):
    if b.svc not in SERVICES:
        raise bad(422, "نوع الخدمة غلط")
    if not enabled_map(conn).get(b.svc):
        raise bad(400, "الخدمة دي لسه مش متاحة وهتتوفر قريباً. لو في خطر اخرج من المكان واطلب أرقام الطوارئ الرسمية.")
    if b.pr not in PRIOS:
        raise bad(422, "الأولوية غلط")
    if not DATE_RE.match(b.date):
        raise bad(422, "اختار تاريخ الزيارة")
    symc = [s for s in b.symc[:20] if s in SYMC]
    pr = "emerg" if set(symc) & SAFETY else b.pr          # قاعدة الأمان على السيرفر مش بس في الفرونت
    addrs = jl(u["addrs"], [])
    addr = addrs[b.addr] if 0 <= b.addr < len(addrs) else (addrs[0] if addrs else {})
    triage = None
    if _predict:
        try:
            triage = _predict(description=b.desc[:2000], symptoms=symc, vulnerable=b.vulnerable)
        except Exception as e:
            log.warning("triage failed: %s", e)
    oid = counter(conn, "order", "HO", 1000)
    conn.execute("""INSERT INTO orders(id,email,svc,pr,place,syms,descr,date,slot,addr,status,files,created,triage)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (oid, u["email"], b.svc, pr, clean(b.place, 60, "المكان"), json.dumps([clean(s, 80, "العرض") for s in b.syms[:20]], ensure_ascii=False),
                  clean(b.desc, 2000, "الوصف"), b.date, clean(b.slot, 80, "الفترة"), json.dumps(addr, ensure_ascii=False),
                  "قيد المراجعة", max(0, min(b.files, 20)), now_ms(), json.dumps(triage, ensure_ascii=False) if triage else None))
    audit(conn, u, f"طلب جديد {oid}")
    return ok(conn, id=oid)


def get_order(conn, oid):
    r = conn.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not r:
        raise bad(404, "الطلب مش موجود")
    return r


class AssignIn(BaseModel):
    tech: str


@app.post("/api/orders/{oid}/assign")
def assign(oid: str, b: AssignIn, u=Depends(need("call")), conn=Depends(get_db)):
    o = get_order(conn, oid)
    if o["status"] not in ASSIGNABLE:
        raise bad(400, "الطلب ده مينفعش يتسند في حالته الحالية")
    t = conn.execute("SELECT * FROM users WHERE role='tech' AND email=? AND active=1", (b.tech.strip().lower(),)).fetchone()
    if not t:
        raise bad(422, "الفني غير متاح")
    conn.execute("UPDATE orders SET tech=?, status='تم الإسناد' WHERE id=?", (t["email"], oid))
    audit(conn, u, f"إسناد {oid} إلى {t['name']}")
    return ok(conn)


def apply_call(conn, u, oid, res):
    o = get_order(conn, oid)
    if o["status"] not in OPEN_ASSIGNED:
        raise bad(400, "الطلب مش مسند لفني دلوقتي")
    t = conn.execute("SELECT name FROM users WHERE role='tech' AND email=?", (o["tech"],)).fetchone()
    if res == "وافق":
        conn.execute("UPDATE orders SET status='إتمام محتمل' WHERE id=?", (oid,))
    elif res == "رفض":
        conn.execute("UPDATE orders SET status='قيد المراجعة', tech='' WHERE id=?", (oid,))
    conn.execute("INSERT INTO calls(ts,dir,who,note,outcome) VALUES(?,?,?,?,?)",
                 (now_ms(), "صادر", t["name"] if t else "—", f"طلب {oid}", res))
    audit(conn, u, f"اتصال بالفني بخصوص {oid}: {res}")


class ResIn(BaseModel):
    result: str


@app.post("/api/orders/{oid}/call")
def order_call(oid: str, b: ResIn, u=Depends(need("call")), conn=Depends(get_db)):
    if b.result not in RESULTS:
        raise bad(422, "نتيجة الاتصال غلط")
    apply_call(conn, u, oid, b.result)
    return ok(conn)


class CloseIn(BaseModel):
    lab: float = 0
    parts: float = 0


@app.post("/api/orders/{oid}/close")
def close_order(oid: str, b: CloseIn, u=Depends(need("tech")), conn=Depends(get_db)):
    o = get_order(conn, oid)
    if o["tech"] != u["email"] or o["status"] not in OPEN_ASSIGNED:
        raise bad(400, "الطلب ده مش مسند لك أو اتقفل قبل كده")
    if not (0 <= b.lab <= 1e6 and 0 <= b.parts <= 1e6):
        raise bad(422, "المبالغ غير صحيحة")
    sub = round(b.lab + b.parts, 2)
    tax = round(sub * VAT, 2)
    inv = {"lab": round(b.lab, 2), "parts": round(b.parts, 2), "sub": sub, "tax": tax, "total": round(sub + tax, 2), "paid": False, "ts": now_ms()}
    conn.execute("UPDATE orders SET status='مكتمل', inv=? WHERE id=?", (json.dumps(inv), oid))
    audit(conn, u, f"إغلاق أمر {oid}")
    return ok(conn)


# ---------------------------------------------------------------- المالي
def get_invoice_order(conn, oid):
    o = get_order(conn, oid)
    inv = jl(o["inv"], None)
    if not inv:
        raise bad(400, "مفيش فاتورة للطلب ده")
    return o, inv


class PayIn(BaseModel):
    method: str = "فيزا"


@app.post("/api/invoices/{oid}/pay")
def pay_invoice(oid: str, b: PayIn, u=Depends(need("finance")), conn=Depends(get_db)):
    o, inv = get_invoice_order(conn, oid)
    if inv.get("paid"):
        raise bad(400, "الفاتورة اتحصّلت قبل كده")
    if b.method not in PAYM:
        raise bad(422, "طريقة الدفع غلط")
    inv.update(paid=True, method=b.method, paidAt=now_ms())
    conn.execute("UPDATE orders SET inv=? WHERE id=?", (json.dumps(inv, ensure_ascii=False), oid))
    audit(conn, u, f"تحصيل فاتورة {oid}")
    return ok(conn)


@app.post("/api/invoices/{oid}/eta")
def eta_invoice(oid: str, u=Depends(need("finance")), conn=Depends(get_db)):
    o, inv = get_invoice_order(conn, oid)
    if not inv.get("eta"):
        inv["eta"] = {"uuid": f"TEST-{oid}-{secrets.token_hex(4)}", "ts": now_ms()}     # تجريبي لحد ما نربط الـ API الحقيقي
        conn.execute("UPDATE orders SET inv=? WHERE id=?", (json.dumps(inv), oid))
        audit(conn, u, f"إرسال تجريبي لـ ETA: {oid}")
    return ok(conn)


class PayTechIn(BaseModel):
    email: str


@app.post("/api/payroll/pay")
def pay_tech(b: PayTechIn, u=Depends(need("finance")), conn=Depends(get_db)):
    t = conn.execute("SELECT name FROM users WHERE role='tech' AND email=?", (b.email.strip().lower(),)).fetchone()
    if not t:
        raise bad(404, "الفني مش موجود")
    n = 0
    for o in conn.execute("SELECT id, inv FROM orders WHERE tech=? AND paid_out=0 AND inv IS NOT NULL", (b.email.strip().lower(),)).fetchall():
        if jl(o["inv"], {}).get("paid"):
            conn.execute("UPDATE orders SET paid_out=1, paid_out_at=? WHERE id=?", (now_ms(), o["id"]))
            n += 1
    if not n:
        raise bad(400, "مفيش مستحقات تتصرف")
    audit(conn, u, f"صرف مستحقات {t['name']} ({n} أوامر)")
    return ok(conn)


class ExpIn(BaseModel):
    descr: str
    amt: float
    kind: str = "أخرى"


@app.post("/api/expenses")
def add_expense(b: ExpIn, u=Depends(need("finance")), conn=Depends(get_db)):
    d = clean(b.descr, 200, "الوصف", True)
    if not (0 < b.amt <= 1e8):
        raise bad(422, "اكتب مبلغ صحيح")
    conn.execute("INSERT INTO expenses(ts,descr,amt,kind) VALUES(?,?,?,?)", (now_ms(), d, round(b.amt, 2), b.kind if b.kind in EXPK else "أخرى"))
    audit(conn, u, f"تسجيل مصروف: {d}")
    return ok(conn)


class RateIn(BaseModel):
    rate: float


@app.put("/api/settings/rate")
def set_rate(b: RateIn, u=Depends(need("finance", "admin")), conn=Depends(get_db)):
    if not (0 <= b.rate <= 100):
        raise bad(422, "النسبة لازم بين 0 و100")
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('rate',?)", (str(b.rate),))
    audit(conn, u, f"تعديل نسبة عمولة الفني إلى {b.rate}%")
    return ok(conn)


# ---------------------------------------------------------------- التذاكر
class TicketIn(BaseModel):
    type: str
    pr: str = "mid"
    text: str
    ord: str = ""
    actions: List[str] = []
    cust: str = ""
    sender: str = ""      # اسم/موبايل العميل زي ما الكول سنتر كتبه


def new_ticket(conn, email, from_name, typ, pr, text, ord_, actions):
    tid = counter(conn, "ticket", "TK", 2000)
    conn.execute("INSERT INTO tickets(id,email,from_name,type,pr,text,ord,actions,status,ts) VALUES(?,?,?,?,?,?,?,?,'جديد',?)",
                 (tid, email, from_name, typ, pr, text, ord_, json.dumps(actions, ensure_ascii=False), now_ms()))
    return tid


@app.post("/api/tickets")
def staff_ticket(b: TicketIn, u=Depends(need("call")), conn=Depends(get_db)):
    text = clean(b.text, 3000, "تفاصيل البلاغ", True)
    typ = clean(b.type, 80, "التصنيف", True)
    if b.pr not in PRIOS:
        raise bad(422, "الأولوية غلط")
    email = b.cust.strip().lower()
    if email and not conn.execute("SELECT 1 FROM users WHERE role='customer' AND email=?", (email,)).fetchone():
        email = ""
    ord_ = b.ord if b.ord and conn.execute("SELECT 1 FROM orders WHERE id=?", (b.ord,)).fetchone() else ""
    acts = [clean(a, 60, "إجراء") for a in b.actions[:6]]
    who = clean(b.sender, 120, "العميل") or "—"
    tid = new_ticket(conn, email, who, typ, b.pr, text, ord_, acts)
    tlog(conn, tid, "تسجيل التذكرة" + (" – " + "، ".join(acts) if acts else ""))
    conn.execute("INSERT INTO calls(ts,dir,who,note,outcome) VALUES(?,?,?,?,?)", (now_ms(), "وارد", who, typ, f"تذكرة {tid}"))
    audit(conn, u, f"تسجيل بلاغ {tid}")
    return ok(conn, id=tid)


class SupportIn(BaseModel):
    type: str = "شكوى"
    text: str


@app.post("/api/tickets/support")
def support_ticket(b: SupportIn, u=Depends(need("customer")), conn=Depends(get_db)):
    text = clean(b.text, 3000, "التفاصيل", True)
    tid = new_ticket(conn, u["email"], u["name"], clean(b.type, 40, "النوع", True), "mid", text, "", [])
    tlog(conn, tid, "العميل أرسل التذكرة")
    return ok(conn, id=tid)


def get_ticket(conn, tid):
    r = conn.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
    if not r:
        raise bad(404, "التذكرة مش موجودة")
    return r


class NoteIn(BaseModel):
    text: str


@app.post("/api/tickets/{tid}/note")
def ticket_note(tid: str, b: NoteIn, u=Depends(need("call")), conn=Depends(get_db)):
    get_ticket(conn, tid)
    tlog(conn, tid, "ملاحظة: " + clean(b.text, 500, "الملاحظة", True))
    return ok(conn)


@app.post("/api/tickets/{tid}/escalate")
def ticket_escalate(tid: str, u=Depends(need("call")), conn=Depends(get_db)):
    get_ticket(conn, tid)
    conn.execute("UPDATE tickets SET status='مُصعَّد' WHERE id=?", (tid,))
    tlog(conn, tid, "تصعيد للأدمن")
    audit(conn, u, f"تصعيد {tid}")
    return ok(conn)


@app.post("/api/tickets/{tid}/done")
def ticket_done(tid: str, u=Depends(need("call")), conn=Depends(get_db)):
    get_ticket(conn, tid)
    conn.execute("UPDATE tickets SET status='تم الحل' WHERE id=?", (tid,))
    tlog(conn, tid, "تم الحل")
    audit(conn, u, f"حل تذكرة {tid}")
    return ok(conn)


@app.post("/api/tickets/{tid}/techcall")
def ticket_techcall(tid: str, b: ResIn, u=Depends(need("call")), conn=Depends(get_db)):
    t = get_ticket(conn, tid)
    if b.result not in RESULTS:
        raise bad(422, "نتيجة الاتصال غلط")
    tlog(conn, tid, "اتصال بالفني: " + b.result)
    if t["ord"]:
        apply_call(conn, u, t["ord"], b.result)
    return ok(conn)


# ---------------------------------------------------------------- الأدمن
class StaffIn(BaseModel):
    role: str
    name: str
    email: str
    password: str


@app.post("/api/admin/staff")
def add_staff(b: StaffIn, u=Depends(need("admin")), conn=Depends(get_db)):
    if b.role not in ("tech", "call", "finance"):
        raise bad(422, "الدور غلط")
    name = clean(b.name, 80, "الاسم", True)
    email = b.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise bad(422, "البريد الإلكتروني مش صحيح")
    check_password_rules(b.password)
    if conn.execute("SELECT 1 FROM users WHERE email=? AND role=?", (email, b.role)).fetchone():
        raise bad(409, "البريد مستخدم قبل كده لنفس الدور")
    conn.execute("INSERT INTO users(role,name,email,phone,pass_hash,created) VALUES(?,?,?,?,?,?)",
                 (b.role, name, email, "", sec.hash_password(b.password), now_ms()))
    audit(conn, u, f"إنشاء حساب {ROLE_AR[b.role]}: {email}")
    return ok(conn)


@app.post("/api/admin/staff/{uid}/toggle")
def toggle_staff(uid: int, u=Depends(need("admin")), conn=Depends(get_db)):
    r = conn.execute("SELECT * FROM users WHERE id=? AND role!='customer'", (uid,)).fetchone()
    if not r:
        raise bad(404, "الحساب مش موجود")
    if r["seeded"] or r["id"] == u["id"]:
        raise bad(400, "الحسابات الثابتة مينفعش تتوقف")
    conn.execute("UPDATE users SET active=? WHERE id=?", (0 if r["active"] else 1, uid))
    audit(conn, u, f"{'إيقاف' if r['active'] else 'تفعيل'} حساب {r['email']}")
    return ok(conn)


@app.post("/api/admin/services/{key}/toggle")
def toggle_service(key: str, u=Depends(need("admin")), conn=Depends(get_db)):
    if key not in SERVICES:
        raise bad(404, "الخدمة مش موجودة")
    m = enabled_map(conn)
    m[key] = 0 if m.get(key) else 1
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('enabled',?)", (json.dumps(m),))
    audit(conn, u, f"{'تفعيل' if m[key] else 'إيقاف'} خدمة {key}")
    return ok(conn)


# ---------------------------------------------------------------- الصفحات
@app.get("/health")
def health():
    return {"status": "ok", "model": _predict is not None}


@app.get("/", include_in_schema=False)
def index():
    f = config.FRONTEND_DIR / "index.html"
    if not f.exists():
        raise bad(404, "ملف الفرونت مش موجود في فولدر frontend")
    return FileResponse(f, headers={"Cache-Control": "no-cache"})
