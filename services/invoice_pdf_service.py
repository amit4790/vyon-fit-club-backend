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
    invoice_time: str
    member_id: str
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
    payment_status: str = "paid"
    remarks: str | None = None
    created_by: str | None = None
    counsellor: str | None = None


@dataclass(frozen=True)
class GymInvoiceProfile:
    logo_text: str
    gym_name: str
    tagline: str
    address: str
    phone: str
    email: str
    gstin_label: str
    pan_label: str


DEFAULT_GYM_INVOICE_PROFILE = GymInvoiceProfile(
    logo_text="VYON",
    gym_name="VYON Fit Club",
    tagline="Membership Invoice",
    address="Address: Update from business profile",
    phone="Phone: Update from business profile",
    email="Email: update@vyonfitclub.com",
    gstin_label="GST No.: Applied For",
    pan_label="PAN No.: Applied For",
)


DEFAULT_RULES_AND_REGULATIONS: list[str] = [
    "Fees once paid are non-refundable and are required to be paid in advance at the time of enrollment.",
    "Equipment must be used carefully. Any damage caused due to misuse may be charged to the member.",
    "Members should consult a physician before joining and are responsible for disclosing relevant medical history.",
    "Membership can be paused only in approved cases with valid supporting documents.",
    "Discounted or complimentary months cannot be paused, carried forward, or converted to cash.",
    "The management reserves the right to modify or update these terms and conditions as needed.",
]


