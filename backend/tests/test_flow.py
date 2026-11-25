import json
from server import main

SEED = ("boss@example.com", "Boss@12345")


def login(c, role, email=SEED[0], pw=SEED[1]):
    r = c.post("/api/auth/login", json={"role": role, "email": email, "password": pw})
    return r


def H(c, role, **kw):
    r = login(c, role, **kw)
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_health_and_index(c):
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/health").json()["model"] is True
    assert c.get("/").status_code == 200


def test_seed_accounts_login_and_wrong_role_or_password(c):
    for role in ("admin", "finance", "call", "tech"):
        assert login(c, role).status_code == 200
    assert login(c, "admin", pw="Wrong@123").status_code == 401
    assert login(c, "customer").status_code == 401        # مفيش عميل بالإيميل ده لسه
    assert c.get("/api/state").status_code == 401


def test_register_rules_and_duplicate(c):
    body = {"name": "سارة", "phone": "01012345678", "email": "Sara@Example.com", "password": "Aa@12345", "lang": "ar",
            "addr": {"city": "دمياط الجديدة", "district": "الحي الأول", "street": "شارع 1", "bld": "5", "floor": "2"}}
    assert c.post("/api/auth/register", json={**body, "password": "weak"}).status_code == 422
    assert c.post("/api/auth/register", json={**body, "phone": "123"}).status_code == 422
    r = c.post("/api/auth/register", json=body)
    assert r.status_code == 200 and r.json()["user"]["email"] == "sara@example.com"
    assert c.post("/api/auth/register", json=body).status_code == 409
    assert login(c, "customer", "sara@example.com", "Aa@12345").status_code == 200   # بترجع تسجل تاني


