#!/usr/bin/env python3
"""
BlackRoad Portfolio Tracker — Investment portfolio tracking and analytics.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from pathlib import Path
from typing import Any, Optional


DB_PATH = Path(os.environ.get("PORTFOLIO_DB", "~/.blackroad/portfolio.db")).expanduser()


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                description TEXT,
                currency    TEXT NOT NULL DEFAULT 'USD',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS assets (
                id           TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                symbol       TEXT NOT NULL,
                name         TEXT NOT NULL,
                asset_type   TEXT NOT NULL DEFAULT 'stock',
                quantity     REAL NOT NULL,
                cost_basis   REAL NOT NULL,
                current_price REAL,
                currency     TEXT NOT NULL DEFAULT 'USD',
                added_at     TEXT NOT NULL,
                updated_at   TEXT NOT NULL,
                notes        TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS transactions (
                id           TEXT PRIMARY KEY,
                portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
                asset_id     TEXT REFERENCES assets(id),
                symbol       TEXT NOT NULL,
                txn_type     TEXT NOT NULL,
                quantity     REAL NOT NULL,
                price        REAL NOT NULL,
                fees         REAL NOT NULL DEFAULT 0,
                txn_date     TEXT NOT NULL,
                notes        TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS price_history (
                id           TEXT PRIMARY KEY,
                symbol       TEXT NOT NULL,
                price        REAL NOT NULL,
                recorded_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_asset_portfolio ON assets(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_txn_portfolio ON transactions(portfolio_id);
            CREATE INDEX IF NOT EXISTS idx_price_symbol ON price_history(symbol);
        """)


