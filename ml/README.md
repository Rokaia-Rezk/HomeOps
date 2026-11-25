# HomeOps Smart Triage (Hybrid: Rules + ML)
يقترح **نوع الخدمة** و**الأولوية** من (وصف حر اختياري + خانات الفورم).

pip install -r requirements.txt
SCALE=3 python generate_data.py && python generate_form_data.py   # الداتا الصناعية
python make_test_form.py                                          # مجموعة الاختبار اليدوية
python train_form.py                                              # تدريب + مقارنة
uvicorn app:app --port 8000

الخانات المسموحة: form_schema.json
POST /predict  {"description":"", "location":"kitchen", "symptoms":["gas"], "onset":"now", "vulnerable":false}

- أعراض gas/burn/spark = طوارئ بقاعدة صريحة (مش احتمالات).
- needs_review=true -> الفرونت يعرض الاقتراح والعميل يأكد/يعدل.
- ملحوظة: train_data.csv / train.py / test_*.csv هي النسخة الأولى (نص بس) للمقارنة.
