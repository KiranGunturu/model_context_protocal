from fastmcp import FastMCP
import requests
from dotenv import load_dotenv
import os
import re
import pandas as pd
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus

load_dotenv()
mcp = FastMCP("my-datagpt-server")

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
DEFAULT_SERVER = os.getenv("SQL_SERVER", r"localhost\MSSQLSERVER03")
DEFAULT_DATABASE = os.getenv("SQL_DATABASE", "retail")

# Built once on first use and reused by every tool.
_engine = None


# ---------- plain helpers (safe to call from other functions) ----------

def _build_engine(server: str, database: str):
    odbc = quote_plus(
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "Encrypt=yes;TrustServerCertificate=yes;"
    )
    return create_engine(f"mssql+pyodbc:///?odbc_connect={odbc}", pool_pre_ping=True)


def _get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine(DEFAULT_SERVER, DEFAULT_DATABASE)
    return _engine


def _validate_select(query: str) -> str:
    normalized = (query or "").strip()
    if not normalized:
        raise ValueError("The query is empty.")
    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()
    if any(tok in normalized for tok in (";", "--", "/*", "*/")):
        raise ValueError("Only one SELECT statement is allowed.")
    # Allow plain SELECT or a CTE (WITH ... SELECT)
    if not re.match(r"^(SELECT|WITH)\b", normalized, flags=re.IGNORECASE):
        raise ValueError("Only SELECT queries are allowed.")
    if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|INTO)\b",
                 normalized, flags=re.IGNORECASE):
        raise ValueError("Write/DDL keywords are not allowed.")
    return normalized


def _run_select(query: str, params: dict | None = None) -> list[dict]:
    sql = _validate_select(query)
    with _get_engine().connect() as conn:
        df = pd.read_sql(text(sql), conn, params=params)
    # JSON-friendly output (DataFrames don't serialize cleanly over MCP)
    return df.to_dict(orient="records")


# ---------- MCP tools ----------

@mcp.tool
def get_engine(server: str = DEFAULT_SERVER, database: str = DEFAULT_DATABASE) -> str:
    """(Re)connect to a SQL Server database. Optional: tools connect to the default DB automatically."""
    global _engine
    _engine = _build_engine(server, database)
    with _engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return f"Connected to {database} on {server}"


@mcp.tool
def get_stock_price(ticker: str) -> dict | str:
    """Fetch the current price of a stock given its ticker symbol."""
    try:
        response = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker.upper(), "token": FINNHUB_API_KEY},
            timeout=10,
        )
        response.raise_for_status()
        price = response.json().get("c")
        if not price:
            return "Ticker not found"
        return {"ticker": ticker.upper(), "price": price}
    except requests.RequestException as e:
        return f"Error fetching price: {e}"


@mcp.tool
def validate_select_query(query: str) -> str:
    """Check that a query is exactly one read-only SELECT (or WITH ... SELECT) statement."""
    _validate_select(query)
    return "OK"


@mcp.tool
def run_query(query: str, params: dict | None = None) -> list[dict]:
    """Run a read-only SELECT query and return rows as a list of records."""
    return _run_select(query, params)


@mcp.tool
def get_schema(table_name: str) -> list[dict]:
    """Return column names and data types for a dbo table."""
    query = """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_NAME = :table_name
        ORDER BY ORDINAL_POSITION
    """
    return _run_select(query, {"table_name": table_name})


@mcp.tool
def get_tables() -> list[dict]:
    """Return all user tables in the dbo schema."""
    query = """
        SELECT TABLE_NAME
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo' AND TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_NAME
    """
    return _run_select(query)


# local
# if __name__ == "__main__":
#     mcp.run()

# http

if __name__ == "__main__":
    mcp.run(
        transport="http",
        host="192.168.1.213",
        port=8000
    )
