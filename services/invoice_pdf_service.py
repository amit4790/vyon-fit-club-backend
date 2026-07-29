"""Reusable PDF invoice renderer."""

from __future__ import annotations

import math
import os
import zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from PIL import Image

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
    final_amount_payable: float
    amount_paid: float
    outstanding_balance: float
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


DEFAULT_LOGO_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "logo.png"
)


class InvoicePdfService:
    """Render invoice PDFs with a layout that is easy to replace later."""

    def __init__(
        self,
        root_dir: str | Path | None = None,
        gym_profile: GymInvoiceProfile | None = None,
        logo_path: str | Path | None = None,
    ):
        if root_dir is None:
            root_dir = Path(__file__).resolve().parents[1] / "storage" / "invoices"
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.gym_profile = gym_profile or DEFAULT_GYM_INVOICE_PROFILE
        self.logo_path = Path(logo_path) if logo_path else DEFAULT_LOGO_PATH

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
        if normalized == "partial":
            return "PARTIALLY PAID"
        if normalized == "pending":
            return "PENDING"
        if normalized == "failed":
            return "FAILED"
        if normalized == "cancelled":
            return "CANCELLED"
        return normalized.upper()

    @staticmethod
    def _status_stamp_color(status: str) -> tuple[float, float, float]:
        """Stroke/text colour used for the circular status stamp."""
        normalized = status.strip().lower()
        if normalized == "paid":
            return (0.09, 0.47, 0.22)
        if normalized == "partial":
            return (0.72, 0.40, 0.03)
        if normalized == "pending":
            return (0.72, 0.40, 0.03)
        if normalized == "failed":
            return (0.70, 0.14, 0.14)
        return (0.35, 0.35, 0.35)

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

    def _cmd_rotated_text(
        self,
        cx: float,
        cy: float,
        text: str,
        angle_degrees: float,
        *,
        size: int = 12,
        bold: bool = True,
        color: tuple[float, float, float] = (0.0, 0.0, 0.0),
        local_y: float = 0.0,
    ) -> list[str]:
        """Draw ``text`` centred horizontally around (cx, cy) but rotated."""
        rad = math.radians(angle_degrees)
        a, b = math.cos(rad), math.sin(rad)
        c, d = -math.sin(rad), math.cos(rad)

        origin_x = cx + local_y * c
        origin_y = cy + local_y * d

        approx_char_w = size * (0.62 if bold else 0.56)
        text_width = len(text) * approx_char_w
        origin_x -= (text_width / 2.0) * a
        origin_y -= (text_width / 2.0) * b

        escaped = self._escape_pdf_text(self._safe_text(text, fallback=""))
        font = "F2" if bold else "F1"
        return [
            "BT",
            f"/{font} {size} Tf",
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} rg",
            f"{a:.4f} {b:.4f} {c:.4f} {d:.4f} {origin_x:.2f} {origin_y:.2f} Tm",
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

    @staticmethod
    def _cmd_circle(cx: float, cy: float, r: float, *, color: tuple[float, float, float], width: float = 1.4) -> list[str]:
        """Approximate a circle stroke using four cubic Bezier arcs."""
        k = 0.5523 * r
        return [
            f"{color[0]:.3f} {color[1]:.3f} {color[2]:.3f} RG",
            f"{width:.2f} w",
            f"{cx - r:.2f} {cy:.2f} m",
            f"{cx - r:.2f} {cy + k:.2f} {cx - k:.2f} {cy + r:.2f} {cx:.2f} {cy + r:.2f} c",
            f"{cx + k:.2f} {cy + r:.2f} {cx + r:.2f} {cy + k:.2f} {cx + r:.2f} {cy:.2f} c",
            f"{cx + r:.2f} {cy - k:.2f} {cx + k:.2f} {cy - r:.2f} {cx:.2f} {cy - r:.2f} c",
            f"{cx - k:.2f} {cy - r:.2f} {cx - r:.2f} {cy - k:.2f} {cx - r:.2f} {cy:.2f} c",
            "S",
        ]

    def _cmd_status_stamp(
        self,
        cx: float,
        cy: float,
        radius: float,
        payload: InvoicePdfPayload,
        *,
        angle_degrees: float = -13.0,
    ) -> list[str]:
        """Draw a rotated, ink-stamp style status marker (double ring)."""
        color = self._status_stamp_color(payload.payment_status)
        status_text = self._display_payment_status(payload.payment_status)
        date_text = f"{self._display_date(payload.invoice_date)}"

        commands: list[str] = []
        commands.extend(self._cmd_circle(cx, cy, radius, color=color, width=2.2))
        commands.extend(self._cmd_circle(cx, cy, radius - 6, color=color, width=0.9))
        commands.extend(
            self._cmd_rotated_text(
                cx,
                cy,
                status_text,
                angle_degrees,
                size=11 if len(status_text) > 8 else 15,
                bold=True,
                color=color,
                local_y=8,
            )
        )
        commands.extend(
            self._cmd_rotated_text(
                cx, cy, date_text, angle_degrees, size=7.5, bold=True, color=color, local_y=-9
            )
        )
        return commands

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

    def _load_png_image(self):
        if not self.logo_path.exists():
            return None

        img = Image.open(self.logo_path).convert("RGBA")

        width, height = img.size

        rgb = bytearray()
        alpha = bytearray()

        for r, g, b, a in img.getdata():
            rgb.extend((r, g, b))
            alpha.append(a)

        return width, height, bytes(rgb), bytes(alpha)

    def _cmd_image(self, img_name: str, x: float, y: float, width: float, height: float) -> list[str]:
        return [
            "q",
            f"{width:.2f} 0 0 {height:.2f} {x:.2f} {y:.2f} cm",
            f"/{img_name} Do",
            "Q",
        ]

    def _append_footer(
        self,
        stream: list[str],
        *,
        margin: float,
        content_w: float,
        footer_y: float,
        border: tuple[float, float, float],
        text_dark: tuple[float, float, float],
        text_muted: tuple[float, float, float],
    ) -> None:
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

    def _append_rules_pages(
        self,
        *,
        page_streams: list[list[str]],
        start_y: float,
        margin: float,
        content_w: float,
        page_h: float,
        primary: tuple[float, float, float],
        text_dark: tuple[float, float, float],
        text_muted: tuple[float, float, float],
        border: tuple[float, float, float],
        footer_y: float,
    ) -> None:
        footer_top = footer_y + 30
        min_gap_above_footer = 16.0
        rules_line_height = 10.0
        rules_item_spacing = 1.0
        continued_top_y = page_h - margin - 12

        def section_title(stream: list[str], title: str, y: float) -> float:
            stream.extend(self._cmd_text(margin, y, title, size=10.5, bold=True, color=primary))
            stream.extend(self._cmd_line(margin, y - 6, margin + content_w, y - 6, color=border, width=0.8))
            return y - 24

        stream = page_streams[-1]
        y = section_title(stream, "RULES & REGULATIONS", start_y)

        for index, rule in enumerate(DEFAULT_RULES_AND_REGULATIONS, start=1):
            rule_lines = self._wrap_text(rule, 84)
            required_height = (len(rule_lines) * rules_line_height) + rules_item_spacing

            if y - required_height < footer_top + min_gap_above_footer:
                stream = []
                page_streams.append(stream)
                y = section_title(stream, "RULES & REGULATIONS (CONTINUED)", continued_top_y)

            first_line = f"{index}. {rule_lines[0]}"
            stream.extend(self._cmd_text(margin, y, first_line, size=8, color=text_dark))
            y -= rules_line_height
            for line in rule_lines[1:]:
                stream.extend(self._cmd_text(margin + 16, y, line, size=8, color=text_dark))
                y -= rules_line_height
            y -= rules_item_spacing

        self._append_footer(
            stream,
            margin=margin,
            content_w=content_w,
            footer_y=footer_y,
            border=border,
            text_dark=text_dark,
            text_muted=text_muted,
        )

    def _build_invoice_streams(self, payload: InvoicePdfPayload) -> tuple[list[bytes], dict]:
        stream: list[str] = []
        page_streams: list[list[str]] = [stream]

        page_w = 595.0
        page_h = 842.0
        margin = 40.0
        content_w = page_w - (2 * margin)

        primary = (0.79, 0.16, 0.29)
        text_dark = (0.12, 0.12, 0.12)
        text_muted = (0.42, 0.42, 0.42)
        border = (0.86, 0.86, 0.86)
        panel_bg = (0.98, 0.98, 0.98)

        taxable_amount = payload.taxable_amount
        gst_amount = payload.gst_amount

        top = page_h - margin

        # Header
        header_h = 150.0
        header_y = top - header_h
        stream.extend(self._cmd_rect(margin, header_y, content_w, header_h, fill=(1, 1, 1), stroke=border))
        stream.extend(self._cmd_rect(margin, header_y + header_h - 4, content_w, 4, fill=primary))

        logo_info = self._load_png_image()
        logo_x = margin + 16
        info_x = logo_x

        if logo_info:
            img_w, img_h, _, _ = logo_info
            target_h = 65.0
            target_w = (img_w / img_h) * target_h
            if target_w > 160.0:
                target_w = 160.0
                target_h = (img_h / img_w) * target_w

            logo_y = header_y + header_h - 16 - target_h
            stream.extend(self._cmd_image("I1", logo_x, logo_y, target_w, target_h))
            info_x = logo_x + target_w + 14
        else:
            logo_size = 46.0
            logo_y = header_y + header_h - 20 - logo_size
            stream.extend(self._cmd_rect(logo_x, logo_y, logo_size, logo_size, fill=primary, stroke=primary))
            stream.extend(self._cmd_text(logo_x + 7, logo_y + 18, self.gym_profile.logo_text, size=13, bold=True, color=(1, 1, 1)))
            info_x = logo_x + logo_size + 12

        info_y = header_y + header_h - 24
        stream.extend(self._cmd_text(info_x, info_y, self.gym_profile.gym_name, size=14, bold=True, color=text_dark))
        stream.extend(self._cmd_text(info_x, info_y - 15, self.gym_profile.tagline, size=8.5, color=primary))
        stream.extend(self._cmd_text(info_x, info_y - 31, self.gym_profile.address, size=8, color=text_muted))
        stream.extend(self._cmd_text(info_x, info_y - 44, self.gym_profile.phone, size=8, color=text_muted))
        stream.extend(self._cmd_text(info_x, info_y - 57, self.gym_profile.email, size=8, color=text_muted))
        stream.extend(self._cmd_text(info_x, info_y - 72, self.gym_profile.gstin_label, size=8, bold=True, color=text_dark))

        meta_w = 150.0
        meta_h = 100.0
        meta_x = margin + 246
        meta_y = header_y + (header_h - meta_h) / 2.0
        stream.extend(self._cmd_rect(meta_x, meta_y, meta_w, meta_h, fill=panel_bg, stroke=border))
        stream.extend(self._cmd_text(meta_x + 12, meta_y + meta_h - 22, "TAX INVOICE", size=11, bold=True, color=primary))
        stream.extend(self._cmd_text(meta_x + 12, meta_y + meta_h - 42, f"No.: {payload.invoice_number}", size=8.5, color=text_dark))
        stream.extend(self._cmd_text(
            meta_x + 12,
            meta_y + meta_h - 58,
            f"Date: {self._display_date(payload.invoice_date)}",
            size=8.5,
            color=text_dark,
        ))
        stream.extend(self._cmd_text(meta_x + 12, meta_y + meta_h - 74, f"Time: {self._safe_text(payload.invoice_time)}", size=8.5, color=text_dark))

        stamp_radius = 38.0
        stamp_cx = margin + content_w - 16 - stamp_radius
        stamp_cy = header_y + header_h / 2.0
        stream.extend(self._cmd_status_stamp(stamp_cx, stamp_cy, stamp_radius, payload))

        y = header_y - 26

        def section_title(title: str) -> None:
            nonlocal y
            stream.extend(self._cmd_text(margin, y, title, size=10.5, bold=True, color=primary))
            stream.extend(self._cmd_line(margin, y - 6, margin + content_w, y - 6, color=border, width=0.8))
            y -= 24

        # Bill To
        section_title("BILL TO")
        stream.extend(self._cmd_text(margin, y, f"Member Name: {self._safe_text(payload.member_name)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Member ID: {self._safe_text(payload.member_id)}", size=10, color=text_dark))
        y -= 17
        stream.extend(self._cmd_text(margin, y, f"Email: {self._safe_text(payload.member_email)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Phone: {self._safe_text(payload.member_phone)}", size=10, color=text_dark))
        y -= 27

        # Membership Details
        section_title("MEMBERSHIP DETAILS")
        stream.extend(self._cmd_text(margin, y, f"Subscription Name: {self._safe_text(payload.plan_label)}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Duration: {self._safe_text(payload.duration_label)}", size=10, color=text_dark))
        y -= 17
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
        y -= 27

        # Payment Summary
        section_title("PAYMENT SUMMARY")
        table_x = margin
        table_w = content_w
        table_row_h = 23.0
        col_split = table_x + (table_w * 0.62)

        amount_paid_color = (0.09, 0.47, 0.22) if payload.outstanding_balance <= 0 else (0.72, 0.40, 0.03)
        rows = [
            ("Original Membership Price", self._format_currency(payload.original_price), False, text_dark),
            ("Discount", self._format_currency(payload.discount_amount), False, text_dark),
            ("Taxable Amount", self._format_currency(taxable_amount), False, text_dark),
            ("GST @ 5%", self._format_currency(gst_amount), False, text_dark),
            ("Final Amount Payable", self._format_currency(payload.final_amount_payable), False, text_dark),
            ("Amount Paid", self._format_currency(payload.amount_paid), True, amount_paid_color),
            ("Outstanding Balance", self._format_currency(payload.outstanding_balance), False, text_dark),
            ("Payment Mode", self._display_payment_mode(payload.payment_mode), False, text_dark),
            ("Transaction Reference", self._safe_text(payload.transaction_reference), False, text_dark),
        ]

        table_h = table_row_h * len(rows)
        table_y = y - table_h + 8
        stream.extend(self._cmd_rect(table_x, table_y, table_w, table_h, fill=(1, 1, 1), stroke=border))

        for row_index, (label, value, highlight, value_color) in enumerate(rows):
            row_top = y + 8 - (row_index * table_row_h)
            row_bottom = row_top - table_row_h
            if highlight:
                stream.extend(self._cmd_rect(table_x + 0.6, row_bottom + 0.6, table_w - 1.2, table_row_h - 1.2, fill=(0.92, 0.97, 0.93)))

            if row_index > 0:
                stream.extend(self._cmd_line(table_x, row_top, table_x + table_w, row_top, color=border, width=0.7))

            stream.extend(self._cmd_text(
                table_x + 10,
                row_bottom + 7,
                label,
                size=10,
                bold=highlight,
                color=text_dark,
            ))
            stream.extend(self._cmd_text(
                col_split + 10,
                row_bottom + 7,
                value,
                size=10,
                bold=highlight,
                color=value_color,
            ))

        stream.extend(self._cmd_line(col_split, table_y, col_split, table_y + table_h, color=border, width=0.7))

        y = table_y - 22

        # Staff details
        section_title("STAFF DETAILS")
        created_by = self._safe_text(payload.created_by)
        counsellor = self._safe_text(payload.counsellor)
        stream.extend(self._cmd_text(margin, y, f"Created By: {created_by}", size=10, color=text_dark))
        stream.extend(self._cmd_text(margin + 290, y, f"Counsellor: {counsellor}", size=10, color=text_dark))
        y -= 27

        if payload.remarks:
            section_title("REMARKS")
            remark_lines = self._wrap_text(payload.remarks, 88)
            for line in remark_lines[:3]:
                stream.extend(self._cmd_text(margin, y, line, size=10, color=text_dark))
                y -= 14
            y -= 10

        footer_y = 46.0
        self._append_rules_pages(
            page_streams=page_streams,
            start_y=y,
            margin=margin,
            content_w=content_w,
            page_h=page_h,
            primary=primary,
            text_dark=text_dark,
            text_muted=text_muted,
            border=border,
            footer_y=footer_y,
        )

        content_streams = ["\n".join(page_stream).encode("latin-1", errors="replace") for page_stream in page_streams]
        return content_streams, {"logo": logo_info, "page_width": page_w, "page_height": page_h}

    def _build_pdf_bytes(self, streams: list[bytes], resources_meta: dict) -> bytes:
        objects: list[bytes] = []

        logo_info = resources_meta.get("logo")
        page_w = resources_meta.get("page_width", 595.0)
        page_h = resources_meta.get("page_height", 842.0)
        page_count = len(streams)
        font1_obj_number = 3 + page_count
        font2_obj_number = 4 + page_count
        content_object_start = 5 + page_count
        xobject_ref = ""
        smask_obj_index = None
        image_obj_number = content_object_start + page_count
        mask_obj_number = image_obj_number + 1 if logo_info and logo_info[3] else None

        if logo_info:
            img_w, img_h, rgb_data, alpha_data = logo_info

            if alpha_data:
                smask_obj_index = mask_obj_number
            xobject_ref = f"/XObject << /I1 {image_obj_number} 0 R >>"

        objects.append(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")
        kids_refs = " ".join(f"{3 + index} 0 R" for index in range(len(streams)))
        objects.append(f"2 0 obj\n<< /Type /Pages /Kids [{kids_refs}] /Count {len(streams)} >>\nendobj\n".encode("latin-1"))

        res_str = f"/Resources << /Font << /F1 {font1_obj_number} 0 R /F2 {font2_obj_number} 0 R >> {xobject_ref} >>"

        for index, stream in enumerate(streams):
            page_obj_number = 3 + index
            content_obj_number = content_object_start + index
            objects.append(
                (
                    f"{page_obj_number} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_w:.0f} {page_h:.0f}] "
                    f"{res_str} /Contents {content_obj_number} 0 R >>\nendobj\n"
                ).encode("latin-1")
            )

        objects.append(f"{font1_obj_number} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode("latin-1"))
        objects.append(f"{font2_obj_number} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n".encode("latin-1"))

        for index, stream in enumerate(streams):
            content_obj_number = content_object_start + index
            objects.append(
                f"{content_obj_number} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                + stream
                + b"\nendstream\nendobj\n"
            )

        if logo_info:
            img_w, img_h, rgb_data, alpha_data = logo_info
            smask_entry = f" /SMask {smask_obj_index} 0 R" if alpha_data else ""
            img_header = (
                f"{image_obj_number} 0 obj\n<< /Type /XObject /Subtype /Image /Width {img_w} /Height {img_h} "
                f"/ColorSpace /DeviceRGB /BitsPerComponent 8{smask_entry} /Length {len(rgb_data)} >>\nstream\n"
            ).encode("latin-1")
            objects.append(img_header + rgb_data + b"\nendstream\nendobj\n")

            if alpha_data:
                mask_header = (
                    f"{mask_obj_number} 0 obj\n<< /Type /XObject /Subtype /Image /Width {img_w} /Height {img_h} "
                    f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Length {len(alpha_data)} >>\nstream\n"
                ).encode("latin-1")
                objects.append(mask_header + alpha_data + b"\nendstream\nendobj\n")

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

        streams, resources_meta = self._build_invoice_streams(payload)
        pdf_bytes = self._build_pdf_bytes(streams, resources_meta)
        output_path.write_bytes(pdf_bytes)

        return os.path.abspath(output_path)
