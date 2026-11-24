"""SQLite database: each visitor's profile, transactions and budgets.

There is no login. Each visitor gets a random id (kept in the page URL as `?u=...`), and every
row belongs to one `client_id`, so visitors of the public demo never see each other's data.
"""
from collections.abc import Iterator
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from wealthwise.config import DATA_DIR, settings


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profile"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), default="")
    age: Mapped[int] = mapped_column(Integer)
    monthly_income: Mapped[float] = mapped_column(Float)
    monthly_expenses: Mapped[float] = mapped_column(Float)
    current_savings: Mapped[float] = mapped_column(Float)
    horizon_years: Mapped[int] = mapped_column(Integer)
    dependents: Mapped[int] = mapped_column(Integer, default=0)
    answers: Mapped[dict] = mapped_column(JSON)          # questionnaire id -> 1..4
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_category: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_id: Mapped[str] = mapped_column(String(64), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Float)          # always positive; `kind` says which way it went
    kind: Mapped[str] = mapped_column(String(10))         # "expense" | "income"
    category: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(String(200), default="")


class Budget(Base):
    __tablename__ = "budgets"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(30), primary_key=True)
    monthly_limit: Mapped[float] = mapped_column(Float)


class QuizScore(Base):
    __tablename__ = "quiz_scores"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    best: Mapped[float] = mapped_column(Float)            # best score as a fraction of questions right


DATA_DIR.mkdir(exist_ok=True)
engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
