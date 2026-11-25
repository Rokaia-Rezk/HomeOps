import re

_TASHKEEL = re.compile(r"[\u064B-\u0652\u0640]")

def normalize_ar(text: str) -> str:
    """تطبيع النص العربي: يشيل التشكيل والتطويل ويوحّد الحروف المتشابهة."""
    t = str(text).lower().strip()
    t = _TASHKEEL.sub("", t)
    t = re.sub("[إأآ]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)          # "بسرررعة" -> "بسرعة"
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()
