import unittest
from io import BytesIO
from app import app, analyze_schedule

class JadwalyTests(unittest.TestCase):
    # اختبار اكتشاف تعارض محاضرتين وحساب مجموع الساعات.
    def test_analysis_finds_conflict_and_busy_day(self):
        lectures = [
            {"subject":"برمجة", "day":"الأحد", "start":"09:00", "end":"11:00"},
            {"subject":"رياضيات", "day":"الأحد", "start":"10:30", "end":"12:00"},
            {"subject":"شبكات", "day":"الأربعاء", "start":"13:00", "end":"14:00"},
        ]
        result = analyze_schedule(lectures)
        self.assertEqual(result["busiest"]["day"], "الأحد")
        self.assertEqual(len(result["conflicts"]), 1)
        self.assertEqual(result["total_hours"], 4.5)

    # يجب أن يعمل الشات بوت المحلي حتى بدون إعداد Gemini.
    def test_api_chat_works_without_gemini_key(self):
        client = app.test_client()
        response = client.post('/api/chat', json={"question":"هل عندي تعارض؟", "lectures":[]})
        self.assertEqual(response.status_code, 200)
        self.assertIn("لا يظهر أي تعارض", response.get_json()["answer"])

    # ملفات PDF المصورة تحتاج إلى Gemini Vision لاستخراج محتواها.
    def test_pdf_upload_requires_gemini_for_scanned_files(self):
        client = app.test_client()
        response = client.post('/api/upload-pdf', data={"pdf": (BytesIO(b"not-a-real-pdf"), "schedule.pdf")}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["lectures"], [])

if __name__ == '__main__':
    unittest.main()
