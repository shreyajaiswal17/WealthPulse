from sqlalchemy import Column, Text, Numeric, Date
from core.database import Base


class PriceHistory(Base):
    __tablename__ = "price_history"
    symbol      = Column(Text, primary_key=True)
    asset_type  = Column(Text, nullable=False)
    price_date  = Column(Date, primary_key=True)
    close_price = Column(Numeric(18, 6), nullable=False)
