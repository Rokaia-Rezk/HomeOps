import joblib, os
import pandas as pd
from common import normalize_ar  # لازم عشان joblib يلاقي الدالة

_D = os.path.dirname(os.path.abspath(__file__))
_cat = joblib.load(os.path.join(_D, "model_form_category.joblib"))
_pri = joblib.load(os.path.join(_D, "model_form_priority.joblib"))

SYMS = ["leak","nowater","gas","burn","spark","nopower","noise","broken","request","crack","lock"]
CAT_THRESHOLD = 0.60
PRI_THRESHOLD = 0.50
EMERGENCY_GUARD = 0.30
EMERGENCY_SYMPTOMS = {"gas", "burn", "spark"}     # قاعدة صريحة: غاز/حريق/شرر = طوارئ دايما
PRI_AR = {"normal": "عادي", "urgent": "عاجل", "emergency": "طوارئ"}

def _row(description, location, symptoms, onset, vulnerable):
    symptoms = set(symptoms or [])
    r = {"text": (description or "").strip(), "location": location or "unknown", "onset": onset or "unknown",
         "vulnerable": int(bool(vulnerable))}
    r.update({f"sym_{s}": int(s in symptoms) for s in SYMS})
    return pd.DataFrame([r])

def predict(description="", location=None, symptoms=None, onset=None, vulnerable=False) -> dict:
    symptoms = set(symptoms or [])
    if len(normalize_ar(description or "")) < 3 and not symptoms:
        return {"category": None, "priority": None, "needs_review": True, "reason": "محتاج وصف أو أعراض"}

    X = _row(description, location, symptoms, onset, vulnerable)
    pc, pp = _cat.predict_proba(X)[0], _pri.predict_proba(X)[0]
    cat, cat_conf = _cat.classes_[pc.argmax()], float(pc.max())
    probs = dict(zip(_pri.classes_, map(float, pp)))
    pri, pri_conf = max(probs.items(), key=lambda kv: kv[1])

    reason = "model"
    if symptoms & EMERGENCY_SYMPTOMS:
        pri, pri_conf, reason = "emergency", 1.0, "rule:" + ",".join(sorted(symptoms & EMERGENCY_SYMPTOMS))
    elif pri != "emergency" and probs.get("emergency", 0) >= EMERGENCY_GUARD:
        pri, pri_conf, reason = "emergency", probs["emergency"], "safety_guard"

    ok_c, ok_p = cat_conf >= CAT_THRESHOLD, pri_conf >= PRI_THRESHOLD
    return {
        "category": cat if ok_c else None, "category_confidence": round(cat_conf, 3),
        "priority": pri if ok_p else None, "priority_ar": PRI_AR[pri] if ok_p else None,
        "priority_confidence": round(pri_conf, 3), "priority_source": reason,
        "needs_review": not (ok_c and ok_p),   # الفرونت: اعرض الاقتراح والعميل يأكد
        "top_categories": [{"label": str(_cat.classes_[i]), "p": round(float(pc[i]), 3)} for i in pc.argsort()[::-1][:3]],
    }

if __name__ == "__main__":
    import json
    for kw in [dict(description="المية بتنزل من تحت الحوض", location="kitchen", symptoms=["leak"], onset="now"),
               dict(description="", location="kitchen", symptoms=["gas"], onset="now"),
               dict(description="", location="bedroom", symptoms=["broken"], onset="today", vulnerable=True),
               dict(description="عايز ادهن الاوضة", location="bedroom", symptoms=["request"], onset="weeks"),
               dict(description="الدنيا حلوة النهارده")]:
        print(kw, "\n  ->", json.dumps(predict(**kw), ensure_ascii=False))
