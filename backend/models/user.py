from sqlalchemy import Column, Text, TIMESTAMP, func
from core.database import Base

class User(Base):
    __tablename__ = "users"
    id         = Column(Text, primary_key=True)  # Auth0 sub
    email      = Column(Text, unique=True, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
