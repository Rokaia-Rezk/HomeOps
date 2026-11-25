import pandas as pd, joblib, json
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.model_selection import cross_val_score
from common import normalize_ar

def build():
    feats = FeatureUnion([
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, preprocessor=normalize_ar)),
        ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, preprocessor=normalize_ar)),
    ])
    return Pipeline([("tfidf", feats), ("clf", LogisticRegression(max_iter=2000, C=5, class_weight="balanced"))])

train = pd.read_csv("train_data.csv"); import sys
test = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else "test_blind.csv")
report = {}
for target in ["category", "priority"]:
    m = build()
    cv = cross_val_score(build(), train.text, train[target], cv=5, scoring="accuracy").mean()
    m.fit(train.text, train[target])
    pred = m.predict(test.text)
    acc, f1 = accuracy_score(test[target], pred), f1_score(test[target], pred, average="macro")
    print(f"\n=== {target} ===\nCV(synthetic)={cv:.3f} | HANDWRITTEN TEST acc={acc:.3f} macroF1={f1:.3f}")
    print(classification_report(test[target], pred, zero_division=0))
    wrong = test[pred != test[target]].assign(predicted=pred[pred != test[target]])
    if len(wrong): print("أخطاء:\n", wrong[["text", target, "predicted"]].to_string(index=False))
    joblib.dump(m, f"model_{target}.joblib")
    report[target] = {"cv_synthetic": round(cv, 3), "handwritten_acc": round(acc, 3), "handwritten_macro_f1": round(f1, 3)}
json.dump(report, open("metrics.json", "w"), ensure_ascii=False, indent=2)
