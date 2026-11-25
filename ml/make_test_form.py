import csv
SYMS = ["leak","nowater","gas","burn","spark","nopower","noise","broken","request","crack","lock"]
# text | category | priority | location | symptoms | onset | vulnerable      (أول 24 = blind)
T = """في خرطوم المية ورا الغسالة اتفك والمطبخ غرقان|سباكة|emergency|kitchen|leak|now|0
عايز اعمل توصيلة مية للمطبخ الجديد|سباكة|normal|kitchen|request|weeks|0
المياه مش بتطلع للدور التالت|سباكة|urgent|other|nowater|today|0
ممكن حد يغيرلي الدش اللي في الحمام|سباكة|normal|bath|request|days|0
اللمبات في الصالة بتنور وتطفي|كهرباء|urgent|living|broken|days|0
محتاج حد يركب سبوتات في الطرقة|كهرباء|normal|entrance|request|weeks|0
في ريحة سلك محروق جاية من ورا التلفزيون|كهرباء|emergency|living|burn|now|0
اضاءة الحمام بايظة|كهرباء|normal|bath|broken|days|0
جهاز التكييف بيطلع هوا سخن|تكييف وتبريد|urgent|bedroom|broken|today|0
عايز اضيف تكييف تاني في الاوضة|تكييف وتبريد|normal|bedroom|request|weeks|0
التبريد في الثلاجة ضعيف والاكل بقى يبوظ|تكييف وتبريد|urgent|kitchen|broken|today|0
عايز اغسل التكييف قبل الصيف|تكييف وتبريد|normal|bedroom|request|weeks|0
محتاج حد يعمل تشطيب للشقة|دهانات وتشطيبات|normal|other|request|weeks|0
الحيطة منفوخة من الرطوبة|دهانات وتشطيبات|normal|bedroom|crack|weeks|0
عايز اغير الارضية القديمة|دهانات وتشطيبات|normal|living|request|weeks|0
في كتلة كبيرة من السقف مدلدلة وهتقع|دهانات وتشطيبات|emergency|living|crack|now|0
مفصلة باب الاوضة اتخلعت|نجارة|normal|bedroom|broken|days|0
عايز اعمل مكتبة خشب على مقاس الحيطة|نجارة|normal|living|request|weeks|0
الباب اتزنق ومش قادر اخرج من الحمام|نجارة|emergency|bath|lock|now|0
الشباك مش بيتقفل والجو بره بارد|نجارة|urgent|bedroom|broken|today|0
الغسالة بتفصل في نص الغسيل|أجهزة منزلية|urgent|bath|broken|today|0
عايز اركب ديب فريزر جديد|أجهزة منزلية|normal|kitchen|request|weeks|0
البوتجاز مش بيولع من امبارح|أجهزة منزلية|urgent|kitchen|broken|days|0
المكواة مبتسخنش|أجهزة منزلية|normal|bedroom|broken|days|0
المواسير في الحمام انفجرت والمية مغرقة الارضية|سباكة|emergency|bath|leak|now|0
الحوض مش بيشفط المية وبيطفح|سباكة|urgent|kitchen|leak|today|0
عايزين نركب حنفية جديدة في المطبخ|سباكة|normal|kitchen|request|weeks|0
مفيش مية سخنة خالص من امبارح|سباكة|urgent|bath|nowater|days|0
في مية بتخرج من تحت التواليت|سباكة|emergency|bath|leak|now|0
بوفيه الكهربا ولع وفي ريحة شياط|كهرباء|emergency|other|burn,spark|now|0
النور قطع من الاوضة دي بس|كهرباء|urgent|bedroom|nopower|today|0
عايز اركب كشاف في البلكونة|كهرباء|normal|balcony|request|weeks|0
كل ما اشغل الغسالة الكهربا تفصل|كهرباء|urgent|other|nopower|days|0
حسيت بكهربا وانا ماسك مفتاح النور|كهرباء|emergency|bedroom|spark|now|0
محتاج توصيل بريزتين جداد في الاوضة|كهرباء|normal|bedroom|request|weeks|0
التكييف مبقاش بيبرد خالص ودرجة الحرارة عالية|تكييف وتبريد|urgent|bedroom|broken|today|0
الاسبلت بيخرج مية على الارض|تكييف وتبريد|urgent|bedroom|leak|days|0
عايز اعمل صيانة وتنضيف للتكييفات قبل الصيف|تكييف وتبريد|normal|other|request|weeks|0
الثلاجة وقفت ومفيش تبريد خالص|تكييف وتبريد|urgent|kitchen|broken|now|0
عايز تركيب تكييف في المكتب|تكييف وتبريد|normal|other|request|weeks|0
في ريحة غاز جاية من التكييف|تكييف وتبريد|emergency|bedroom|gas|now|0
محتاج نقاش يطلي الصالة|دهانات وتشطيبات|normal|living|request|weeks|0
الدهان قشر من على الحيطة جنب الشباك|دهانات وتشطيبات|normal|living|crack|weeks|0
عايز اغير لون الاوضة|دهانات وتشطيبات|normal|bedroom|request|weeks|0
في تشققات كبيرة في السقف وبتكبر|دهانات وتشطيبات|urgent|living|crack|days|0
عايز اركب ارضية باركيه|دهانات وتشطيبات|normal|living|request|weeks|0
قطعة من السقف وقعت|دهانات وتشطيبات|emergency|living|crack|now|0
الباب مش راضي يتفتح|نجارة|urgent|entrance|lock|today|0
مفتاح الباب اتكسر جوه الكالون|نجارة|emergency|entrance|lock|now|0
عايز ادولب في الاوضة بتاعتي|نجارة|normal|bedroom|request|weeks|0
مفصلات الدولاب بتزيق ومحتاجة تتغير|نجارة|normal|bedroom|noise|weeks|0
ضلفة الشباك وقعت|نجارة|normal|bedroom|broken|days|0
عايز اصلح كرسي السفرة|نجارة|normal|living|broken|weeks|0
الغسالة مش بتفتح ومية جواها|أجهزة منزلية|urgent|bath|broken|today|0
ريحة غاز في المطبخ من البوتجاز|أجهزة منزلية|emergency|kitchen|gas|now|0
الفرن الكهربا مش بيسخن|أجهزة منزلية|normal|kitchen|broken|days|0
الغسالة بتسيب مية على الارض|أجهزة منزلية|urgent|bath|leak|today|0
المكنسة الكهربا مبقتش بتشفط|أجهزة منزلية|normal|living|broken|days|0
الميكرويف طلع شرار ودخان|أجهزة منزلية|emergency|kitchen|spark,burn|now|0
الشاشة مش بتفتح خالص|أجهزة منزلية|normal|living|broken|days|0
بنزل مية من اوضة جارنا على سقفنا|سباكة|emergency|bath|leak|now|0
السخان بيقطر ومحتاج صيانة|سباكة|normal|bath|leak|days|0
القاطع الرئيسي بيفصل وبيرجع تاني|كهرباء|urgent|entrance|nopower|days|0
محتاج حد يوزعلي الاضاءة في الشقة الجديدة|كهرباء|normal|other|request|weeks|0
التكييف واقف والجو نار ومعايا اطفال|تكييف وتبريد|urgent|bedroom|broken|today|1
عايز اعمل جبس بورد للسقف|دهانات وتشطيبات|normal|living|request|weeks|0
الكالون مش بيقفل ومحتاج ابقى مطمن|نجارة|urgent|entrance|lock|today|0
البوتجاز الشعلة مش بتولع|أجهزة منزلية|urgent|kitchen|broken|today|0"""
with open("test_form.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["text","category","priority","location","onset","vulnerable"] + [f"sym_{s}" for s in SYMS] + ["split"])
    for i, line in enumerate(T.strip().split("\n")):
        t, c, p, loc, sy, on, v = line.split("|"); sy = set(sy.split(","))
        w.writerow([t, c, p, loc, on, int(v)] + [int(s in sy) for s in SYMS] + ["blind" if i < 24 else "old"])
print(i + 1, "test rows")
