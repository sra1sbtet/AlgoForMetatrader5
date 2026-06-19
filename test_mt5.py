import MetaTrader5 as mt5

print(mt5.initialize())
print(mt5.last_error())

if mt5.initialize():
    print(mt5.terminal_info())
    mt5.shutdown()