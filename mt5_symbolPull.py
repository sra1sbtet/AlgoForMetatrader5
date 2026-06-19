import MetaTrader5 as mt5

mt5.initialize()

symbols = mt5.symbols_get()

for s in symbols:
    if "100" in s.name or "NAS" in s.name or "TEC" in s.name:
        print(s.name)

mt5.shutdown()