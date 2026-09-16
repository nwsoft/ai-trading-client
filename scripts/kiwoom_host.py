"""PyInstaller entry point; build with Windows 32-bit Python only."""
from trading.exchanges.adapters.kiwoom_host_launcher import main

if __name__ == "__main__":
    main()
