"""CEFBOT -- a standalone paper/hypothetical forward-trading bot for the T12 CEF discount-LEVEL
tilt (the one bar-clearing revive of THOROUGH_REEXAM.md R1).

PAPER ONLY. No real orders, no real money, no broker trading endpoint. Marks are mark-to-market
against realised prices, exactly like scripts/trading_bot/basket_forward.py.

Modules:
  strategy  -- the FROZEN rule (sha256-verified against the pre-registration) + book construction
  bot       -- the paper execution + weekly position manager (one cycle per invocation)
  evaluate  -- the read-only evaluate-and-improve loop (two benchmarks, gates, kill switch)

CLI:  python -m scripts.trading_bot.cefbot <selftest|show|run|run-dry|evaluate|proof|status>
"""
