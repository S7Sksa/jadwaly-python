import json
import os
import re
import base64
import subprocess
import tempfile
from datetime import datetime
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# الأيام الدراسية المدعومة في النسخة الحالية من التطبيق.
DAYS = ["الأحد", "الاثنين", "الثلاثاء", "الأربعاء", "الخميس"]
DAY_INDEX = {day: i for i, day in enumerate(DAYS)}


def to_minutes(value):
    """تحويل الوقت من HH:MM إلى دقائق لتسهيل المقارنة والحساب."""
    try:
        hour, minute = [int(part) for part in value.split(":")]
        return hour * 60 + minute
    except (ValueError, AttributeError):
        return None


def format_minutes(total):
    hour = (total // 60) % 24
    minute = total % 60
    suffix = "صباحًا" if hour < 12 else "مساءً"
    display = hour % 12 or 12
    return f"{display}:{minute:02d} {suffix}"


def validate_lecture(item):
    """التأكد من اكتمال بيانات المحاضرة وأن وقت النهاية بعد البداية."""
    required = ["subject", "day", "start", "end"]
    if any(not str(item.get(key, "")).strip() for key in required):
        return False
    start, end = to_minutes(item["start"]), to_minutes(item["end"])
    return item["day"] in DAYS and start is not None and end is not None and end > start


def analyze_schedule(lectures):
    """إنشاء ملخص إحصائي للجدول دون الحاجة إلى خدمة ذكاء اصطناعي."""
    valid = [x for x in lectures if validate_lecture(x)]
    by_day = {day: [] for day in DAYS}
    for lecture in valid:
        lecture = dict(lecture)
        lecture["start_min"] = to_minutes(lecture["start"])
        lecture["end_min"] = to_minutes(lecture["end"])
        by_day[lecture["day"]].append(lecture)
    daily = []
    all_gaps = []
    conflicts = []
    # ترتيب محاضرات كل يوم يسمح باكتشاف التعارضات والفجوات الزمنية.
    for day in DAYS:
        items = sorted(by_day[day], key=lambda x: x["start_min"])
        hours = sum(x["end_min"] - x["start_min"] for x in items) / 60
        gaps = []
        for previous, current in zip(items, items[1:]):
            gap = current["start_min"] - previous["end_min"]
            if gap < 0:
                conflicts.append({"day": day, "first": previous["subject"], "second": current["subject"]})
            elif gap > 0:
                gaps.append({"start": previous["end_min"], "end": current["start_min"], "minutes": gap})
                all_gaps.append({"day": day, **gaps[-1]})
        daily.append({"day": day, "lectures": len(items), "hours": round(hours, 1), "gaps": [{**g, "label": f"{format_minutes(g['start'])} - {format_minutes(g['end'])}"} for g in gaps]})
    busiest = max(daily, key=lambda x: (x["lectures"], x["hours"]), default={"day": "-", "lectures": 0, "hours": 0})
    total_hours = round(sum(item["hours"] for item in daily), 1)
    pressure = "منخفض" if total_hours < 12 and len(conflicts) == 0 else "متوسط" if total_hours < 22 and len(conflicts) == 0 else "مرتفع"
    best_day = min(daily, key=lambda x: (x["lectures"], -len(x["gaps"])), default={"day": "-"})
    longest_gap = max(all_gaps, key=lambda x: x["minutes"], default=None)
    suggestions = []
    if longest_gap:
        suggestions.append(f"استغل فراغك الأطول يوم {longest_gap['day']} من {format_minutes(longest_gap['start'])} إلى {format_minutes(longest_gap['end'])} للمراجعة.")
    if busiest.get("lectures", 0) >= 4:
        suggestions.append(f"يوم {busiest['day']} مزدحم؛ حضّر موادك مسبقًا وخذ استراحة قصيرة بين المحاضرات.")
    if best_day.get("day") != "-":
        suggestions.append(f"يوم {best_day['day']} مناسب للمذاكرة لأنه الأقل ازدحامًا.")
    if conflicts:
        suggestions.append("يوجد تعارض في مواعيد محاضراتك؛ راجع البيانات أو تواصل مع القسم.")
    return {"daily": daily, "total_hours": total_hours, "busiest": busiest, "pressure": pressure, "best_day": best_day.get("day", "-"), "longest_gap": longest_gap, "conflicts": conflicts, "suggestions": suggestions}


def local_chat(question, lectures):
    """ردود محلية سريعة تعمل كخطة بديلة عند عدم وجود مفتاح Gemini."""
    analysis = analyze_schedule(lectures)
    q = question.lower()
    if any(word in q for word in ["مذاكرة", "مذاكر", "study"]):
        return f"أفضل وقت مبدئي للمذاكرة هو يوم {analysis['best_day']}. ولديك فراغ مناسب: {analysis['longest_gap']['day']} من {format_minutes(analysis['longest_gap']['start'])} إلى {format_minutes(analysis['longest_gap']['end'])}." if analysis['longest_gap'] else f"يوم {analysis['best_day']} هو الأقل ازدحامًا للمذاكرة."
    if any(word in q for word in ["فراغ", "free"]):
        return f"مجموع ساعات المحاضرات المسجلة هذا الأسبوع هو {analysis['total_hours']} ساعة. راجع بطاقات الفراغ في التحليل لمعرفة الأوقات بالتفصيل."
    if any(word in q for word in ["تداخل", "تعارض", "overlap"]):
        return "نعم، يوجد تعارض: " + "، ".join(f"{x['day']} بين {x['first']} و{x['second']}" for x in analysis["conflicts"]) if analysis["conflicts"] else "لا يظهر أي تعارض بين المحاضرات المسجلة."
    if any(word in q for word in ["متوازن", "جدول"]):
        return f"ضغط جدولك {analysis['pressure']}، وأكثر يوم ازدحامًا هو {analysis['busiest']['day']} بعدد {analysis['busiest']['lectures']} محاضرات."
    return "أستطيع مساعدتك في معرفة أفضل يوم للمذاكرة، أوقات الفراغ، التعارضات، وضغط الجدول. جرّب سؤالًا أكثر تحديدًا."


def gemini_chat(question, lectures):
    """إرسال سؤال الطالب وجدوله إلى Gemini مع الرجوع للتحليل المحلي عند الفشل."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return local_chat(question, lectures), False
    try:
        import urllib.request
        prompt = "أنت مساعد جامعي عربي. أجب باختصار وبشكل عملي بناءً على جدول الطالب التالي:\n" + json.dumps(lectures, ensure_ascii=False) + "\nسؤال الطالب: " + question
        payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read())
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        return answer, True
    except Exception:
        return local_chat(question, lectures), False


def extract_pdf_with_gemini(pdf_file):
    """تحويل أول صفحة PDF إلى صورة وقراءة المحاضرات عبر Gemini Vision."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return [], "لم يتم ضبط GEMINI_API_KEY. أضف المفتاح من إعدادات التشغيل لقراءة الجدول المصوّر تلقائيًا."
    with tempfile.TemporaryDirectory() as directory:
        pdf_path = os.path.join(directory, "schedule.pdf")
        image_prefix = os.path.join(directory, "page")
        pdf_file.save(pdf_path)
        subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-png", "-r", "180", pdf_path, image_prefix], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with open(image_prefix + "-1.png", "rb") as image:
            image_data = base64.b64encode(image.read()).decode("ascii")
    # نطلب JSON من النموذج حتى نستطيع التحقق من النتائج قبل عرضها للمستخدم.
    prompt = '''اقرأ جدول المحاضرات الجامعي من الصورة. أرجع JSON فقط بهذا الشكل:
{"lectures":[{"subject":"اسم المادة","doctor":"اسم الدكتور","day":"الأحد أو الاثنين أو الثلاثاء أو الأربعاء أو الخميس","start":"HH:MM","end":"HH:MM","room":"رقم القاعة","kind":"نظري أو عملي أو مشروع"}]}
حوّل الأوقات إلى نظام 24 ساعة. لا تضف بيانات الطالب أو المجموع، ولا تخمّن صفوفًا غير موجودة.'''
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/png", "data": image_data}}]}], "generationConfig": {"responseMimeType": "application/json"}}
    try:
        import urllib.request
        body = json.dumps(payload).encode()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=45) as response:
            data = json.loads(response.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        lectures = [item for item in parsed.get("lectures", []) if validate_lecture(item)]
        return lectures, f"تم استخراج {len(lectures)} محاضرات. راجع البيانات قبل الإضافة."
    except Exception as error:
        return [], f"تعذر قراءة الـPDF تلقائيًا: {error}"


@app.get("/")
def home():
    # الواجهة كلها موجودة في قالب HTML واحد لتسهيل تشغيل النسخة الأولية.
    return render_template("index.html")


@app.post("/api/analyze")
def api_analyze():
    # تحليل الجدول يتم محليًا حتى يعمل التطبيق حتى بدون Gemini.
    data = request.get_json(silent=True) or {}
    lectures = data.get("lectures", [])
    return jsonify(analyze_schedule(lectures))


@app.post("/api/chat")
def api_chat():
    data = request.get_json(silent=True) or {}
    answer, used_gemini = gemini_chat(str(data.get("question", "")), data.get("lectures", []))
    return jsonify({"answer": answer, "used_gemini": used_gemini})


@app.post("/api/upload-pdf")
def api_upload_pdf():
    # استقبال الملف من المتصفح وعدم حفظه بشكل دائم على الخادم.
    uploaded = request.files.get("pdf")
    if not uploaded or not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"lectures": [], "message": "اختر ملف PDF صحيحًا."}), 400
    try:
        lectures, message = extract_pdf_with_gemini(uploaded)
        return jsonify({"lectures": lectures, "message": message, "used_gemini": bool(lectures)})
    except (subprocess.CalledProcessError, FileNotFoundError):
        return jsonify({"lectures": [], "message": "أداة تحويل PDF غير متوفرة على الخادم."}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=True)