class InvoicePdfService:
    """Render invoice PDFs with a layout that is easy to replace later."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        gym_profile: GymInvoiceProfile | None = None,
    ):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parents[1] / "storage" / "invoices"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.gym_profile = gym_profile or DEFAULT_GYM_INVOICE_PROFILE

    @staticmethod
    def _format_currency(value: float) -> str:
        rounded = round(float(value), 2)
        text = f"{abs(rounded):,.2f}"
        if text.endswith(".00"):
            text = text[:-3]
        sign = "-" if rounded < 0 else ""
        return f"{sign}Rs. {text}"

    @staticmethod
    def _safe_text(value: str | None, fallback: str = "-") -> str:
        if value is None:
            return fallback
        cleaned = " ".join(value.strip().split())
        return cleaned or fallback

    @staticmethod
    def _display_date(value: date | None) -> str:
        if value is None:
            return "-"
        return value.strftime("%d %b %Y")

    @staticmethod
    def _display_payment_mode(payment_mode: str) -> str:
        return payment_mode.replace("_", " ").title()

    @staticmethod
    def _display_payment_status(payment_status: str) -> str:
        normalized = payment_status.strip().lower()
        if normalized == "paid":
            return "PAID"
        if normalized == "pending":
            return "PENDING"
        if normalized == "failed":
            return "FAILED"
        if normalized == "cancelled":
            return "CANCELLED"
        return normalized.upper()

    @staticmethod
    def _status_badge(status: str) -> tuple[str, tuple[float, float, float], tuple[float, float, float]]:
        normalized = status.strip().lower()
        if normalized == "paid":
            return "PAID", (0.88, 0.97, 0.91), (0.10, 0.45, 0.20)
        if normalized == "pending":
            return "PENDING", (1.00, 0.96, 0.85), (0.70, 0.38, 0.03)
        if normalized == "failed":
            return "FAILED", (0.99, 0.90, 0.90), (0.68, 0.13, 0.13)
        return normalized.upper(), (0.93, 0.93, 0.93), (0.28, 0.28, 0.28)

    @staticmethod
    def _escape_pdf_text(value: str) -> str:
        return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def _cmd_text(
        self,
        x: float,
        y: float,
        text: str,
        *,
        size: int = 11,
        bold: bool = False,
        color: tuple[float, float, float] = (0.12, 0.12, 0.12),
    ) -> list[str]:
        escaped = self._escape_pdf_text(self._safe_text(text, fallback=""))
        font = "F2" if bold else "F1"
        return [
            "BT",
            f"/{font} {size} Tf",
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg",
            f"1 0 0 1 {x:.2f} {y:.2f} Tm",
            f"({escaped}) Tj",
            "ET",
        ]

    @staticmethod
    def _cmd_rect(x: float, y: float, width: float, height: float, *, fill: tuple[float, float, float] | None = None,
                  stroke: tuple[float, float, float] | None = None, line_width: float = 1.0) -> list[str]:
        commands: list[str] = []
        if fill is not None:
            commands.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg")
        if stroke is not None:
            commands.append(f"{stroke[0]:.3f} {stroke[1]:.3f} {stroke[2]:.3f} RG")
            commands.append(f"{line_width:.2f} w")
        commands.append(f"{x:.2f} {y:.2f} {width:.2f} {height:.2f} re")
        if fill is not None and stroke is not None:
            commands.append("B")
        elif fill is not None:
            commands.append("f")
        else:
            commands.append("S")
        return commands

    @staticmethod
    def _cmd_line(x1: float, y1: float, x2: float, y2: float, *, color: tuple[float, float, float], width: float = 1.0) -> list[str]:
        return [
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG",
            f"{width:.2f} w",
            f"{x1:.2f} {y1:.2f} m",
            f"{x2:.2f} {y2:.2f} l",
            "S",
        ]

    def _wrap_text(self, text: str, max_chars: int) -> list[str]:
        words = self._safe_text(text, fallback="").split()
        if not words:
            return ["-"]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _build_invoice_stream(self, payload: InvoicePdfPayload) -> bytes:
        stream: list[str] = []

        page_w = 595.0
        page_h = 842.0
        margin = 34.0
        content_w = page_w - (2 * margin)

        primary = (0.79, 0.16, 0.29)
        text_dark = (0.12, 0.12, 0.12)
        text_muted = (0.40, 0.40, 0.40)
        border = (0.85, 0.85, 0.85)
        panel_bg = (0.98, 0.98, 0.98)
        success_bg = (0.90, 0.95, 0.90)
        success_text = (0.10, 0.45, 0.20)

        top = page_h - margin

        # Header container
        header_h = 128.0
        header_y = top - header_h
        stream.extend(self._cmd_rect(margin, header_y, content_w, header_h, fill=(1, 1, 1), stroke=border))

        # Logo block
        logo_size = 54.0
        logo_x = margin + 14
        logo_y = top - 66
        stream.extend(self._cmd_rect(logo_x, logo_y, logo_size, logo_size, fill=primary, stroke=primary))
        stream.extend(self._cmd_text(logo_x + 6, logo_y + 22, self.gym_profile.logo_text, size=16, bold=True, color=(1, 1, 1)))

        left_x = logo_x + logo_size + 14
        stream.extend(self._cmd_text(left_x, top - 30, self.gym_profile.gym_name, size=17, bold=True, color=text_dark))
        stream.extend(self._cmd_text(left_x, top - 48, self.gym_profile.tagline, size=10, color=primary))
        stream.extend(self._cmd_text(left_x, top - 66, self.gym_profile.address, size=10, color=text_muted))
        stream.extend(self._cmd_text(left_x, top - 81, self.gym_profile.phone, size=10, color=text_muted))
        stream.extend(self._cmd_text(left_x, top - 96, self.gym_profile.email, size=10, color=text_muted))
        stream.extend(self._cmd_text(left_x, top - 111, self.gym_profile.gstin_label, size=10, bold=True, color=text_dark))

        # Invoice meta (right)
        right_box_w = 205.0
        right_box_h = 104.0
        right_x = margin + content_w - right_box_w - 16
        right_y = top - right_box_h - 16
        stream.extend(self._cmd_rect(right_x, right_y, right_box_w, right_box_h, fill=panel_bg, stroke=border))
        stream.extend(self._cmd_text(right_x + 12, right_y + right_box_h - 22, "RENEWAL INVOICE", size=13, bold=True, color=primary))
        stream.extend(self._cmd_text(right_x + 12, right_y + right_box_h - 40, f"Invoice No.: {payload.invoice_number}", size=10, color=text_dark))
        stream.extend(self._cmd_text(
            right_x + 12,
            right_y + right_box_h - 56,
            f"Invoice Date: {self._display_date(payload.invoice_date)}",
            size=10,
            color=text_dark,
        ))
        stream.extend(self._cmd_text(right_x + 12, right_y + right_box_h - 72, f"Invoice Time: {self._safe_text(payload.invoice_time)}", size=10, color=text_dark))

        badge_text, badge_bg, badge_fg = self._status_badge(payload.payment_status)
        badge_w = 80.0
        badge_h = 20.0
        badge_x = right_x + 12
        badge_y = right_y + 14
        stream.extend(self._cmd_rect(badge_x, badge_y, badge_w, badge_h, fill=badge_bg, stroke=badge_bg))
        stream.extend(self._cmd_text(badge_x + 12, badge_y + 6, badge_text, size=9, bold=True, color=badge_fg))

        y = header_y - 16

        def section_title(title: str) -> None:
            nonlocal y
            stream.extend(self._cmd_text(margin, y, title, size=11, bold=True, color=primary))
            stream.extend(self._cmd_line(margin, y - 6, margin + content_w, y - 6, color=border, width=0.8))
            y -= 22

        # Bill To
        section_title("BILL TO")
        stream.extend(self._cmd_text(margin, y, f"Member Name: {self._safe_text(payload.member_name)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Member ID: {self._safe_text(payload.member_id)}", size=10, color=text_dark))
        y -= 16
        stream.extend(self._cmd_text(margin, y, f"Email: {self._safe_text(payload.member_email)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Phone: {self._safe_text(payload.member_phone)}", size=10, color=text_dark))
        y -= 24

        # Membership Details
        section_title("MEMBERSHIP DETAILS")
        stream.extend(self._cmd_text(margin, y, f"Subscription Name: {self._safe_text(payload.plan_label)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Duration: {self._safe_text(payload.duration_label)}", size=10, color=text_dark))
        y -= 16
        stream.extend(self._cmd_text(
            margin,
            y,
            f"From Date: {self._display_date(payload.start_date)}",
            size=10,
            color=text_dark,
        ))
        stream.extend(self._cmd_text(
            margin + 290,
            y,
            f"To Date: {self._display_date(payload.end_date)}",
            size=10,
            color=text_dark,
        ))
        y -= 24

        # Payment Summary Table
        section_title("PAYMENT SUMMARY")
        table_x = margin
        table_w = content_w
        table_row_h = 22.0
        col_split = table_x + (table_w * 0.62)

        rows = [
            ("Original Price", self._format_currency(payload.original_price)),
            ("Discount", self._format_currency(payload.discount_amount)),
            ("GST", self._format_currency(payload.gst_amount)),
            ("Final Amount Paid", self._format_currency(payload.total_paid)),
            ("Payment Mode", self._display_payment_mode(payload.payment_mode)),
            ("Transaction Reference", self._safe_text(payload.transaction_reference)),
        ]

        table_h = table_row_h * len(rows)
        table_y = y - table_h + 8
        stream.extend(self._cmd_rect(table_x, table_y, table_w, table_h, fill=(1, 1, 1), stroke=border))

        for row_index, (label, value) in enumerate(rows):
            row_top = y + 8 - (row_index * table_row_h)
            row_bottom = row_top - table_row_h
            if row_index == 3:
                stream.extend(self._cmd_rect(table_x + 0.6, row_bottom + 0.6, table_w - 1.2, table_row_h - 1.2, fill=(0.95, 0.97, 1.0)))

            if row_index > 0:
                stream.extend(self._cmd_line(table_x, row_top, table_x + table_w, row_top, color=border, width=0.7))

            stream.extend(self._cmd_text(
                table_x + 10,
                row_bottom + 7,
                label,
                size=10,
                bold=(row_index == 3),
                color=text_dark,
            ))
            stream.extend(self._cmd_text(
                col_split + 10,
                row_bottom + 7,
                value,
                size=10,
                bold=(row_index == 3),
                color=text_dark,
            ))

        stream.extend(self._cmd_line(col_split, table_y, col_split, table_y + table_h, color=border, width=0.7))

        y = table_y - 18

        # Payment Breakdown
        section_title("PAYMENT BREAKDOWN")
        breakdown_rows = [
            ("Original Price", self._format_currency(payload.original_price), False),
            ("Discount", f"- {self._format_currency(payload.discount_amount)}", False),
            ("GST", self._format_currency(payload.gst_amount), False),
            ("Total Paid", self._format_currency(payload.total_paid), True),
        ]

        breakdown_x = margin
        breakdown_w = content_w
        breakdown_h = 112.0
        breakdown_y = y - breakdown_h + 8
        stream.extend(self._cmd_rect(breakdown_x, breakdown_y, breakdown_w, breakdown_h, fill=(1, 1, 1), stroke=border))

        cursor_y = breakdown_y + breakdown_h - 22
        for index, (label, amount, highlight) in enumerate(breakdown_rows):
            if highlight:
                stream.extend(self._cmd_rect(breakdown_x + 1, cursor_y - 5, breakdown_w - 2, 22, fill=success_bg))

            stream.extend(self._cmd_text(
                breakdown_x + 12,
                cursor_y,
                label,
                size=10,
                bold=highlight,
                color=text_dark,
            ))
            stream.extend(self._cmd_text(
                breakdown_x + breakdown_w - 160,
                cursor_y,
                amount,
                size=10,
                bold=highlight,
                color=success_text if highlight else text_dark,
            ))

            if index < len(breakdown_rows) - 1:
                stream.extend(self._cmd_text(breakdown_x + (breakdown_w / 2) - 4, cursor_y - 15, "v", size=10, color=text_muted))
            cursor_y -= 26

        y = breakdown_y - 18

        # Staff and remarks
        section_title("STAFF DETAILS")
        created_by = self._safe_text(payload.created_by)
        counsellor = self._safe_text(payload.counsellor)
        stream.extend(self._cmd_text(margin, y, f"Created By: {created_by}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Counsellor: {counsellor}", size=10, color=text_dark))
        y -= 24

        if payload.remarks:
            section_title("REMARKS")
            remark_lines = self._wrap_text(payload.remarks, 88)
            for line in remark_lines[:3]:
                stream.extend(self._cmd_text(margin, y, line, size=10, color=text_dark))
                y -= 14
            y -= 8

        section_title("RULES & REGULATIONS")
        for index, rule in enumerate(DEFAULT_RULES_AND_REGULATIONS, start=1):
            rule_lines = self._wrap_text(rule, 82)
            first_line = f"{index}. {rule_lines[0]}"
            stream.extend(self._cmd_text(margin, y, first_line, size=8, color=text_dark))
            y -= 12
            for line in rule_lines[1:]:
                stream.extend(self._cmd_text(margin + 16, y, line, size=8, color=text_dark))
                y -= 12
            y -= 2

        # Footer
        footer_y = 46.0
        stream.extend(self._cmd_line(margin, footer_y + 30, margin + content_w, footer_y + 30, color=border, width=0.8))
        stream.extend(self._cmd_text(margin, footer_y + 14, f"For {self.gym_profile.gym_name}", size=10, bold=True, color=text_dark))
        stream.extend(self._cmd_text(margin, footer_y, "This is a computer-generated invoice and does not require a signature.", size=9, color=text_muted))
        stream.extend(
            self._cmd_text(
                margin,
                footer_y - 14,
                self.gym_profile.pan_label,
                size=9,
                color=text_muted,
            )
        )
        stream.extend(self._cmd_text(margin + 250, footer_y - 14, self.gym_profile.gstin_label, size=9, color=text_muted))

        return "\n".join(stream).encode("latin-1", errors="replace")

    def _build_pdf_bytes(self, stream: bytes) -> bytes:

        objects: list[bytes] = []
        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        objects.append(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n")
        objects.append(
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>\nendobj\n"
        )
        objects.append(b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n")
        objects.append(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n")
        objects.append(
            f"6 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
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

        stream = self._build_invoice_stream(payload)
        pdf_bytes = self._build_pdf_bytes(stream)
        output_path.write_bytes(pdf_bytes)

        return os.path.abspath(output_path)
