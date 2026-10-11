import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings

# Resolve relative path for database storage
db_path = settings.DATABASE_URL.replace("sqlite:///", "")
if not os.path.isabs(db_path):
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_path))

os.makedirs(os.path.dirname(db_path), exist_ok=True)

engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class InvoiceRecord(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    invoice_number = Column(String, unique=True, nullable=False, index=True)
    vendor_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    due_date = Column(String, nullable=True)
    email_date = Column(String, nullable=True)
    file_location = Column(String, nullable=False)
    status = Column(String, default="RECORDED")
    created_at = Column(DateTime, server_default=func.now())

def init_db():
    Base.metadata.create_all(bind=engine)