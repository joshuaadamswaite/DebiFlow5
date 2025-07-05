from flask import make_response, request, flash, redirect
from io import BytesIO, StringIO
from datetime import datetime
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from google.cloud import storage
from scripts.utils import build_investor_path, require_investor

def generate_utilisation_request(bucket_name, investor):
    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect("/pending")

    gcs = storage.Client()
    bucket = gcs.bucket(bucket_name)

    # Load Schedule file
    schedule_blob = bucket.blob(build_investor_path(investor, "raw", f"Schedule_{report_date}.csv"))
    df = pd.read_csv(StringIO(schedule_blob.download_as_text()), dtype={"LoanID": str})
    total_purchase = df["Purchase_Consideration"].sum()

    today = datetime.now().strftime("%d %B %Y")

    # Create PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=25*mm, rightMargin=25*mm,
                            topMargin=30*mm, bottomMargin=20*mm)

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    normal.fontName = "Helvetica"
    normal.fontSize = 11
    normal.leading = 16

    story = []

    # Title
    title_style = styles["Title"]
    title_style.fontName = "Helvetica-Bold"
    title_style.fontSize = 14
    story.append(Paragraph("UTILISATION REQUEST", title_style))
    story.append(Spacer(1, 12))

    # Recipient and sender
    story.append(Paragraph("To: Fin South Africa Proprietary Limited", normal))
    story.append(Paragraph("From: Happy Pay Proprietary Limited", normal))
    story.append(Paragraph("Debt Purchase Facility Agreement dated 27 June 2025", normal))
    story.append(Spacer(1, 12))

    # Date and totals
    story.append(Paragraph(f"Date: {today}", normal))
    story.append(Paragraph(f"Reporting Date: {report_date}", normal))
    story.append(Paragraph(f"Total Purchase Consideration: ZAR {total_purchase:,.2f}", normal))
    story.append(Spacer(1, 12))

    # Body paragraphs
    body_paragraphs = [
        "Dear Sirs,",
        "",
        "1. We refer to the Agreement. This is a Utilisation Request.",
        "",
        "2. Terms defined in the Agreement have the same meaning in this Utilisation Request, unless given a different meaning herein.",
        "",
        "3. We wish to conclude a Purchase on the following terms:",
        "",
        f"&emsp;Proposed Utilisation Date: {today}<br/>"
        f"&emsp;Purchase Consideration (aggregate): ZAR {total_purchase:,.2f}<br/>"
        "&emsp;Happy Pay Receivables: See schedule attached.",
        "",
        "4. We –",
        "&emsp;(i) Include with this Utilisation Request copies of the Instalment Plans applicable to such Receivables, a schedule of Receivable Outstandings and a current Debtors Age Analysis; and",
        "&emsp;(ii) Confirm that each Purchase Condition has been satisfied.",
        "",
        "5. This Utilisation Request is irrevocable.",
        "",
        "Yours faithfully,",
        "",
        "",
        "______________________________<br/>"
        "Authorised Signatory<br/>"
        "Happy Pay Proprietary Limited"
    ]

    for para in body_paragraphs:
        if para.strip() == "":
            story.append(Spacer(1, 12))
        else:
            story.append(Paragraph(para, normal))

    doc.build(story)

    buffer.seek(0)
    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=Utilisation_Request_{report_date}.pdf"
    return response
