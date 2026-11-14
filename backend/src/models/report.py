from sqlalchemy import String, Double, ForeignKey, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Report(Base):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    destination: Mapped[str] = mapped_column(String(120))
    interval_seconds: Mapped[int]
    next_run: Mapped[float] = mapped_column(Double)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
class Delivery(Base):
    __tablename__ = 'deliveries'
    __table_args__ = (UniqueConstraint('report_id', 'scheduled_at', name='uq_delivery_period'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey('reports.id'))
    scheduled_at: Mapped[float | None] = mapped_column(Double, nullable=True)
    created_at: Mapped[float] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    error: Mapped[str] = mapped_column(String(1000), default='')
    checksum: Mapped[str] = mapped_column(String(64), default='')
    meta_checksum: Mapped[str] = mapped_column(String(64), default='')
    filename: Mapped[str] = mapped_column(String(160), default='')
    destination: Mapped[str] = mapped_column(String(120))
    snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
