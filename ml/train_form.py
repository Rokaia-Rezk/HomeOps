import pandas as pd, joblib, json
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from common import normalize_ar

SYMS = ["leak","nowater","gas","burn","spark","nopower","noise","broken","request","crack","lock"]
BIN = [f"sym_{s}" for s in SYMS] + ["vulnerable"]

def build(use_form=True):
    parts = [("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, preprocessor=normalize_ar), "text"),
             ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, preprocessor=normalize_ar), "text")]
    if use_form:
        parts += [("oh", OneHotEncoder(handle_unknown="ignore"), ["location", "onset"]), ("bin", "passthrough", BIN)]
    return Pipeline([("ct", ColumnTransformer(parts)), ("clf", LogisticRegression(max_iter=3000, C=5, class_weight="balanced"))])

tr = pd.read_csv("train_form.csv").fillna({"text": ""}); te = pd.read_csv("test_form.csv")
te_blank = te.assign(text="")          # عميل مكتبش وصف خالص
res, final = {}, {}
for target in ["category", "priority"]:
    for name, use_form in [("text_only", False), ("text+form", True)]:
        m = build(use_form).fit(tr, tr[target])
        for split, d in [("blind24", te[te.split == "blind"]), ("all68", te)]:
            p = m.predict(d); res[(target, name, split)] = accuracy_score(d[target], p)
        if use_form:
            p = m.predict(te_blank); res[(target, "form_only(no text)", "all68")] = accuracy_score(te[target], p)
            final[target] = m
    joblib.dump(final[target], f"model_form_{target}.joblib")
df = pd.Series(res).unstack(level=[0]).round(3)
print(df.to_string())
df.to_csv("metrics_form.csv", encoding="utf-8-sig")
