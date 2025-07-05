from flask import make_response, request, redirect, flash
from io import BytesIO, StringIO
from datetime import datetime
import pandas as pd
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from google.cloud import storage
from scripts.utils import build_investor_path, require_investor

def download_confirmation(bucket_name, investor):
    report_date = request.args.get("report_date")
    if not report_date:
        flash("❌ No report date provided.")
        return redirect("/")

    # Initialize GCS client
    gcs = storage.Client()
    bucket = gcs.bucket(bucket_name)

    # Load Receivables and Repayments data
    recv_blob = bucket.blob(
    build_investor_path(investor, "outputs", f"Receivables_Allocated_{report_date}.csv")
)
    df_recv = pd.read_csv(
        StringIO(recv_blob.download_as_text()),
        dtype={"LoanID": str},
        low_memory=False
    )
    repay_blob = bucket.blob(
    build_investor_path(investor, "master", f"HP_Repayments_Master_{report_date}.csv")
)
    df_repay = pd.read_csv(
        StringIO(repay_blob.download_as_text()),
        low_memory=False
    )

    # Compute totals
    total_due      = df_recv["Minimum_Recovery_Amount"].sum()
    total_repaid   = df_repay["HP_Repayment_Amount"].sum()
    net_amount_due = total_due - total_repaid
    today = datetime.now().strftime("%d %B %Y")

    # Setup PDF canvas (A4 with 25 mm margins)
    buffer = BytesIO()
    width, height = A4
    p = canvas.Canvas(buffer, pagesize=A4)
    left = 25 * mm
    right = width - 25 * mm
    y = height - 25 * mm

    # Title & subtitle
    p.setFont("Helvetica-Bold", 16)
    p.drawCentredString(width/2, y, "SCHEDULE 1")
    y -= 8 * mm
    p.setFont("Helvetica", 14)
    p.drawCentredString(width/2, y, "Form of Repayment Request")
    y -= 12 * mm

    # Logos (if present) - commented out for now
    # logo_w = 40 * mm
    # logo_h = 15 * mm
    # try:
    #     img = ImageReader(BytesIO(
    #           bucket.blob(
    #               build_investor_path(investor, "branding", "Logo_Lender.png")
    #           ).download_as_bytes()
    #       ))
    #     p.drawImage(img, left, y, width=logo_w, height=logo_h, mask='auto')
    # except:
    #     pass
    # try:
    #     img = ImageReader(BytesIO(
    #           bucket.blob(
    #               build_investor_path(investor, "branding", "Logo_Borrower.png")
    #           ).download_as_bytes()
    #       ))
    #     p.drawImage(img, right-logo_w, y, width=logo_w, height=logo_h, mask='auto')
    # except:
    #     pass
    # y -= (logo_h + 8 * mm)

    # Parties & agreement
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left, y, "Fin South Africa Proprietary Limited")
    y -= 6 * mm
    p.setFont("Helvetica", 12)
    p.drawString(left, y, "To: Happy Pay Proprietary Limited")
    y -= 6 * mm
    p.drawString(left, y, "Debt Purchase Facility Agreement dated 26 September 2024")
    y -= 12 * mm

    # Date & amount
    p.setFont("Helvetica-Bold", 12)
    p.drawString(left, y, f"Date: {today}")
    y -= 6 * mm
    p.drawString(left, y, f"Amount Due: ZAR {net_amount_due:,.2f}")
    y -= 12 * mm

    # Prepare body text with wrapping
    font_name = "Helvetica"
    font_size = 11
    leading = 16

    text = p.beginText()
    text.setTextOrigin(left, y)
    text.setFont(font_name, font_size)
    text.setLeading(leading)
    max_w = right - left

    body = [
        "Dear Sirs,",
        "",
        "1. We refer to the Agreement. This is a Repayment Request.",
        "",
        "2. Terms defined in the Agreement have the same meaning in this Repayment Request unless expressly stated otherwise.",
        "",
        "3. We confirm that the total amount currently due and payable under the Agreement as at the date of this Repayment Request is:",
        f"   Amount Due: ZAR {net_amount_due:,.2f}",
        "",
        f"4. Please arrange settlement of this amount by no later than {today}.",
        "",
        "5. We include with this Repayment Request:",
        "   (i) A statement of Receivables purchased and outstanding as at this date;",
        "   (ii) A current up-to-date Debtors Age Analysis;",
        "",
        "6. This Repayment Request is irrevocable.",
        "",
        "Yours faithfully,",
        "",
        "___________________________",
        "Authorised Signatory",
        "Fin South Africa Proprietary Limited"
    ]

    for line in body:
        words = line.split()
        cur = ""
        for w in words:
            test = (cur + " " + w).strip()
            if p.stringWidth(test, font_name, font_size) <= max_w:
                cur = test
            else:
                text.textLine(cur)
                cur = w
        text.textLine(cur)

    p.drawText(text)

    # Finish PDF
    p.showPage()
    p.save()
    buffer.seek(0)

    response = make_response(buffer.read())
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = (
        f"attachment; filename=Repayment_Request_{report_date}.pdf"
    )
    return response
