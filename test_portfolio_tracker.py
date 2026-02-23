"""Tests for BlackRoad Portfolio Tracker."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ["PORTFOLIO_DB"] = str(Path(tempfile.mkdtemp()) / "test_portfolio.db")
sys.path.insert(0, str(Path(__file__).parent))
from main import PortfolioTracker, init_db


class TestPortfolioTracker(unittest.TestCase):
    def setUp(self):
        init_db()
        self.tracker = PortfolioTracker()
        self.portfolio = self.tracker.create_portfolio("Test Portfolio")

    def test_create_portfolio(self):
        p = self.tracker.create_portfolio("My Portfolio", currency="EUR")
        self.assertIsNotNone(p.id)
        self.assertEqual(p.currency, "EUR")

    def test_add_asset(self):
        a = self.tracker.add_asset(self.portfolio.id, "AAPL", "Apple Inc", 10.0, 150.0)
        self.assertEqual(a.symbol, "AAPL")
        self.assertEqual(a.quantity, 10.0)

    def test_calculate_returns_no_price_update(self):
        self.tracker.add_asset(self.portfolio.id, "MSFT", "Microsoft", 5.0, 300.0)
        returns = self.tracker.calculate_returns(self.portfolio.id)
        self.assertEqual(returns["total_cost"], 1500.0)

    def test_update_price_and_returns(self):
        self.tracker.add_asset(self.portfolio.id, "GOOGL", "Alphabet", 2.0, 100.0)
        self.tracker.update_price("GOOGL", 150.0)
        returns = self.tracker.calculate_returns(self.portfolio.id)
        asset = next(a for a in returns["assets"] if a["symbol"] == "GOOGL")
        self.assertAlmostEqual(asset["unrealized_gain"], 100.0)
        self.assertAlmostEqual(asset["unrealized_gain_pct"], 50.0)

    def test_rebalance_suggestion(self):
        self.tracker.add_asset(self.portfolio.id, "AAPL2", "Apple", 10.0, 100.0)
        self.tracker.update_price("AAPL2", 100.0)
        self.tracker.add_asset(self.portfolio.id, "MSFT2", "Microsoft", 10.0, 100.0)
        self.tracker.update_price("MSFT2", 100.0)
        result = self.tracker.rebalance_suggestion(self.portfolio.id, {"AAPL2": 60.0, "MSFT2": 40.0})
        self.assertIn("suggestions", result)

    def test_record_transaction(self):
        txn = self.tracker.record_transaction(self.portfolio.id, "TSLA", "buy", 3.0, 200.0)
        self.assertEqual(txn["symbol"], "TSLA")
        self.assertEqual(txn["type"], "buy")

    def test_list_portfolios(self):
        self.tracker.create_portfolio("List Test 1")
        self.tracker.create_portfolio("List Test 2")
        items = self.tracker.list_portfolios()
        self.assertGreaterEqual(len(items), 2)


if __name__ == "__main__":
    unittest.main()
