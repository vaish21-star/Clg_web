import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "title",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=30,
            alignment=1,
            leading=34,
        ),
        "sub": ParagraphStyle(
            "sub",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            alignment=1,
            leading=16,
        ),
        "dept": ParagraphStyle(
            "dept",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=18,
            alignment=1,
            leading=22,
        ),
        "meta": ParagraphStyle(
            "meta",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=12,
            leading=15,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=13,
            leading=22,
            alignment=4,
        ),
        "center": ParagraphStyle(
            "center",
            parent=base["Normal"],
            fontName="Times-Bold",
            fontSize=16,
            alignment=1,
        ),
        "small_center": ParagraphStyle(
            "small_center",
            parent=base["Normal"],
            fontName="Times-Roman",
            fontSize=11,
            alignment=1,
        ),
    }


def _line():
    t = Table([[""]], colWidths=[17.0 * cm], rowHeights=[0.1 * cm])
    t.setStyle(TableStyle([("LINEABOVE", (0, 0), (-1, -1), 1.2, colors.black)]))
    return t


def _header(elements, s):
    elements.append(Paragraph("Sri Venkateshwara Polytechnic", s["title"]))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        "(A Unit of Nehru Smaraka Vidya Kendra Trust, Bangalore)<br/>"
        "Recognised by AICTE New Delhi and Govt. of Karnataka<br/>"
        "Jangalpalya, Bannerghatta, Bengaluru - 560 083",
        s["sub"],
    ))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph("Department of Computer Science &amp; Engg.", s["dept"]))
    elements.append(Spacer(1, 4))
    elements.append(_line())
    elements.append(Spacer(1, 10))


def _sign_block(elements, s):
    sign = Table(
        [[
            Paragraph("<b>______________________________</b><br/><b>Signature of Program Co-Ordinator</b>", s["small_center"]),
            Paragraph("<b>______________________________</b><br/><b>Signature of Principal</b>", s["small_center"]),
        ]],
        colWidths=[8.4 * cm, 8.4 * cm],
    )
    sign.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    elements.append(sign)


def _safe_text(value):
    if value is None:
        return "-"
    text = str(value).strip()
    return text if text else "-"


def _marks_text(obtained, maximum):
    if obtained in (None, "") or maximum in (None, ""):
        return "-"
    return f"{obtained}/{maximum}"


