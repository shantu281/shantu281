import sys, pandas as pd
sys.path.insert(0, "/home/user/shantu281")
from deltabot.backtest import trades_frame
from deltabot.data import load_candles
from deltabot.real_backtest import RealConfig, run_real_backtest
from deltabot.strategies import MoveAdaptiveSeller
stop = float(sys.argv[1])
index = load_candles("data/BTC_index_5m.csv")
s = MoveAdaptiveSeller(f"stop_{stop}", stop_mult=stop, params={"width": 0.5})
df = trades_frame(run_real_backtest(index, "data/options", s, RealConfig(qty_btc=0.1, hours_before=float(sys.argv[3]))))
df.to_csv(sys.argv[2], index=False)
