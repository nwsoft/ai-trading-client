import sqlite3
import os

# 실제 거래 데이터와 DB 비교
db_path = 'c:/Users/super/SynologyDrive/Works/크몽용바이낸스신버전/noahai_client/data/trading.db'

print("=" * 100)
print("🔍 이미지에 나온 실제 거래 vs 데이터베이스 비교")
print("=" * 100)

# 이미지에 나온 거래 내역 (2025-10-31)
actual_trades = [
    {"time": "2025-10-31 10:11:30", "symbol": "AVAXUSDT", "side": "Buy", "price": 18.3590, "qty": "1 AVAX"},
    {"time": "2025-10-31 10:10:40", "symbol": "ADAUSDT", "side": "Buy", "price": 0.61130, "qty": "9 ADA"},
    {"time": "2025-10-31 10:10:24", "symbol": "DOTUSDT", "side": "Buy", "price": 2.911, "qty": "1.8 DOT"},
    {"time": "2025-10-31 10:10:07", "symbol": "DOTUSDT", "side": "Sell", "price": 2.907, "qty": "1.8 DOT"},
    {"time": "2025-10-31 10:09:43", "symbol": "AVAXUSDT", "side": "Sell", "price": 18.3290, "qty": "1 AVAX"},
    {"time": "2025-10-31 10:09:10", "symbol": "ADAUSDT", "side": "Sell", "price": 0.61050, "qty": "9 ADA"},
]

print("\n📋 이미지에 나온 실제 거래 (2025-10-31):")
for i, trade in enumerate(actual_trades, 1):
    print(f"  {i}. {trade['time']} | {trade['symbol']} | {trade['side']} | {trade['price']} | {trade['qty']}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 오늘 날짜의 거래 확인
print("\n" + "=" * 100)
print("📊 데이터베이스에 2025-10-31 거래가 있는지 확인")
print("=" * 100)

cursor.execute("""
    SELECT id, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, exchange, pnl
    FROM trade_log
    WHERE date(entry_time) = '2025-10-31' OR date(exit_time) = '2025-10-31'
    ORDER BY entry_time DESC
""")

today_trades = cursor.fetchall()

if today_trades:
    print(f"\n✅ 2025-10-31 거래 발견: {len(today_trades)}건")
    for trade in today_trades:
        print(f"\n  ID: {trade[0]}")
        print(f"  심볼: {trade[1]}")
        print(f"  방향: {trade[2]}")
        print(f"  진입가: {trade[3]}")
        print(f"  청산가: {trade[4]}")
        print(f"  수량: {trade[5]}")
        print(f"  진입시간: {trade[6]}")
        print(f"  청산시간: {trade[7]}")
        print(f"  거래소: {trade[8]}")
        print(f"  손익: {trade[9]}")
else:
    print("\n❌ 2025-10-31 거래가 데이터베이스에 없습니다!")

# 모든 거래 확인
print("\n" + "=" * 100)
print("📊 데이터베이스의 모든 거래 확인")
print("=" * 100)

cursor.execute("""
    SELECT id, symbol, side, entry_price, exit_price, quantity, entry_time, exit_time, exchange, pnl
    FROM trade_log
    ORDER BY entry_time DESC
""")

all_trades = cursor.fetchall()
print(f"\n총 거래 수: {len(all_trades)}건\n")

for trade in all_trades:
    print(f"ID: {trade[0]} | {trade[1]} | {trade[2]} | 진입: {trade[3]} | 청산: {trade[4]} | 수량: {trade[5]}")
    print(f"  진입시간: {trade[6]} | 청산시간: {trade[7]} | 거래소: {trade[8]} | 손익: {trade[9]}")
    print()

# exchange_trade_stats 확인
print("=" * 100)
print("📊 exchange_trade_stats 테이블 확인")
print("=" * 100)

cursor.execute("SELECT * FROM exchange_trade_stats")
stats = cursor.fetchall()

if stats:
    print(f"\n통계 데이터: {len(stats)}건")
    for stat in stats:
        print(f"  {stat}")
else:
    print("\n❌ exchange_trade_stats 테이블이 비어있습니다!")

# 테이블 구조 비교
print("\n" + "=" * 100)
print("🔍 trade_log와 exchange_trade_stats 테이블 구조 비교")
print("=" * 100)

print("\n[trade_log 컬럼]")
cursor.execute("PRAGMA table_info(trade_log)")
for col in cursor.fetchall():
    print(f"  - {col[1]} ({col[2]})")

print("\n[exchange_trade_stats 컬럼]")
cursor.execute("PRAGMA table_info(exchange_trade_stats)")
for col in cursor.fetchall():
    print(f"  - {col[1]} ({col[2]})")

conn.close()

print("\n" + "=" * 100)
print("🔍 결론")
print("=" * 100)
print("""
1. 이미지의 실제 거래(2025-10-31)가 DB에 있는지 확인
2. trade_log에는 거래별 상세 정보 저장
3. exchange_trade_stats에는 거래소별 통계 저장
4. 두 테이블의 관계 확인
""")