@dataclass
class Asset:
    id: str
    portfolio_id: str
    symbol: str
    name: str
    asset_type: str
    quantity: float
    cost_basis: float
    current_price: Optional[float]
    currency: str
    added_at: str
    updated_at: str
    notes: str = ""

    @property
    def market_value(self) -> float:
        if self.current_price is None:
            return self.quantity * self.cost_basis
        return self.quantity * self.current_price

    @property
    def total_cost(self) -> float:
        return self.quantity * self.cost_basis

    @property
    def unrealized_gain(self) -> float:
        return self.market_value - self.total_cost

    @property
    def unrealized_gain_pct(self) -> float:
        if self.total_cost == 0:
            return 0.0
        return (self.unrealized_gain / self.total_cost) * 100

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Asset":
        return cls(
            id=row["id"], portfolio_id=row["portfolio_id"], symbol=row["symbol"],
            name=row["name"], asset_type=row["asset_type"], quantity=row["quantity"],
            cost_basis=row["cost_basis"], current_price=row["current_price"],
            currency=row["currency"], added_at=row["added_at"],
            updated_at=row["updated_at"], notes=row["notes"] or "",
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["market_value"] = self.market_value
        d["total_cost"] = self.total_cost
        d["unrealized_gain"] = self.unrealized_gain
        d["unrealized_gain_pct"] = round(self.unrealized_gain_pct, 2)
        return d


@dataclass
class Portfolio:
    id: str
    name: str
    description: str
    currency: str
    created_at: str
    updated_at: str
    assets: list[Asset] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return sum(a.market_value for a in self.assets)

    @property
    def total_cost(self) -> float:
        return sum(a.total_cost for a in self.assets)

    @property
    def total_gain(self) -> float:
        return self.total_value - self.total_cost

    @property
    def total_gain_pct(self) -> float:
        if self.total_cost == 0:
            return 0.0
        return (self.total_gain / self.total_cost) * 100

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Portfolio":
        return cls(
            id=row["id"], name=row["name"], description=row["description"] or "",
            currency=row["currency"], created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


class PortfolioTracker:

    def create_portfolio(self, name: str, description: str = "", currency: str = "USD") -> Portfolio:
        pid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO portfolios(id, name, description, currency, created_at, updated_at) VALUES (?,?,?,?,?,?)",
                (pid, name, description, currency, now, now),
            )
        return Portfolio(id=pid, name=name, description=description, currency=currency,
                         created_at=now, updated_at=now)

    def add_asset(self, portfolio_id: str, symbol: str, name: str, quantity: float,
                  cost_basis: float, asset_type: str = "stock", currency: str = "USD",
                  notes: str = "") -> Asset:
        aid = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO assets(id, portfolio_id, symbol, name, asset_type, quantity, cost_basis, "
                "currency, added_at, updated_at, notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (aid, portfolio_id, symbol, name, asset_type, quantity, cost_basis, currency, now, now, notes),
            )
        return Asset(id=aid, portfolio_id=portfolio_id, symbol=symbol, name=name,
                     asset_type=asset_type, quantity=quantity, cost_basis=cost_basis,
                     current_price=None, currency=currency, added_at=now, updated_at=now, notes=notes)

    def update_price(self, symbol: str, price: float) -> int:
        now = datetime.utcnow().isoformat()
        pid = str(uuid.uuid4())
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO price_history(id, symbol, price, recorded_at) VALUES (?,?,?,?)",
                (pid, symbol, price, now),
            )
            result = conn.execute(
                "UPDATE assets SET current_price=?, updated_at=? WHERE symbol=?",
                (price, now, symbol),
            )
            return result.rowcount

    def record_transaction(self, portfolio_id: str, symbol: str, txn_type: str,
                           quantity: float, price: float, fees: float = 0.0,
                           txn_date: str | None = None, notes: str = "") -> dict:
        tid = str(uuid.uuid4())
        txn_date = txn_date or datetime.utcnow().isoformat()
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO transactions(id, portfolio_id, symbol, txn_type, quantity, price, fees, txn_date, notes) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (tid, portfolio_id, symbol, txn_type, quantity, price, fees, txn_date, notes),
            )
        return {"id": tid, "symbol": symbol, "type": txn_type, "quantity": quantity,
                "price": price, "fees": fees, "date": txn_date}

    def load_portfolio(self, portfolio_id: str) -> Portfolio:
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM portfolios WHERE id=?", (portfolio_id,)).fetchone()
            if not row:
                raise ValueError(f"Portfolio {portfolio_id!r} not found")
            portfolio = Portfolio.from_row(row)
            asset_rows = conn.execute("SELECT * FROM assets WHERE portfolio_id=?", (portfolio_id,)).fetchall()
            portfolio.assets = [Asset.from_row(r) for r in asset_rows]
        return portfolio

    def calculate_returns(self, portfolio_id: str) -> dict:
        portfolio = self.load_portfolio(portfolio_id)
        asset_returns = []
        for asset in portfolio.assets:
            asset_returns.append({
                "symbol": asset.symbol,
                "name": asset.name,
                "quantity": asset.quantity,
                "cost_basis": asset.cost_basis,
                "current_price": asset.current_price,
                "market_value": round(asset.market_value, 2),
                "total_cost": round(asset.total_cost, 2),
                "unrealized_gain": round(asset.unrealized_gain, 2),
                "unrealized_gain_pct": round(asset.unrealized_gain_pct, 2),
            })
        return {
            "portfolio_id": portfolio.id,
            "portfolio_name": portfolio.name,
            "total_value": round(portfolio.total_value, 2),
            "total_cost": round(portfolio.total_cost, 2),
            "total_gain": round(portfolio.total_gain, 2),
            "total_gain_pct": round(portfolio.total_gain_pct, 2),
            "assets": asset_returns,
            "asset_count": len(portfolio.assets),
            "as_of": datetime.utcnow().isoformat(),
        }

    def rebalance_suggestion(self, portfolio_id: str, target_allocation: dict[str, float]) -> dict:
        """Suggest trades to rebalance portfolio to target allocation percentages."""
        portfolio = self.load_portfolio(portfolio_id)
        total = portfolio.total_value
        if total == 0:
            return {"error": "Portfolio has no value to rebalance"}

        suggestions: list[dict] = []
        current_alloc: dict[str, float] = {}
        asset_map = {a.symbol: a for a in portfolio.assets}

        for asset in portfolio.assets:
            current_alloc[asset.symbol] = (asset.market_value / total) * 100

        for symbol, target_pct in target_allocation.items():
            current_pct = current_alloc.get(symbol, 0.0)
            current_val = (current_pct / 100) * total
            target_val = (target_pct / 100) * total
            diff = target_val - current_val
            asset = asset_map.get(symbol)
            price = asset.current_price or asset.cost_basis if asset else None
            if price and price > 0:
                shares_to_trade = diff / price
                suggestions.append({
                    "symbol": symbol,
                    "action": "buy" if diff > 0 else "sell",
                    "current_pct": round(current_pct, 2),
                    "target_pct": target_pct,
                    "diff_pct": round(target_pct - current_pct, 2),
                    "amount_usd": round(abs(diff), 2),
                    "shares": round(abs(shares_to_trade), 4),
                })

        return {
            "portfolio_id": portfolio_id,
            "total_value": round(total, 2),
            "suggestions": sorted(suggestions, key=lambda x: abs(x["diff_pct"]), reverse=True),
            "current_allocation": {k: round(v, 2) for k, v in current_alloc.items()},
        }

    def performance_summary(self, portfolio_id: str) -> dict:
        portfolio = self.load_portfolio(portfolio_id)
        by_type: dict[str, dict] = {}
        for asset in portfolio.assets:
            t = asset.asset_type
            if t not in by_type:
                by_type[t] = {"value": 0.0, "cost": 0.0, "count": 0}
            by_type[t]["value"] += asset.market_value
            by_type[t]["cost"] += asset.total_cost
            by_type[t]["count"] += 1

        return {
            "by_type": {k: {
                "value": round(v["value"], 2),
                "cost": round(v["cost"], 2),
                "gain": round(v["value"] - v["cost"], 2),
                "count": v["count"],
            } for k, v in by_type.items()},
            "top_gainers": sorted(
                [{"symbol": a.symbol, "gain_pct": round(a.unrealized_gain_pct, 2)} for a in portfolio.assets],
                key=lambda x: x["gain_pct"], reverse=True,
            )[:5],
            "top_losers": sorted(
                [{"symbol": a.symbol, "gain_pct": round(a.unrealized_gain_pct, 2)} for a in portfolio.assets],
                key=lambda x: x["gain_pct"],
            )[:5],
        }

    def list_portfolios(self) -> list[dict]:
        with get_conn() as conn:
            rows = conn.execute("SELECT * FROM portfolios ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]


def main() -> None:
    init_db()
    parser = argparse.ArgumentParser(prog="portfolio", description="BlackRoad Portfolio Tracker")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p = sub.add_parser("create", help="Create portfolio")
    p.add_argument("name"); p.add_argument("--currency", default="USD")

    p = sub.add_parser("add-asset", help="Add asset to portfolio")
    p.add_argument("portfolio_id"); p.add_argument("symbol"); p.add_argument("name")
    p.add_argument("quantity", type=float); p.add_argument("cost_basis", type=float)
    p.add_argument("--type", default="stock")

    p = sub.add_parser("update-price", help="Update asset price")
    p.add_argument("symbol"); p.add_argument("price", type=float)

    p = sub.add_parser("returns", help="Calculate portfolio returns")
    p.add_argument("portfolio_id")

    p = sub.add_parser("rebalance", help="Suggest rebalancing")
    p.add_argument("portfolio_id")
    p.add_argument("--target", default="{}", help='JSON target allocation e.g. {"AAPL":40,"GOOG":60}')

    p = sub.add_parser("performance", help="Performance summary")
    p.add_argument("portfolio_id")

    p = sub.add_parser("list", help="List all portfolios")

    p = sub.add_parser("buy", help="Record a buy transaction")
    p.add_argument("portfolio_id"); p.add_argument("symbol")
    p.add_argument("quantity", type=float); p.add_argument("price", type=float)
    p.add_argument("--fees", type=float, default=0.0)

    args = parser.parse_args()
    tracker = PortfolioTracker()

    if args.command == "create":
        p = tracker.create_portfolio(args.name, currency=args.currency)
        print(json.dumps({"id": p.id, "name": p.name}, indent=2))
    elif args.command == "add-asset":
        a = tracker.add_asset(args.portfolio_id, args.symbol, args.name,
                               args.quantity, args.cost_basis, asset_type=args.type)
        print(json.dumps(a.to_dict(), indent=2))
    elif args.command == "update-price":
        n = tracker.update_price(args.symbol, args.price)
        print(f"Updated {n} asset(s) with {args.symbol} = ${args.price}")
    elif args.command == "returns":
        print(json.dumps(tracker.calculate_returns(args.portfolio_id), indent=2))
    elif args.command == "rebalance":
        target = json.loads(args.target)
        print(json.dumps(tracker.rebalance_suggestion(args.portfolio_id, target), indent=2))
    elif args.command == "performance":
        print(json.dumps(tracker.performance_summary(args.portfolio_id), indent=2))
    elif args.command == "list":
        print(json.dumps(tracker.list_portfolios(), indent=2))
    elif args.command == "buy":
        txn = tracker.record_transaction(args.portfolio_id, args.symbol, "buy",
                                          args.quantity, args.price, fees=args.fees)
        print(json.dumps(txn, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
