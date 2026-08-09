"""Repository for gym business settings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BusinessSetting


class BusinessSettingRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create_settings(self) -> BusinessSetting:
        settings = self.db.execute(
            select(BusinessSetting).where(BusinessSetting.id == 1)
        ).scalar_one_or_none()
        if settings:
            return settings

        settings = BusinessSetting(id=1, target_revenue=0)
        self.db.add(settings)
        self.db.flush()
        self.db.refresh(settings)
        return settings

    def update_target_revenue(self, amount: float) -> BusinessSetting:
        settings = self.get_or_create_settings()
        settings.target_revenue = amount
        self.db.flush()
        self.db.refresh(settings)
        return settings