def _section_title(text):
    t = Table([[text]], colWidths=[17.0 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f5f5")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#6a6a6a")),
        ("FONTNAME", (0, 0), (-1, -1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


def _detail_grid(rows):
    t = Table(rows, colWidths=[3.1 * cm, 5.4 * cm, 3.1 * cm, 5.4 * cm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#7a7a7a")),
        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def generate_admission_letter(student, personal=None, education=None, docs=None, fee_summary=None):
    file_path = f"static/pdfs/admission_{student['admission_id']}.pdf"
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=0.9 * cm,
        bottomMargin=0.9 * cm,
    )
    elements = []

    personal = personal or {}
    education = education or {}
    docs = docs or {}
    generated_on = datetime.now().strftime("%d-%m-%Y")

    top_meta = Table([[
        f"Application No.: {_safe_text(student.get('admission_id'))}",
        f"Generated On: {generated_on}",
    ]], colWidths=[8.5 * cm, 8.5 * cm])
    top_meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    elements.append(top_meta)
    elements.append(Spacer(1, 4))

    title = Table([["ADMISSION APPLICATION DETAILS"]], colWidths=[17.0 * cm])
    title.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 16),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(title)
    elements.append(Spacer(1, 4))

    student_rows = [
        ["Student Name", _safe_text(student.get("student_name")), "Admission ID", _safe_text(student.get("admission_id"))],
        ["Branch", _safe_text(student.get("branch")), "Status", _safe_text(student.get("status"))],
        ["Mobile", _safe_text(personal.get("student_mobile") or student.get("mobile")), "Email", _safe_text(personal.get("student_email"))],
        ["Date of Birth", _safe_text(personal.get("dob")), "Gender", _safe_text(personal.get("gender"))],
    ]
    student_table = _detail_grid(student_rows)

    photo_path = None
    if docs.get("student_photo"):
        candidate = os.path.join("static", "uploads", str(docs.get("student_photo")))
        if os.path.exists(candidate):
            photo_path = candidate

    photo_cell = "Photo Not Available"
    if photo_path:
        img = Image(photo_path, width=2.4 * cm, height=3.0 * cm)
        photo_cell = Table([[img]], colWidths=[2.6 * cm], rowHeights=[3.2 * cm])
        photo_cell.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#7a7a7a")),
        ]))

    head_block = Table([[student_table, photo_cell]], colWidths=[14.1 * cm, 2.9 * cm])
    head_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(head_block)
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Personal Details"))
    elements.append(_detail_grid([
        ["Nationality", _safe_text(personal.get("indian_nationality")), "Religion", _safe_text(personal.get("religion"))],
        ["Caste Category", _safe_text(personal.get("caste_category")), "Alloted Category", _safe_text(personal.get("alloted_category"))],
        ["Admission Quota", _safe_text(personal.get("admission_quota")), "Register Number", _safe_text(personal.get("register_number") or education.get("register_number"))],
    ]))
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Academic Details"))
    elements.append(_detail_grid([
        ["Qualifying Exam", _safe_text(personal.get("qualifying_exam") or education.get("qualifying_exam")), "Marks Exam Type", _safe_text(personal.get("qualifying_exam") or education.get("qualifying_exam"))],
        ["Year Of Passing", _safe_text(personal.get("year_of_passing") or education.get("year_of_passing")), "Total Max Marks", _safe_text(education.get("total_max_marks"))],
        ["Total Marks Obtained", _safe_text(education.get("total_marks_obtained")), "Percentage", _safe_text(education.get("percentage"))],
        ["Science Marks", _marks_text(education.get("science_marks_obtained"), education.get("science_max_marks")), "Maths Marks", _marks_text(education.get("maths_marks_obtained"), education.get("maths_max_marks"))],
    ]))
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Parent Details"))
    elements.append(_detail_grid([
        ["Father Name", _safe_text(personal.get("father_name")), "Father Mobile", _safe_text(personal.get("father_mobile"))],
        ["Mother Name", _safe_text(personal.get("mother_name")), "Mother Mobile", _safe_text(personal.get("mother_mobile"))],
    ]))
    elements.append(Spacer(1, 8))

    if fee_summary:
        elements.append(_section_title("Fee Details"))
        elements.append(_detail_grid([
            ["Academic Year", _safe_text(fee_summary.get("academic_year")), "Current Sem", _safe_text(fee_summary.get("current_sem"))],
            ["Total Due", _safe_text(fee_summary.get("total_due")), "Total Paid", _safe_text(fee_summary.get("total_paid"))],
            ["Balance", _safe_text(fee_summary.get("balance")), "Fee State", _safe_text(fee_summary.get("payment_state"))],
        ]))
        elements.append(Spacer(1, 8))

    address_rows = [
        ["Residential Address", _safe_text(personal.get("residential_address"))],
        ["Permanent Address", _safe_text(personal.get("permanent_address"))],
    ]
    address_table = Table(address_rows, colWidths=[3.8 * cm, 13.2 * cm])
    address_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.8, colors.HexColor("#7a7a7a")),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(_section_title("Address Details"))
    elements.append(address_table)

    doc.build(elements)
    return file_path


