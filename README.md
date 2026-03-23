# blackroad-portfolio-tracker

> Investment portfolio tracking and analytics

Part of the [BlackRoad OS](https://blackroad.io) ecosystem — [BlackRoad-Ventures](https://github.com/BlackRoad-Ventures)

---

# blackroad-portfolio-tracker

![CI](https://github.com/BlackRoad-Ventures/blackroad-portfolio-tracker/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

Investment portfolio tracking and analytics for the BlackRoad OS platform.

## Features
- Multi-portfolio management
- Asset tracking with cost basis and current price
- Return calculations (unrealized gain/loss)
- Rebalancing suggestions
- Transaction history
- Performance summary by asset type

## Usage
```bash
python main.py create "My Portfolio"
python main.py add-asset <id> AAPL "Apple Inc" 10 150.0
python main.py update-price AAPL 175.0
python main.py returns <id>
python main.py rebalance <id> --target '{"AAPL":60,"MSFT":40}'
python main.py performance <id>
```
