import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
from backtesting.lib import crossover
import pandas_ta as ta
import yfinance as yf
from datetime import datetime
import pytz

class ORBNQStrategy(Strategy):
    # Params from Pine
    qty = 3
    tp1_pct = 33
    tp2_pct = 33
    tp3_pct = 34
    rr1 = 1.0
    rr2 = 2.0
    rr3 = 4.0
    sl_buffer = 0.0
    use_be = True
    be_offset = 0.0
    use_trail = False
    trail_pts = 10.0
    
    def init(self):
        self.ny_tz = pytz.timezone('America/New_York')
        self.or_high = pd.Series(index=self.data.index, dtype=float)
        self.or_low = pd.Series(index=self.data.index, dtype=float)
        self.entry_taken = pd.Series(index=self.data.index, dtype=bool)
        self.tp1_hit = pd.Series(index=self.data.index, dtype=bool)
        self.trail_price = pd.Series(index=self.data.index, dtype=float)
        
    def or_period(self, i):
        dt = self.data.index[i].tz_localize('UTC').tz_convert(self.ny_tz)
        return dt.time() >= datetime.strptime('09:30', '%H:%M').time() and dt.time() <= datetime.strptime('09:45', '%H:%M').time()
    
    def next(self):
        i = len(self.data)
        if self.data.index[i-1].day != self.data.index[i].day:  # New day
            self.or_high[i] = np.nan
            self.or_low[i] = np.nan
            self.entry_taken[i] = False
            self.tp1_hit[i] = False
            self.trail_price[i] = np.nan
        
        # ORB calc
        if self.or_period(i):
            self.or_high[i] = self.data.High[i] if np.isnan(self.or_high[i-1]) else max(self.or_high[i-1], self.data.High[i])
            self.or_low[i] = self.data.Low[i] if np.isnan(self.or_low[i-1]) else min(self.or_low[i-1], self.data.Low[i])
        else:
            self.or_high[i] = self.or_high[i-1]
            self.or_low[i] = self.or_low[i-1]
        
        # Breakout
        if not self.entry_taken[i-1] and not np.isnan(self.or_high[i]) and self.data.Close[i] > self.or_high[i]:
            self.buy(size=self.qty)
            self.entry_taken[i] = True
        elif not self.entry_taken[i-1] and not np.isnan(self.or_low[i]) and self.data.Close[i] < self.or_low[i]:
            self.sell(size=self.qty)
            self.entry_taken[i] = True
        
        # Exits (simplified partials via qty_percent approx)
        pos = self.position
        if pos.is_long:
            risk = pos.pl_pct  # Approx
            tp1 = pos.avg_entry_price * (1 + risk * self.rr1)
            tp2 = pos.avg_entry_price * (1 + risk * self.rr2)
            tp3 = pos.avg_entry_price * (1 + risk * self.rr3)
            sl = self.or_low[i] - self.sl_buffer
            
            # BE/Trail
            if self.tp1_hit[i]:
                sl = max(sl, pos.avg_entry_price + self.be_offset)
            
            self.position.close()  # Simplified - full for demo; partials need custom
            
        # Similar for short...
        
        # EOD close
        dt = self.data.index[i].tz_localize('UTC').tz_convert(self.ny_tz)
        if dt.hour == 15 and dt.minute >= 55:
            self.position.close()

# Data
data = yf.download('NQ=F', start='2025-02-16', end='2026-02-16', interval='15m')  # Adjust
bt = Backtest(data, ORBNQStrategy, cash=100000)
stats = bt.run()
print(stats)