def generate_fee_receipt(student, fees):
    receipt_no = str(fees.get("receipt_no") or student.get("admission_id") or "receipt")
    safe_receipt = "".join(ch for ch in receipt_no if ch.isalnum() or ch in ("-", "_"))
    file_path = f"static/pdfs/fee_receipt_{safe_receipt}.pdf"
    s = _styles()
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.3 * cm,
    )
    elements = []

    _header(elements, s)
    elements.append(Paragraph("OFFICIAL FEE RECEIPT", s["center"]))
    elements.append(Spacer(1, 10))

    date_text = fees.get("payment_date") or datetime.now().strftime("%d-%m-%Y")
    ref_text = fees.get("receipt_no") or f"SVP/FEE/{student.get('admission_id', '')}"
    meta = Table([[
        Paragraph(f"Ref. No.: {ref_text}", s["meta"]),
        Paragraph(f"Date: {date_text}", s["meta"]),
    ]], colWidths=[9.0 * cm, 8.0 * cm])
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(meta)
    elements.append(Spacer(1, 12))

    admission_fee = float(fees.get("admission_fee", 0) or 0)
    tuition_fee = float(fees.get("tuition_fee", 0) or 0)
    management_fee = float(fees.get("management_fee", 0) or 0)
    exam_fee = float(fees.get("exam_fee", 0) or 0)
    total_paid = round(admission_fee + tuition_fee + management_fee + exam_fee, 2)
    payment_type = fees.get("payment_type") or fees.get("payment_status") or "-"

    info = Table([
        ["Admission ID", student.get("admission_id", "")],
        ["Student Name", student.get("student_name", "")],
        ["Branch", student.get("branch", "")],
        ["Payment Type", str(payment_type)],
        ["Receipt No", str(ref_text)],
        ["Academic Year", str(fees.get("academic_year", "-"))],
        ["Semester", str(fees.get("semester_no", "-"))],
    ], colWidths=[5.2 * cm, 11.8 * cm])
    info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(info)
    elements.append(Spacer(1, 10))

    amt = Table([
        ["Admission Fee", f"Rs {admission_fee:.2f}"],
        ["Tuition Fee", f"Rs {tuition_fee:.2f}"],
        ["Management Fee", f"Rs {management_fee:.2f}"],
        ["Exam Fee", f"Rs {exam_fee:.2f}"],
        ["Total Paid", f"Rs {total_paid:.2f}"],
    ], colWidths=[8.5 * cm, 8.5 * cm])
    amt.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
    ]))
    elements.append(amt)
    elements.append(Spacer(1, 22))
    elements.append(Paragraph(
        "Received the above amount towards fee payment for official academic records.",
        s["body"],
    ))
    elements.append(Spacer(1, 85))
    _sign_block(elements, s)
    elements.append(Spacer(1, 24))
    elements.append(_line())
    foot = Table([[
        Paragraph("E-mail ID: srivenkateshwara364@gmail.com", s["meta"]),
        Paragraph("Website: www.svpolytechnic.edu.in", s["meta"]),
    ]], colWidths=[8.5 * cm, 8.5 * cm])
    foot.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(foot)

    doc.build(elements)
    return file_path


def generate_students_list_pdf(students, title_text="Student Records", filter_text=""):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"static/pdfs/students_{stamp}.pdf"
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=1 * cm,
        rightMargin=1 * cm,
        topMargin=1 * cm,
        bottomMargin=1 * cm,
    )
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("SRI VENKATESHWARA POLYTECHNIC", ParagraphStyle(
        "h1", parent=styles["Normal"], fontName="Times-Bold", fontSize=15, alignment=1
    )))
    elements.append(Paragraph(title_text, ParagraphStyle(
        "h2", parent=styles["Normal"], fontName="Times-Bold", fontSize=12, alignment=1
    )))
    if filter_text:
        elements.append(Paragraph(filter_text, ParagraphStyle(
            "meta", parent=styles["Normal"], fontName="Times-Roman", fontSize=9, alignment=1
        )))
    elements.append(Spacer(1, 8))

    rows = [[
        "SI", "Name", "Admission ID", "Reg No", "Branch", "Gender", "Mobile", "Caste", "Allotted", "Status"
    ]]
    for idx, s in enumerate(students or [], start=1):
        rows.append([
            str(idx),
            str(s.get("student_name") or "-"),
            str(s.get("admission_id") or "-"),
            str(s.get("college_reg_no") or "-"),
            str(s.get("branch") or "-"),
            str(s.get("gender") or "-"),
            str(s.get("mobile") or "-"),
            str(s.get("caste_category") or "-"),
            str(s.get("alloted_category") or "-"),
            str(s.get("status") or "-"),
        ])

    table = Table(rows, colWidths=[0.8 * cm, 2.6 * cm, 2.4 * cm, 2.2 * cm, 2.5 * cm, 1.4 * cm, 2.0 * cm, 1.6 * cm, 1.8 * cm, 1.5 * cm])
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececec")),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (9, 0), (9, -1), "CENTER"),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        f"Generated On: {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        ParagraphStyle("foot", parent=styles["Normal"], fontName="Times-Roman", fontSize=9, alignment=2)
    ))

    doc.build(elements)
    return file_path


