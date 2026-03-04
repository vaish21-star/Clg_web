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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.join(BASE_DIR, "static", "pdfs")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(PDF_DIR, exist_ok=True)


def _resolve_photo_path(photo_filename):
    if not photo_filename:
        return None
    candidates = [
        os.path.join(UPLOAD_DIR, photo_filename),
        os.path.join("static", "uploads", photo_filename),
        os.path.join(os.getcwd(), "static", "uploads", photo_filename),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _val(value):
    if value is None:
        return "-"
    txt = str(value).strip()
    return txt if txt else "-"


def _section_title(text):
    t = Table([[text]], colWidths=[17.0 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef4ff")),
        ("FONTNAME", (0, 0), (-1, -1), "Times-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 12),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#112b55")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#cad8f2")),
    ]))
    return t


def _kv_table(rows):
    data = []
    for left_label, left_value, right_label, right_value in rows:
        data.append([left_label, _val(left_value), right_label, _val(right_value)])
    tbl = Table(data, colWidths=[3.0 * cm, 5.5 * cm, 3.0 * cm, 5.5 * cm])
    tbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#444444")),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTNAME", (3, 0), (3, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def generate_admission_letter(student, photo_filename=None):
    file_path = os.path.join(PDF_DIR, f"admission_{student['admission_id']}.pdf")
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
    today = datetime.now().strftime("%d-%m-%Y")
    meta = Table([[
        Paragraph(f"Application No.: {student.get('admission_id', '')}", s["meta"]),
        Paragraph(f"Generated On: {today}", s["meta"]),
    ]], colWidths=[9.0 * cm, 8.0 * cm])
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(meta)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("ADMISSION APPLICATION DETAILS", s["center"]))
    elements.append(Spacer(1, 8))

    photo = None
    photo_path = _resolve_photo_path(photo_filename)
    if photo_path:
        try:
            photo = Image(photo_path, width=3.0 * cm, height=3.8 * cm)
        except Exception:
            photo = None

    basic_rows = [
        ("Student Name", student.get("student_name"), "Admission ID", student.get("admission_id")),
        ("Branch", student.get("branch"), "Status", student.get("status")),
        ("Mobile", student.get("student_mobile") or student.get("mobile"), "Email", student.get("student_email")),
        ("Date of Birth", student.get("dob"), "Gender", student.get("gender")),
    ]
    basic_tbl = _kv_table(basic_rows)
    photo_cell = photo if photo else Paragraph("Photo Not Available", s["meta"])
    top = Table([[basic_tbl, photo_cell]], colWidths=[13.8 * cm, 3.2 * cm])
    top.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("BOX", (1, 0), (1, 0), 0.7, colors.HexColor("#444444")),
    ]))
    elements.append(top)
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Personal Details"))
    elements.append(Spacer(1, 4))
    elements.append(_kv_table([
        ("Nationality", student.get("indian_nationality"), "Religion", student.get("religion")),
        ("Caste Category", student.get("caste_category"), "Alloted Category", student.get("alloted_category")),
        ("Admission Quota", student.get("admission_quota"), "Register Number", student.get("register_number")),
    ]))
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Academic Details"))
    elements.append(Spacer(1, 4))
    elements.append(_kv_table([
        ("Qualifying Exam", student.get("qualifying_exam"), "Marks Exam Type", student.get("marks_exam_type")),
        ("Year Of Passing", student.get("year_of_passing"), "Total Max Marks", student.get("total_max_marks")),
        ("Total Marks Obtained", student.get("total_marks_obtained"), "Percentage", student.get("percentage")),
        ("Science Marks", student.get("science_marks_obtained"), "Maths Marks", student.get("maths_marks_obtained")),
    ]))
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Parent Details"))
    elements.append(Spacer(1, 4))
    elements.append(_kv_table([
        ("Father Name", student.get("father_name"), "Father Mobile", student.get("father_mobile")),
        ("Mother Name", student.get("mother_name"), "Mother Mobile", student.get("mother_mobile")),
    ]))
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Address Details"))
    elements.append(Spacer(1, 4))
    addr = Table([
        ["Residential Address", _val(student.get("residential_address"))],
        ["Permanent Address", _val(student.get("permanent_address"))],
    ], colWidths=[4.5 * cm, 12.5 * cm])
    addr.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.7, colors.HexColor("#444444")),
        ("FONTNAME", (0, 0), (0, -1), "Times-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    elements.append(addr)
    elements.append(Spacer(1, 8))

    elements.append(_section_title("Document Numbers"))
    elements.append(Spacer(1, 4))
    elements.append(_kv_table([
        ("Aadhaar Number", student.get("aadhaar_number"), "Caste RD Number", student.get("caste_rd_number")),
        ("Income RD Number", student.get("income_rd_number"), "Generated Date", today),
    ]))
    elements.append(Spacer(1, 24))
    _sign_block(elements, s)
    elements.append(Spacer(1, 16))
    elements.append(_line())
    foot = Table([[
        Paragraph("E-mail ID: srivenkateshwara364@gmail.com", s["meta"]),
        Paragraph("Website: www.svpolytechnic.edu.in", s["meta"]),
    ]], colWidths=[8.5 * cm, 8.5 * cm])
    foot.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(foot)

    doc.build(elements)
    return file_path


def generate_fee_receipt(student, fees):
    receipt_no = str(fees.get("receipt_no") or student.get("admission_id") or "receipt")
    safe_receipt = "".join(ch for ch in receipt_no if ch.isalnum() or ch in ("-", "_"))
    file_path = os.path.join(PDF_DIR, f"fee_receipt_{safe_receipt}.pdf")
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
