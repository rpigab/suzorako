from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from suzorako.config import settings

metadata = MetaData()

commodities = Table(
    "commodities",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("mnemonic", Text, nullable=False),   # EUR, USD
    Column("fullname", Text),
    Column("namespace", Text, nullable=False),  # CURRENCY | STOCK
    Column("fraction", Integer, nullable=False, default=100),
)

accounts = Table(
    "accounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("guid", Text, unique=True, nullable=False),
    Column("name", Text, nullable=False),
    # ASSET | LIABILITY | INCOME | EXPENSE | EQUITY
    Column("account_type", Text, nullable=False),
    Column("commodity_id", Integer, ForeignKey("commodities.id")),
    Column("parent_id", Integer, ForeignKey("accounts.id"), nullable=True),
    Column("placeholder", Integer, nullable=False, default=0),
    Column("description", Text, default=""),
    Column("hidden", Integer, nullable=False, default=0),
)

transactions = Table(
    "transactions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("guid", Text, unique=True, nullable=False),
    Column("post_date", Text, nullable=False),    # YYYY-MM-DD
    Column("enter_date", Text, nullable=False),   # YYYY-MM-DDTHH:MM:SS
    Column("description", Text, nullable=False, default=""),
    Column("notes", Text, default=""),
    Column("commodity_id", Integer, ForeignKey("commodities.id")),
)

splits = Table(
    "splits",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("guid", Text, unique=True, nullable=False),
    Column("transaction_id", Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Integer, ForeignKey("accounts.id"), nullable=False),
    Column("memo", Text, default=""),
    Column("value_num", Integer, nullable=False),
    Column("value_denom", Integer, nullable=False),
    Column("quantity_num", Integer, nullable=False),
    Column("quantity_denom", Integer, nullable=False),
    Column("reconcile_state", Text, nullable=False, default="n"),  # n | c | y
    Column("reconcile_date", Text, nullable=True),
    Column("external_id", Text, nullable=True),  # OFX FITID pour dédup
)

budgets = Table(
    "budgets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", Text, nullable=False),
    Column("period_start", Text, nullable=False),  # YYYY-MM-DD
    Column("period_type", Text, nullable=False),   # monthly | annual
)

budget_amounts = Table(
    "budget_amounts",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("budget_id", Integer, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False),
    Column("account_id", Integer, ForeignKey("accounts.id"), nullable=False),
    Column("period_num", Integer, nullable=False),  # 1-12
    Column("amount_num", Integer, nullable=False),
    Column("amount_denom", Integer, nullable=False),
)

Index("idx_splits_transaction", splits.c.transaction_id)
Index("idx_splits_account", splits.c.account_id)
Index("idx_splits_external_id", splits.c.external_id, unique=True, sqlite_where=splits.c.external_id.isnot(None))
Index("idx_transactions_post_date", transactions.c.post_date)
Index("idx_accounts_parent", accounts.c.parent_id)

# Moteur async (requêtes FastAPI)
async_engine = create_async_engine(settings.database_url, echo=settings.debug)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)

# Moteur sync (Alembic)
sync_engine = create_engine(settings.database_url_sync, echo=settings.debug)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
