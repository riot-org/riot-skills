"""零依赖 SVG 图表库。各函数返回完整 SVG 字符串，CLI 见 scripts/render_svg.py。"""
from .behavior import chips, daily_moves, national_team
from .card import stock_card
from .fundamentals import cashflow, growth_gap
from .market import breadth_history, regime, sector_heatmap
from .portfolio import allocation, scores
from .price import kline, performance, valuation_band

__all__ = ["kline", "performance", "valuation_band", "cashflow", "growth_gap", "regime", "sector_heatmap",
           "breadth_history", "scores", "allocation", "stock_card", "chips", "national_team", "daily_moves"]
