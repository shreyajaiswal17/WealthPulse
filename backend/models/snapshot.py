from sqlalchemy import Column, Text, Numeric, Date, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid
from core.database import Base

class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"
    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id       = Column(Text, nullable=False)
    snapshot_date = Column(Date, nullable=False)
    total_value   = Column(Numeric(18, 2))
    total_cost    = Column(Numeric(18, 2))
    breakdown     = Column(JSONB)
    __table_args__ = (UniqueConstraint("user_id", "snapshot_date"),)