def test_full_cycle(c):
    cust = H(c, "customer", email="sara@example.com", pw="Aa@12345")
    order = {"svc": "plumb", "pr": "norm", "place": "المطبخ", "syms": ["ريحة غاز"], "symc": ["gas"], "desc": "ريحة", "date": "2030-01-01",
             "slot": "الفترة الصباحية 09:00 – 12:00", "addr": 0, "files": 0}
    # خدمة مش متاحة
    assert c.post("/api/orders", headers=cust, json={**order, "svc": "ac"}).status_code == 400
    r = c.post("/api/orders", headers=cust, json=order)
    assert r.status_code == 200
    oid = r.json()["id"]
    st = c.get("/api/state", headers=cust).json()
    o = [x for x in st["orders"] if x["id"] == oid][0]
    assert o["pr"] == "emerg" and o["status"] == "قيد المراجعة"       # قاعدة الأمان على السيرفر

    # صلاحيات: العميل مينفعش يسند ولا يحصّل
    assert c.post(f"/api/orders/{oid}/assign", headers=cust, json={"tech": SEED[0]}).status_code == 403
    call, tech, fin, admin = H(c, "call"), H(c, "tech"), H(c, "finance"), H(c, "admin")
    assert c.post(f"/api/orders/{oid}/close", headers=call, json={"lab": 1, "parts": 0}).status_code == 403
    # الفني ما يشوفش الطلب قبل الإسناد
    assert c.get("/api/state", headers=tech).json()["orders"] == []
    assert c.post(f"/api/orders/{oid}/close", headers=tech, json={"lab": 100, "parts": 0}).status_code == 400

    assert c.post(f"/api/orders/{oid}/assign", headers=call, json={"tech": "nobody@x.com"}).status_code == 422
    assert c.post(f"/api/orders/{oid}/assign", headers=call, json={"tech": SEED[0]}).status_code == 200
    ts = c.get("/api/state", headers=tech).json()
    assert [x["id"] for x in ts["orders"]] == [oid] and ts["users"][0]["email"] == "sara@example.com"
    # رفض ثم إسناد تاني ثم موافقة
    assert c.post(f"/api/orders/{oid}/call", headers=call, json={"result": "رفض"}).status_code == 200
    assert c.get("/api/state", headers=tech).json()["orders"] == []
    c.post(f"/api/orders/{oid}/assign", headers=call, json={"tech": SEED[0]})
    assert c.post(f"/api/orders/{oid}/call", headers=call, json={"result": "وافق"}).status_code == 200
    assert c.post(f"/api/orders/{oid}/call", headers=call, json={"result": "xx"}).status_code == 422

    # إغلاق بفاتورة والضريبة 14% تتحسب على السيرفر
    assert c.post(f"/api/orders/{oid}/close", headers=tech, json={"lab": -5, "parts": 0}).status_code == 422
    assert c.post(f"/api/orders/{oid}/close", headers=tech, json={"lab": 200, "parts": 100}).status_code == 200
    assert c.post(f"/api/orders/{oid}/close", headers=tech, json={"lab": 200, "parts": 100}).status_code == 400
    inv = [x for x in c.get("/api/state", headers=cust).json()["orders"] if x["id"] == oid][0]["inv"]
    assert inv["sub"] == 300 and inv["tax"] == 42 and inv["total"] == 342 and inv["paid"] is False

    # المالي
    assert c.post(f"/api/invoices/{oid}/pay", headers=fin, json={"method": "كاش"}).status_code == 422
    assert c.post(f"/api/invoices/{oid}/eta", headers=fin).status_code == 200
    assert c.post(f"/api/invoices/{oid}/pay", headers=fin, json={"method": "فودافون كاش"}).status_code == 200
    assert c.post(f"/api/invoices/{oid}/pay", headers=fin, json={"method": "فيزا"}).status_code == 400
    assert c.post("/api/payroll/pay", headers=fin, json={"email": SEED[0]}).status_code == 200
    assert c.post("/api/payroll/pay", headers=fin, json={"email": SEED[0]}).status_code == 400
    assert c.post("/api/expenses", headers=fin, json={"descr": "بنزين", "amt": 50, "kind": "وقود وانتقالات"}).status_code == 200
    assert c.post("/api/expenses", headers=fin, json={"descr": "x", "amt": -1}).status_code == 422
    assert c.put("/api/settings/rate", headers=fin, json={"rate": 150}).status_code == 422
    assert c.put("/api/settings/rate", headers=fin, json={"rate": 55}).status_code == 200
    fs = c.get("/api/state", headers=fin).json()
    assert fs["rate"] == 55 and fs["expenses"][0]["amt"] == 50 and fs["orders"][0]["paidOut"] is True

    # الأدمن بيشوف سجل التدقيق
    assert any("إغلاق" in a["a"] for a in c.get("/api/state", headers=admin).json()["audit"])


def test_tickets(c):
    cust = H(c, "customer", email="sara@example.com", pw="Aa@12345")
    call = H(c, "call")
    assert c.post("/api/tickets/support", headers=cust, json={"type": "شكوى", "text": "  "}).status_code == 422
    tid = c.post("/api/tickets/support", headers=cust, json={"type": "شكوى", "text": "تأخير"}).json()["id"]
    assert tid in [t["id"] for t in c.get("/api/state", headers=call).json()["tickets"]]
    assert c.post(f"/api/tickets/{tid}/note", headers=cust, json={"text": "x"}).status_code == 403
    for p, b in [("note", {"text": "اتصلت"}), ("escalate", None), ("done", None)]:
        assert c.post(f"/api/tickets/{tid}/{p}", headers=call, **({"json": b} if b else {})).status_code == 200
    t = [t for t in c.get("/api/state", headers=call).json()["tickets"] if t["id"] == tid][0]
    assert t["status"] == "تم الحل" and len(t["log"]) >= 4
    r = c.post("/api/tickets", headers=call, json={"type": "بلاغ عطل جديد", "pr": "urgent", "text": "x", "actions": ["إخطار الفني فوراً"], "sender": "عميل تليفوني"})
    assert r.status_code == 200
    assert c.post("/api/tickets/TK-9999/done", headers=call).status_code == 404
    # العميل ميشوفش تذاكر غيره
    assert all(t["email"] == "sara@example.com" for t in c.get("/api/state", headers=cust).json()["tickets"])


