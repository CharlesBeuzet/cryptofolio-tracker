"""Database models for the crypto portfolio tracker."""
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()


class Asset(Base):
    """Asset information (crypto tokens)."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=True)
    current_price = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    positions = relationship("Position", back_populates="asset")


class Tag(Base):
    """User-defined conviction tag (e.g. VC play, backspot, Majors)."""

    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False, index=True)
    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    positions = relationship("Position", back_populates="tag")


class Position(Base):
    """Portfolio position: exchange-mirrored (synced) or user-declared (manual)."""

    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint(
            "source = 'manual' OR (display_name IS NULL AND external_url IS NULL)",
            name="ck_positions_manual_only_fields",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    asset_id = Column(Integer, ForeignKey("assets.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    quantity = Column(Float, nullable=False, default=0.0)
    first_bought_at = Column(DateTime, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    exchange = Column(String(50), nullable=True)  # binance, coinbase, wallet, etc.
    status = Column(String(10), nullable=False, default="open")  # open | closed
    tag_id = Column(Integer, ForeignKey("tags.id"), nullable=True, index=True)
    source = Column(String(16), nullable=False, default="synced")  # synced | manual
    display_name = Column(String(120), nullable=True)  # manual positions only
    external_url = Column(String(500), nullable=True)  # manual positions only

    asset = relationship("Asset", back_populates="positions")
    tag = relationship("Tag", back_populates="positions")
    orders = relationship("Order", back_populates="position", cascade="all, delete-orphan")
    metrics = relationship(
        "PositionMetrics",
        back_populates="position",
        uselist=False,
        cascade="all, delete-orphan",
    )
    valuations = relationship(  # manual positions only; synced use metrics
        "PositionValuation",
        back_populates="position",
        cascade="all, delete-orphan",
        order_by="PositionValuation.recorded_at",
    )


class PositionValuation(Base):
    """User-entered mark-to-market snapshot for a manual position."""

    __tablename__ = "position_valuations"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False, index=True)
    recorded_at = Column(DateTime, nullable=False, index=True)
    value_amount = Column(Float, nullable=False)
    quantity = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    position = relationship("Position", back_populates="valuations")


class PositionMetrics(Base):
    """Order-derived analytics for a position (average-cost method)."""

    __tablename__ = "position_metrics"

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), unique=True, nullable=False)

    avg_entry_price = Column(Float, nullable=False, default=0.0)
    avg_exit_price = Column(Float, nullable=True)
    break_even_price = Column(Float, nullable=False, default=0.0)

    realised_pnl = Column(Float, nullable=False, default=0.0)
    realised_pnl_percent = Column(Float, nullable=False, default=0.0)
    unrealised_pnl = Column(Float, nullable=False, default=0.0)
    unrealised_pnl_percent = Column(Float, nullable=False, default=0.0)
    total_pnl = Column(Float, nullable=False, default=0.0)
    total_pnl_percent = Column(Float, nullable=False, default=0.0)

    holding_value = Column(Float, nullable=False, default=0.0)
    order_derived_qty = Column(Float, nullable=False, default=0.0)
    total_buy_qty = Column(Float, nullable=False, default=0.0)
    total_buy_cost = Column(Float, nullable=False, default=0.0)
    total_sell_qty = Column(Float, nullable=False, default=0.0)
    total_sell_proceeds = Column(Float, nullable=False, default=0.0)

    last_processed_order_id = Column(Integer, nullable=True)
    metrics_updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    position = relationship("Position", back_populates="metrics")


class Order(Base):
    """Trading orders (buy/sell)."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint("exchange", "external_order_id", name="uq_order_exchange_external"),
    )

    id = Column(Integer, primary_key=True, index=True)
    position_id = Column(Integer, ForeignKey("positions.id"), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    type = Column(String(10), nullable=False)  # 'buy' or 'sell'
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    executed_at = Column(DateTime, nullable=False, index=True)
    exchange = Column(String(50), nullable=True)
    external_order_id = Column(String(64), nullable=True, index=True)

    position = relationship("Position", back_populates="orders")


class PortfolioSnapshot(Base):
    """Historical portfolio value snapshots."""

    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    total_value = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class FiatDeposit(Base):
    """Fiat injected via exchange fiat rails (synced) or manual SQLite rows."""

    __tablename__ = "fiat_deposits"
    __table_args__ = (
        UniqueConstraint("exchange", "external_order_id", name="uq_fiat_deposit_exchange_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    exchange = Column(String(50), nullable=False, index=True)
    external_order_id = Column(String(128), nullable=True)
    currency = Column(String(16), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    fee = Column(Float, nullable=True)
    status = Column(String(64), nullable=True)
    method = Column(String(128), nullable=True)
    deposited_at = Column(DateTime, nullable=False, index=True)
    source = Column(String(32), nullable=False, default="api_sync")  # api_sync | manual
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


# Database setup
from pathlib import Path

# Get the project root directory (two levels up from this file)
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATABASE_PATH = BASE_DIR / "portfolio.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Needed for SQLite
    echo=False,  # Set to True for SQL query logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Initialize the database by creating all tables."""
    Base.metadata.create_all(bind=engine)
    migrate_tags_schema()
    migrate_manual_positions_schema()


def migrate_tags_schema(bind=None):
    """Ensure tags table exists and positions.tag_id is present (safe for existing DBs)."""
    eng = bind or engine
    Base.metadata.create_all(bind=eng, tables=[Tag.__table__])
    with eng.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(positions)")}
        if "tag_id" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE positions ADD COLUMN tag_id INTEGER REFERENCES tags(id)"
            )
        tag_cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(tags)")}
        if "color" in tag_cols:
            conn.exec_driver_sql("ALTER TABLE tags DROP COLUMN color")
        if "sort_order" in tag_cols:
            conn.exec_driver_sql("ALTER TABLE tags DROP COLUMN sort_order")


def migrate_manual_positions_schema(bind=None):
    """Add manual-position columns and the valuations table (safe for existing DBs)."""
    eng = bind or engine
    Base.metadata.create_all(bind=eng, tables=[PositionValuation.__table__])
    with eng.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(positions)")}
        if "source" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE positions ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'synced'"
            )
        if "display_name" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE positions ADD COLUMN display_name VARCHAR(120)"
            )
        if "external_url" not in cols:
            conn.exec_driver_sql(
                "ALTER TABLE positions ADD COLUMN external_url VARCHAR(500)"
            )


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

