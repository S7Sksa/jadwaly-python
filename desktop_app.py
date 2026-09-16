"""تطبيق جدولي المكتبي: نسخة مستقلة تعمل مباشرة ببايثون وTkinter."""
import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app import DAYS, analyze_schedule, extract_pdf_with_gemini, local_chat, validate_lecture


class LocalUploadedFile:
    """محاكاة بسيطة لكائن رفع Flask حتى نعيد استخدام قارئ PDF في التطبيق المكتبي."""
    def __init__(self, path):
        self.path = path

    def save(self, destination):
        with open(self.path, "rb") as source, open(destination, "wb") as target:
            target.write(source.read())


class JadwalyDesktop(tk.Tk):
    """النافذة الرئيسية التي تجمع الإدخال والتحليل والمساعد الذكي."""

    def __init__(self):
        super().__init__()
        self.title("جدولي | مخطط الطالب الجامعي")
        self.geometry("1120x720")
        self.minsize(900, 600)
        self.lectures = []
        self._configure_style()
        self._build_ui()
        self._refresh()

    def _configure_style(self):
        """توحيد ألوان وخطوط وأحجام عناصر واجهة التطبيق."""
        self.configure(bg="#f6f8fc")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f6f8fc")
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("TLabel", background="#ffffff", foreground="#172033", font=("Arial", 11))
        style.configure("Title.TLabel", background="#f6f8fc", foreground="#302b80", font=("Arial", 22, "bold"))
        style.configure("Sub.TLabel", background="#f6f8fc", foreground="#6e7890", font=("Arial", 11))
        style.configure("TButton", font=("Arial", 10, "bold"), padding=7)
        style.configure("Accent.TButton", background="#6256e8", foreground="white")
        style.configure("Treeview", rowheight=30, font=("Arial", 10))
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"))

    def _build_ui(self):
        """إنشاء الشريط العلوي وعلامات التبويب الرئيسية."""
        header = ttk.Frame(self)
        header.pack(fill="x", padx=24, pady=(20, 8))
        ttk.Label(header, text="جدولي", style="Title.TLabel").pack(anchor="e")
        ttk.Label(header, text="تطبيق سطح مكتب لتنظيم جدولك الجامعي بذكاء", style="Sub.TLabel").pack(anchor="e")

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=10)
        self.entry_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=18)
        self.analysis_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=18)
        self.chat_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=18)
        self.tabs.add(self.entry_tab, text="إضافة الجدول")
        self.tabs.add(self.analysis_tab, text="التحليل")
        self.tabs.add(self.chat_tab, text="المساعد الذكي")
        self._build_entry_tab()
        self._build_analysis_tab()
        self._build_chat_tab()

    def _build_entry_tab(self):
        """بناء شاشة إدخال المحاضرات يدويًا أو من ملف PDF."""
        form = ttk.LabelFrame(self.entry_tab, text="إضافة محاضرة يدويًا", padding=12)
        form.pack(fill="x", pady=(0, 12))
        self.fields = {}
        labels = [("subject", "اسم المادة"), ("doctor", "الدكتور"), ("start", "البداية HH:MM"), ("end", "النهاية HH:MM"), ("room", "القاعة")]
        for column, (key, label) in enumerate(labels):
            ttk.Label(form, text=label).grid(row=0, column=column, padx=5, sticky="e")
            entry = ttk.Entry(form, width=18, justify="right")
            entry.grid(row=1, column=column, padx=5, pady=5)
            self.fields[key] = entry
        ttk.Label(form, text="اليوم").grid(row=0, column=5, padx=5, sticky="e")
        self.day_var = tk.StringVar(value=DAYS[0])
        ttk.Combobox(form, textvariable=self.day_var, values=DAYS, state="readonly", width=14, justify="right").grid(row=1, column=5, padx=5)
        ttk.Button(form, text="إضافة المحاضرة", style="Accent.TButton", command=self._add_lecture).grid(row=1, column=6, padx=12)

        pdf_box = ttk.LabelFrame(self.entry_tab, text="إضافة الجدول من PDF", padding=12)
        pdf_box.pack(fill="x", pady=(0, 12))
        ttk.Label(pdf_box, text="يدعم ملفات PDF المصورة عبر Gemini Vision — ستراجع النتائج قبل اعتمادها").pack(side="right", padx=10)
        ttk.Button(pdf_box, text="اختيار PDF وتحليله", command=self._upload_pdf).pack(side="left")

        actions = ttk.Frame(self.entry_tab)
        actions.pack(fill="x", pady=5)
        ttk.Button(actions, text="حذف الجدول", command=self._clear).pack(side="left")
        ttk.Button(actions, text="حفظ نسخة JSON", command=self._export).pack(side="left", padx=8)
        ttk.Label(actions, text="المحاضرات الحالية", font=("Arial", 12, "bold")).pack(side="right")

        columns = ("subject", "day", "start", "end", "room", "doctor", "kind")
        self.tree = ttk.Treeview(self.entry_tab, columns=columns, show="headings", height=12)
        headings = {"subject": "المادة", "day": "اليوم", "start": "البداية", "end": "النهاية", "room": "القاعة", "doctor": "الدكتور", "kind": "النوع"}
        for key in columns:
            self.tree.heading(key, text=headings[key])
            self.tree.column(key, width=120, anchor="center")
        self.tree.pack(fill="both", expand=True)

    def _build_analysis_tab(self):
        """بناء شاشة عرض مؤشرات ضغط الجدول والاقتراحات."""
        self.analysis_text = tk.Text(self.analysis_tab, wrap="word", height=22, font=("Arial", 13), padx=15, pady=15, bg="#fbfbff", fg="#172033")
        self.analysis_text.pack(fill="both", expand=True)
        self.analysis_text.configure(state="disabled")
        ttk.Button(self.analysis_tab, text="إعادة التحليل", command=self._refresh_analysis).pack(anchor="e", pady=10)

    def _build_chat_tab(self):
        """بناء شاشة المحادثة مع المساعد المحلي المرتبط ببيانات الجدول."""
        self.chat_log = tk.Text(self.chat_tab, wrap="word", height=22, font=("Arial", 12), padx=15, pady=15, bg="#fbfbff", fg="#172033")
        self.chat_log.pack(fill="both", expand=True)
        self.chat_log.insert("end", "المساعد: أهلًا! اسألني عن أفضل يوم للمذاكرة أو أوقات فراغك.\n\n")
        self.chat_log.configure(state="disabled")
        row = ttk.Frame(self.chat_tab)
        row.pack(fill="x", pady=10)
        self.question = ttk.Entry(row, justify="right")
        self.question.pack(side="right", fill="x", expand=True, padx=(0, 8))
        ttk.Button(row, text="إرسال", style="Accent.TButton", command=self._chat).pack(side="left")

    def _add_lecture(self, lecture=None):
        """التحقق من محاضرة جديدة وإضافتها إلى القائمة الداخلية."""
        if lecture is None:
            lecture = {key: entry.get().strip() for key, entry in self.fields.items()}
            lecture.update({"day": self.day_var.get(), "kind": "نظري"})
        if not validate_lecture(lecture):
            messagebox.showwarning("بيانات غير مكتملة", "تأكد من اسم المادة واليوم والوقت، وأن النهاية بعد البداية.")
            return False
        self.lectures.append(lecture)
        self._refresh()
        for entry in self.fields.values():
            entry.delete(0, "end")
        return True

    def _refresh(self):
        """تحديث جدول Treeview وإعادة حساب التحليل بعد أي تغيير."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        for lecture in self.lectures:
            self.tree.insert("", "end", values=tuple(lecture.get(key, "") for key in ("subject", "day", "start", "end", "room", "doctor", "kind")))
        self._refresh_analysis()

    def _refresh_analysis(self):
        """تحويل نتيجة التحليل إلى نص واضح داخل شاشة التحليل."""
        result = analyze_schedule(self.lectures)
        lines = ["ملخص الجدول", "=" * 45, f"إجمالي ساعات المحاضرات: {result['total_hours']} ساعة", f"أكثر يوم ازدحامًا: {result['busiest']['day']}", f"أفضل يوم للمذاكرة: {result['best_day']}", f"مستوى الضغط: {result['pressure']}", f"عدد التعارضات: {len(result['conflicts'])}", "", "الاقتراحات:"]
        lines += [f"• {item}" for item in result["suggestions"]] or ["• أضف محاضرات ليظهر التحليل."]
        if result["longest_gap"]:
            gap = result["longest_gap"]
            lines.append(f"• أطول فراغ: يوم {gap['day']} من الدقيقة {gap['start']} إلى {gap['end']}.")
        self.analysis_text.configure(state="normal")
        self.analysis_text.delete("1.0", "end")
        self.analysis_text.insert("end", "\n".join(lines))
        self.analysis_text.configure(state="disabled")

    def _upload_pdf(self):
        """اختيار PDF، استخراج محاضراته، ثم طلب موافقة المستخدم قبل الحفظ."""
        path = filedialog.askopenfilename(title="اختر جدول PDF", filetypes=[("PDF files", "*.pdf")])
        if not path:
            return
        try:
            lectures, message = extract_pdf_with_gemini(LocalUploadedFile(path))
        except Exception as error:
            messagebox.showerror("خطأ في قراءة PDF", str(error))
            return
        if not lectures:
            messagebox.showinfo("نتيجة التحليل", message)
            return
        preview = "\n".join(f"{i + 1}. {x['subject']} — {x['day']} — {x['start']} إلى {x['end']}" for i, x in enumerate(lectures))
        if messagebox.askyesno("مراجعة المحاضرات", message + "\n\n" + preview + "\n\nهل تريد إضافتها؟"):
            self.lectures.extend(lectures)
            self._refresh()
            messagebox.showinfo("تم", "تمت إضافة محاضرات PDF إلى الجدول.")

    def _chat(self):
        """إرسال سؤال المستخدم إلى المساعد المحلي وعرض الرد في سجل المحادثة."""
        question = self.question.get().strip()
        if not question:
            return
        answer = local_chat(question, self.lectures)
        self.chat_log.configure(state="normal")
        self.chat_log.insert("end", f"أنت: {question}\nالمساعد: {answer}\n\n")
        self.chat_log.configure(state="disabled")
        self.question.delete(0, "end")

    def _clear(self):
        """حذف جميع المحاضرات بعد أخذ تأكيد من المستخدم."""
        if messagebox.askyesno("تأكيد", "هل تريد حذف جميع المحاضرات؟"):
            self.lectures = []
            self._refresh()

    def _export(self):
        """تصدير الجدول الحالي إلى ملف JSON يمكن الاحتفاظ به أو مشاركته."""
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="jadwaly-schedule.json")
        if path:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(self.lectures, file, ensure_ascii=False, indent=2)
            messagebox.showinfo("تم الحفظ", "تم حفظ الجدول بنجاح.")


if __name__ == "__main__":
    JadwalyDesktop().mainloop()