def test_admin_staff_and_services(c):
    admin = H(c, "admin")
    s = {"role": "tech", "name": "م. أحمد", "email": "ahmed@example.com", "password": "Tech@12345"}
    assert c.post("/api/admin/staff", headers=admin, json={**s, "password": "123"}).status_code == 422
    assert c.post("/api/admin/staff", headers=admin, json={**s, "role": "admin"}).status_code == 422
    assert c.post("/api/admin/staff", headers=admin, json=s).status_code == 200
    assert c.post("/api/admin/staff", headers=admin, json=s).status_code == 409
    assert login(c, "tech", "ahmed@example.com", "Tech@12345").status_code == 200
    staff = c.get("/api/state", headers=admin).json()["staff"]
    ahmed = [x for x in staff if x["email"] == "ahmed@example.com"][0]
    seeded = [x for x in staff if x["seeded"]][0]
    assert c.post(f"/api/admin/staff/{seeded['id']}/toggle", headers=admin).status_code == 400
    assert c.post(f"/api/admin/staff/{ahmed['id']}/toggle", headers=admin).status_code == 200
    assert login(c, "tech", "ahmed@example.com", "Tech@12345").status_code == 401     # موقوف
    # الموظف غير الأدمن مينفعش يعمل حسابات
    assert c.post("/api/admin/staff", headers=H(c, "call"), json=s).status_code == 403
    # تفعيل خدمة
    assert c.post("/api/admin/services/ac/toggle", headers=admin).status_code == 200
    cust = H(c, "customer", email="sara@example.com", pw="Aa@12345")
    assert c.get("/api/state", headers=cust).json()["enabled"]["ac"] == 1
    assert c.post("/api/admin/services/zzz/toggle", headers=admin).status_code == 404


def test_predict_and_profile(c):
    cust = H(c, "customer", email="sara@example.com", pw="Aa@12345")
    r = c.post("/api/predict", headers=cust, json={"description": "المية بتنزل من تحت الحوض", "location": "kitchen", "symptoms": ["leak", "evil"], "onset": "now"})
    assert r.status_code == 200 and r.json()["category"] == "سباكة" and r.json()["priority"] == "emergency"
    assert c.post("/api/predict", json={"description": "x"}).status_code == 401
    r = c.put("/api/me", headers=cust, json={"name": "سارة إبراهيم", "phone": "01099999999", "lang": "ar"})
    assert r.status_code == 200 and r.json()["name"] == "سارة إبراهيم"
    assert c.put("/api/me", headers=cust, json={"name": "x", "phone": "12"}).status_code == 422


def test_otp_reset_and_lockout(c, capsys):
    main.config.DEV_OTP = True
    assert c.post("/api/auth/forgot", json={"email": "nobody@x.com"}).json() == {"ok": True}       # مفيش كشف للإيميلات
    assert c.post("/api/auth/forgot", json={"email": "sara@example.com"}).status_code == 200
    code = [l for l in capsys.readouterr().out.splitlines() if "[OTP]" in l][-1].split(":")[-1].strip()
    assert c.post("/api/auth/reset", json={"email": "sara@example.com", "code": "0000" if code != "0000" else "1111", "password": "New@12345"}).status_code == 400
    assert c.post("/api/auth/reset", json={"email": "sara@example.com", "code": code, "password": "weak"}).status_code == 422
    r = c.post("/api/auth/reset", json={"email": "sara@example.com", "code": code, "password": "New@12345"})
    assert r.status_code == 200
    assert c.post("/api/auth/reset", json={"email": "sara@example.com", "code": code, "password": "New@12345"}).status_code == 400   # الرمز بيتستخدم مرة
    assert login(c, "customer", "sara@example.com", "New@12345").status_code == 200
    for _ in range(5):
        login(c, "customer", "sara@example.com", "bad")
    assert login(c, "customer", "sara@example.com", "New@12345").status_code == 429           # قفل مؤقت
