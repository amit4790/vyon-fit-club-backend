"""Service layer for live admin reports."""

from sqlalchemy.orm import Session

from repositories import DashboardRepository, InvoiceRepository
from schemas.report import ReportsSummaryData


class ReportService:
    """Build report metrics from live production tables."""

    def __init__(self, db: Session):
        self.dashboard_repo = DashboardRepository(db)
        self.invoice_repo = InvoiceRepository(db)

    def get_summary(self) -> ReportsSummaryData:
        invoice_metrics = self.invoice_repo.get_report_metrics()

        return ReportsSummaryData(
            total_members=self.dashboard_repo.get_total_members(),
            active_members=self.dashboard_repo.get_active_members(),
            total_invoices=invoice_metrics["total_invoices"],
            paid_invoices=invoice_metrics["paid_invoices"],
            pending_invoices=invoice_metrics["pending_invoices"],
            collected_revenue=invoice_metrics["collected_revenue"],
            pending_revenue=invoice_metrics["pending_revenue"],
            average_invoice_value=invoice_metrics["average_invoice_value"],
            expiring_memberships_next_30_days=self.dashboard_repo.get_expiring_memberships(days=30),
        )
