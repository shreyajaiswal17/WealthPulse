from sqlalchemy import Column, Text, Numeric, Date, TIMESTAMP, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from core.database import Base

class Holding(Base):
    __tablename__ = "holdings"
    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id    = Column(Text, nullable=False)
    symbol     = Column(Text, nullable=False)
    name       = Column(Text, nullable=False)
    asset_type = Column(Text, nullable=False)
    buy_price  = Column(Numeric(18, 6), nullable=False)
    quantity   = Column(Numeric(18, 6), nullable=False)
    buy_date   = Column(Date, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
