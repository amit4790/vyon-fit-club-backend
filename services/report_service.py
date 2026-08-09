"""Service layer for live admin reports."""

from sqlalchemy.orm import Session

from repositories import DashboardRepository, InvoiceRepository
from repositories.business_setting_repository import BusinessSettingRepository
from schemas.report import ReportsSummaryData


class ReportService:
    """Build report metrics from live production tables."""

    def __init__(self, db: Session):
        self.db = db
        self.dashboard_repo = DashboardRepository(db)
        self.invoice_repo = InvoiceRepository(db)
        self.settings_repo = BusinessSettingRepository(db)

    def get_summary(self) -> ReportsSummaryData:
        invoice_metrics = self.invoice_repo.get_report_metrics()
        settings = self.settings_repo.get_or_create_settings()
        collected = float(invoice_metrics["collected_revenue"])
        target = float(settings.target_revenue or 0)

        return ReportsSummaryData(
            total_members=self.dashboard_repo.get_total_members(),
            active_members=self.dashboard_repo.get_active_members(),
            total_invoices=invoice_metrics["total_invoices"],
            paid_invoices=invoice_metrics["paid_invoices"],
            pending_invoices=invoice_metrics["pending_invoices"],
            collected_revenue=collected,
            outstanding_revenue=invoice_metrics["outstanding_revenue"],
            target_revenue=target,
            revenue_gap=target - collected,
            average_invoice_value=invoice_metrics["average_invoice_value"],
            expiring_memberships_next_30_days=self.dashboard_repo.get_expiring_memberships(days=30),
        )

    def update_target_revenue(self, target_revenue: float) -> ReportsSummaryData:
        try:
            self.settings_repo.update_target_revenue(target_revenue)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return self.get_summary()
