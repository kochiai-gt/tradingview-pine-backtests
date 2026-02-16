import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy
import yfinance as yf
from datetime import datetime, time, timedelta
import pytz

class ORBStrategy(Strategy):
    # Parameters mirroring PineScript inputs
    qty = 3
    tp1_percent = 33
    tp2_percent = 33
    tp3_percent = 34
    rr1 = 1.0
    rr2 = 2.0
    rr3 = 4.0
    sl_buffer = 0.0
    use_be = True
    be_offset = 0.0
    use_trail = False
    trail_pts = 10.0
    show_trail_line = True  # Not used in backtesting.py, but included for completeness

    def init(self):
        self.ny_tz = pytz.timezone('America/New_York')
        # State variables (updated per bar)
        self.or_high = np.nan
        self.or_low = np.nan
        self.entry_taken = False
        self.tp1_hit = False
        self.trail_price = np.nan
        self.original_qty = self.qty
        self.current_position_qty = 0  # Track current position size for tp1_hit detection
        self.entry_price = np.nan
        self.sl_level = np.nan
        self.direction = 0  # 1 for long, -1 for short

    def partial_close(self, fraction):
        size_to_close = max(1.0, round(abs(self.position.size) * fraction))
        if self.position.is_long:
            self.sell(size=size_to_close)
        elif self.position.is_short:
            self.buy(size=size_to_close)

    def is_new_day(self):
        if len(self.data) < 2:
            return False
        prev_dt = self.data.index[-2].astimezone(self.ny_tz)
        curr_dt = self.data.index[-1].astimezone(self.ny_tz)
        return prev_dt.day != curr_dt.day

    def is_in_orb(self):
        dt = self.data.index[-1].astimezone(self.ny_tz)
        start_time = time(9, 30)
        end_time = time(9, 45)
        return start_time <= dt.time() < end_time

    def is_eod(self):
        dt = self.data.index[-1].astimezone(self.ny_tz)
        # Approximate session.islastbar_regular as last bar of data, but check time
        return dt.time() >= time(15, 55) and dt.hour == 15

    def next(self):
        high = self.data.High[-1]
        low = self.data.Low[-1]
        close = self.data.Close[-1]

        if self.is_new_day():
            self.entry_taken = False
            self.tp1_hit = False
            self.or_high = np.nan
            self.or_low = np.nan
            self.trail_price = np.nan
            self.current_position_qty = 0
            self.entry_price = np.nan
            self.sl_level = np.nan
            self.direction = 0

        # ORB calculation
        if self.is_in_orb():
            if np.isnan(self.or_high):
                self.or_high = high
                self.or_low = low
            else:
                self.or_high = max(self.or_high, high)
                self.or_low = min(self.or_low, low)

        # Detect tp1_hit based on position size
        if self.position and abs(self.position.size) < self.original_qty:
            self.tp1_hit = True

        # Breakout entries
        if not self.is_in_orb() and not self.entry_taken and not np.isnan(self.or_high):
            if close > self.or_high:
                self.buy(size=self.qty)
                self.entry_taken = True
                self.tp1_hit = False
                self.trail_price = np.nan
                self.current_position_qty = self.qty
                self.entry_price = close  # Approximate avg_price
                self.direction = 1
                risk = self.entry_price - (self.or_low - self.sl_buffer)
                self.sl_level = self.or_low - self.sl_buffer
            elif close < self.or_low:
                self.sell(size=self.qty)
                self.entry_taken = True
                self.tp1_hit = False
                self.trail_price = np.nan
                self.current_position_qty = self.qty
                self.entry_price = close  # Approximate avg_price
                self.direction = -1
                risk = (self.or_high + self.sl_buffer) - self.entry_price
                self.sl_level = self.or_high + self.sl_buffer

        # Exit logic
        if self.position:
            if self.direction == 1:  # Long
                risk = self.entry_price - (self.or_low - self.sl_buffer)
                tp1_price = self.entry_price + (risk * self.rr1)
                tp2_price = self.entry_price + (risk * self.rr2)
                tp3_price = self.entry_price + (risk * self.rr3)
                sl_level = self.or_low - self.sl_buffer
                if self.use_be and self.tp1_hit:
                    sl_level = self.entry_price + self.be_offset
                if self.use_trail and self.tp1_hit:
                    if np.isnan(self.trail_price):
                        self.trail_price = high - self.trail_pts
                    else:
                        self.trail_price = max(self.trail_price, high - self.trail_pts)
                    sl_level = max(sl_level, self.trail_price)
                self.sl_level = sl_level

                # Check for SL hit (use low for intrabar)
                if low <= sl_level:
                    self.position.close()
                    return

                # Partial TPs (check if high >= tp for potential fill)
                remaining_fraction = 1.0
                if high >= tp1_price and self.tp1_percent > 0:
                    fraction = self.tp1_percent / 100
                    self.partial_close(fraction)
                    remaining_fraction -= fraction
                if high >= tp2_price and self.tp2_percent > 0:
                    fraction = self.tp2_percent / 100 * remaining_fraction  # Adjust for remaining
                    self.partial_close(fraction)
                    remaining_fraction -= fraction
                if high >= tp3_price and self.tp3_percent > 0:
                    self.partial_close(1.0)  # Close remaining
            elif self.direction == -1:  # Short
                risk = (self.or_high + self.sl_buffer) - self.entry_price
                tp1_price = self.entry_price - (risk * self.rr1)
                tp2_price = self.entry_price - (risk * self.rr2)
                tp3_price = self.entry_price - (risk * self.rr3)
                sl_level = self.or_high + self.sl_buffer
                if self.use_be and self.tp1_hit:
                    sl_level = self.entry_price - self.be_offset
                if self.use_trail and self.tp1_hit:
                    if np.isnan(self.trail_price):
                        self.trail_price = low + self.trail_pts
                    else:
                        self.trail_price = min(self.trail_price, low + self.trail_pts)
                    sl_level = min(sl_level, self.trail_price)
                self.sl_level = sl_level

                # Check for SL hit (use high for intrabar)
                if high >= sl_level:
                    self.position.close()
                    return

                # Partial TPs (check if low <= tp for potential fill)
                remaining_fraction = 1.0
                if low <= tp1_price and self.tp1_percent > 0:
                    fraction = self.tp1_percent / 100
                    self.partial_close(fraction)
                    remaining_fraction -= fraction
                if low <= tp2_price and self.tp2_percent > 0:
                    fraction = self.tp2_percent / 100 * remaining_fraction
                    self.partial_close(fraction)
                    remaining_fraction -= fraction
                if low <= tp3_price and self.tp3_percent > 0:
                    self.partial_close(1.0)  # Close remaining

            # EOD close
            if self.is_eod():
                self.position.close()

        if not self.position:
            self.trail_price = np.nan

# Fetch data (adjust dates as needed; using historical for example)
data = yf.download('NQ=F', start=(datetime.now(pytz.timezone('UTC')) - timedelta(days=59)).strftime('%Y-%m-%d'), end=datetime.now(pytz.timezone('UTC')).strftime('%Y-%m-%d'), interval='15m')
data = data.dropna()
if isinstance(data.columns, pd.MultiIndex):
    data.columns = data.columns.get_level_values(0)
data = data[['Open', 'High', 'Low', 'Close', 'Volume']]  # Ensure OHLCV exact for backtesting.py

# Run backtest
bt = Backtest(data, ORBStrategy, cash=100_000, margin=1/10, commission=0.0001)  # Approximate futures margin/commission
stats = bt.run()
print(stats)
# Optional: bt.plot() if you have plotting enabled