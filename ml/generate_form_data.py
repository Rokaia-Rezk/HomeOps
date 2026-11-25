"""داتا صناعية مع خانات الفورم. السياسات (policy) موثقة تحت."""
import os, re, random, csv
os.environ.setdefault("SCALE", "3")
import generate_data as g          # بيولّد rows (نص, فئة, أولوية)
random.seed(7)

SYMS = ["leak","nowater","gas","burn","spark","nopower","noise","broken","request","crack","lock"]
RULES = {
 "leak":    r"تسريب|بتنزل|بتغرق|مغرق|بتقطر|بينقط|بيقطر|بتسرب|طالعة|راجعة|بتنقط",
 "nowater": r"مفيش مية|ضغط المية|السخان مش شغال",
 "gas":     r"غاز|لهب",
 "burn":    r"حريق|دخان|شياط|محروق|سخنت",
 "spark":   r"شرار|شرارة|اخدت كهربا|صعقة|بيكهربني|فرقعة|ولعت|طلع شرار",
 "nopower": r"الكهربا قطعت|مفيهاش كهربا|بيفصل|بيرمش|مفيش كهربا",
 "noise":   r"صوت|بيصرصر|بتزيق",
 "broken":  r"مش شغال|مش بتبرد|واقف|وقف|بايظ|باظ|مش بتعصر|مش بتولع|مش بيسخن|مش بيشتغل|مش بيبرد|ضعيف|مش بيتقفل|مش بتفتح|مش بتصرف|مسدود|ببطء|مش مظبوط|مش راضي",
 "crack":   r"شرخ|شروخ|رطوبة|قشرة|تتساقط|يتساقط|هيقع|اتكسر|وقع",
 "lock":    r"القفل|قفل|كالون|مفتاح|علق|اتحبست",
}
LOC_RE = {"kitchen": r"مطبخ", "bath": r"حمام", "living": r"صالة", "bedroom": r"اوضة|غرفة"}
LOC_BY_CAT = {
 "سباكة": {"bath": .5, "kitchen": .4, "other": .1},
 "كهرباء": {"living": .25, "bedroom": .25, "kitchen": .15, "bath": .1, "entrance": .1, "balcony": .1, "other": .05},
 "تكييف وتبريد": {"bedroom": .5, "living": .3, "kitchen": .15, "other": .05},
 "دهانات وتشطيبات": {"living": .35, "bedroom": .35, "bath": .1, "kitchen": .1, "other": .1},
 "نجارة": {"bedroom": .35, "entrance": .25, "living": .2, "kitchen": .1, "balcony": .1},
 "أجهزة منزلية": {"kitchen": .55, "living": .2, "bath": .15, "bedroom": .1},
}
ONSET = {"emergency": {"now": .7, "today": .25, "days": .05},
         "urgent":    {"now": .3, "today": .45, "days": .25},
         "normal":    {"today": .1, "days": .3, "weeks": .6}}

def pick(d): return random.choices(list(d), weights=list(d.values()))[0]

def derive_symptoms(text):
    t = text.replace("مفتاح النور", "")
    out = {k for k, rx in RULES.items() if re.search(rx, t)}
    if not out:
        out = {"request"} if re.search(r"عايز|محتاج|ممكن حد", t) else {"broken"}
    elif re.search(r"عايز|محتاج", t) and not (out - {"noise"}):
        out = {"request"} | out
    return out

def derive_location(text, cat):
    for loc, rx in LOC_RE.items():
        if re.search(rx, text) and random.random() < .85: return loc
    return pick(LOC_BY_CAT[cat])

rows = []
for text, cat, prio in g.rows:
    sy = derive_symptoms(text)
    # ضوضاء واقعية: العميل بينسى يعلّم 20%، وأحيانا يعلّم حاجة زيادة 8%
    shown = {s for s in sy if random.random() < .8}
    if random.random() < .08: shown.add(random.choice(SYMS))
    vul = int(random.random() < .15)
    # policy: وجود أطفال/كبار سن يرفع الطلب "العادي" (مش طلب تركيب) لعاجل
    if vul and prio == "normal" and "request" not in sy: prio = "urgent"
    onset = pick(ONSET[prio])
    t_in = text if random.random() > .2 else ""        # 20% من العملاء مش بيكتبوا وصف
    rows.append([t_in, cat, prio, derive_location(text, cat), onset, vul] + [int(s in shown) for s in SYMS])

random.shuffle(rows)
with open("train_form.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f); w.writerow(["text","category","priority","location","onset","vulnerable"] + [f"sym_{s}" for s in SYMS]); w.writerows(rows)
print(len(rows), "rows | empty-text:", sum(1 for r in rows if not r[0]))
