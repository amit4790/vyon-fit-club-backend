"""Reusable PDF invoice renderer."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass
class InvoicePdfPayload:
    invoice_number: str
    invoice_date: date
    member_name: str
    member_phone: str | None
    member_email: str | None
    plan_label: str
    duration_label: str
    start_date: date
    end_date: date
    original_price: float
    discount_amount: float
    taxable_amount: float
    gst_amount: float
    total_paid: float
    payment_mode: str
    transaction_reference: str | None


class InvoicePdfService:
    """Render invoice PDFs with a layout that is easy to replace later."""

    def __init__(self, root_dir: str | Path | None = None):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parents[1] / "storage" / "invoices"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _money(value: float) -> str:
        return f"INR {value:,.2f}"

    @staticmethod
    def _escape_pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _build_pdf_bytes(self, lines: list[str]) -> bytes:
        stream_lines = ["BT", "/F1 11 Tf", "1 0 0 1 50 790 Tm", "15 TL"]

        for index, line in enumerate(lines):
            escaped = self._escape_pdf_text(line)
            if index > 0:
                stream_lines.append("T*")
            stream_lines.append(f"({escaped}) Tj")

        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")

        objects: list[bytes] = []
        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        objects.append(
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        )
        objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
        objects.append(
            f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream\nendobj\n"
        )

        pdf = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(len(pdf))
            pdf.extend(obj)

        xref_start = len(pdf)
        pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
        pdf.extend(b"0000000000 65535 f \n")

        for offset in offsets[1:]:
            pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

        pdf.extend(
            (
                f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                f"startxref\n{xref_start}\n%%EOF"
            ).encode("latin-1")
        )
        return bytes(pdf)

    def render_invoice_pdf(self, payload: InvoicePdfPayload) -> str:
        file_name = f"{payload.invoice_number}.pdf"
        output_path = self.root_dir / file_name
        lines = [
            "VYON FIT CLUB",
            "Invoice",
            "",
            f"Invoice Number: {payload.invoice_number}",
            f"Invoice Date: {payload.invoice_date.isoformat()}",
            "",
            "Member Details",
            f"Member Name: {payload.member_name}",
            f"Member Phone: {payload.member_phone or '-'}",
            f"Member Email: {payload.member_email or '-'}",
            "",
            "Membership",
            f"Plan: {payload.plan_label}",
            f"Duration: {payload.duration_label}",
            f"Start Date: {payload.start_date.isoformat()}",
            f"Expiry Date: {payload.end_date.isoformat()}",
            "",
            "Payment Summary",
            f"Original Membership Price: {self._money(payload.original_price)}",
            f"Discount Amount: {self._money(payload.discount_amount)}",
            f"Taxable Amount: {self._money(payload.taxable_amount)}",
            f"GST (5%): {self._money(payload.gst_amount)}",
            f"Total Paid: {self._money(payload.total_paid)}",
            f"Payment Mode: {payload.payment_mode.replace('_', ' ').title()}",
            f"Transaction Reference: {payload.transaction_reference or '-'}",
            "",
            "Thank you for choosing VYON FIT CLUB.",
        ]

        pdf_bytes = self._build_pdf_bytes(lines)
        output_path.write_bytes(pdf_bytes)

        return os.path.abspath(output_path)
