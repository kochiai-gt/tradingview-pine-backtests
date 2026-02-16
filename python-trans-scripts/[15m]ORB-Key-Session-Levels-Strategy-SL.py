import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
import pandas_ta as ta
import yfinance as yf
from datetime import datetime
import pytz

class ORBKeySessionStrategy(Strategy):
    sl_pct = 0.02  # 2%
    tp_rr = 2  # 1:2
    size_pct = 0.01
    
    def init(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.orb_high = pd.Series(dtype=float)
        self.orb_low = pd.Series(dtype=float)
        self.orb_complete = pd.Series(dtype=bool)
    
    def or_period(self, i):
        dt = self.data.index[i].tz_localize('UTC').tz_convert(self.ny_tz)
        return 9 <= dt.hour < 10  # Approx 9:30-9:45 -> first hour proxy for daily
    
    def next(self):
        i = len(self.data)
        if self.data.index[i].day != self.data.index[i-1].day:
            self.orb_high[i] = np.nan
            self.orb_low[i] = np.nan
            self.orb_complete[i] = False
        
        # ORB
        if self.or_period(i):
            self.orb_high[i] = self.data.High[i] if np.isnan(self.orb_high[i-1]) else max(self.orb_high[i-1], self.data.High[i])
            self.orb_low[i] = self.data.Low[i] if np.isnan(self.orb_low[i-1]) else min(self.orb_low[i-1], self.data.Low[i])
        else:
            self.orb_high[i] = self.orb_high[i-1]
            self.orb_low[i] = self.orb_low[i-1]
            self.orb_complete[i] = True
        
        # Breakout (simplified)
        if self.orb_complete[i] and not self.position:
            if crossover(self.data.Close, self.orb_high[i]):
                sl = self.data.Close[i] * (1 - self.sl_pct)
                tp = self.data.Close[i] * (1 + self.sl_pct * self.tp_rr)
                self.buy(sl=sl, tp=tp)
            elif crossover(self.orb_low[i], self.data.Close):  # crossunder
                sl = self.data.Close[i] * (1 + self.sl_pct)
                tp = self.data.Close[i] * (1 - self.sl_pct * self.tp_rr)
                self.sell(sl=sl, tp=tp)

# Data (4h BTC 1y)
data = yf.download('BTC-USD', start='2025-02-16', interval='4h')
bt = Backtest(data, ORBKeySessionStrategy)
stats = bt.run()
print(stats)