def generate_results_summary_pdf(rows, filter_text=""):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"static/pdfs/results_summary_{stamp}.pdf"
    doc = SimpleDocTemplate(
        file_path, pagesize=A4, leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm, bottomMargin=1 * cm
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("SRI VENKATESHWARA POLYTECHNIC", ParagraphStyle("rt1", parent=styles["Normal"], fontName="Times-Bold", fontSize=15, alignment=1)),
        Paragraph("Student Result Summary", ParagraphStyle("rt2", parent=styles["Normal"], fontName="Times-Bold", fontSize=12, alignment=1)),
    ]
    if filter_text:
        elements.append(Paragraph(filter_text, ParagraphStyle("rt3", parent=styles["Normal"], fontName="Times-Roman", fontSize=9, alignment=1)))
    elements.append(Spacer(1, 8))

    data = [["SI", "Name", "Reg No", "Sem", "Branch", "Result", "%", "CGPA"]]
    for i, r in enumerate(rows or [], start=1):
        data.append([
            str(i),
            str(r.get("student_name") or "-"),
            str(r.get("register_number") or "-"),
            str(r.get("semester_no") or "-"),
            str(r.get("branch") or "-"),
            str(r.get("final_result") or "-"),
            str(r.get("percentage") or "-"),
            str(r.get("cgpa") or "-"),
        ])
    t = Table(data, colWidths=[0.8 * cm, 3.2 * cm, 2.8 * cm, 1.2 * cm, 2.8 * cm, 2.4 * cm, 1.8 * cm, 1.6 * cm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececec")),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)
    doc.build(elements)
    return file_path


def generate_result_student_pdf(summary, subject_rows):
    reg_no = str((summary or {}).get("register_number") or "result")
    safe = "".join(ch for ch in reg_no if ch.isalnum() or ch in ("-", "_"))
    file_path = f"static/pdfs/result_{safe}.pdf"
    doc = SimpleDocTemplate(
        file_path, pagesize=A4, leftMargin=1 * cm, rightMargin=1 * cm, topMargin=1 * cm, bottomMargin=1 * cm
    )
    styles = getSampleStyleSheet()
    elements = [
        Paragraph("SRI VENKATESHWARA POLYTECHNIC", ParagraphStyle("sr1", parent=styles["Normal"], fontName="Times-Bold", fontSize=15, alignment=1)),
        Paragraph("Student Result Detail", ParagraphStyle("sr2", parent=styles["Normal"], fontName="Times-Bold", fontSize=12, alignment=1)),
        Spacer(1, 6),
    ]
    info = Table([
        ["Name", str(summary.get("student_name") or "-"), "Reg No", str(summary.get("register_number") or "-")],
        ["Branch", str(summary.get("branch") or "-"), "Sem", str(summary.get("semester_no") or "-")],
        ["Final Result", str(summary.get("final_result") or "-"), "CGPA", str(summary.get("cgpa") or "-")],
        ["Percentage", str(summary.get("percentage") or "-"), "Exam Session", str(summary.get("exam_session") or "-")],
    ], colWidths=[2.8 * cm, 5.4 * cm, 2.8 * cm, 5.4 * cm])
    info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTNAME", (3, 0), (3, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
    ]))
    elements.append(info)
    elements.append(Spacer(1, 8))

    subject_data = [["SI", "Sem", "QP Code", "Subject", "IA", "TR", "PR", "Result", "Credit", "Grade"]]
    for i, s in enumerate(subject_rows or [], start=1):
        subject_data.append([
            str(i),
            str(s.get("semester_no") or "-"),
            str(s.get("subject_code") or "-"),
            str(s.get("subject_name") or "-"),
            str(s.get("ia_marks") or "-"),
            str(s.get("theory_marks") or "-"),
            str(s.get("practical_marks") or "-"),
            str(s.get("result_status") or "-"),
            str(s.get("credit") or "-"),
            str(s.get("grade") or "-"),
        ])
    st = Table(subject_data, colWidths=[0.7 * cm, 1.0 * cm, 1.8 * cm, 4.4 * cm, 1.0 * cm, 1.0 * cm, 1.0 * cm, 1.8 * cm, 1.2 * cm, 1.2 * cm])
    st.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ececec")),
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    elements.append(st)
    doc.build(elements)
    return file_path
