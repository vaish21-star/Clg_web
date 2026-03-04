from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


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


def generate_admission_letter(student):
    file_path = f"static/pdfs/admission_{student['admission_id']}.pdf"
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
        Paragraph(f"Ref. No.: SVP/ADM/{student.get('admission_id', '')}", s["meta"]),
        Paragraph(f"Date: {today}", s["meta"]),
    ]], colWidths=[9.0 * cm, 8.0 * cm])
    meta.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    elements.append(meta)
    elements.append(Spacer(1, 28))
    elements.append(Paragraph("To whomsoever it may concern", s["center"]))
    elements.append(Spacer(1, 18))
    elements.append(Paragraph(
        f"This is to certify that <b>{student.get('student_name', '')}</b> "
        f"(Admission ID: <b>{student.get('admission_id', '')}</b>) is a student of "
        f"<b>{student.get('branch', '')}</b> at Sri Venkateshwara Polytechnic. "
        "This certificate is issued for official purpose.",
        s["body"],
    ))
    elements.append(Spacer(1, 140))
    _sign_block(elements, s)
    elements.append(Spacer(1, 28))
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
