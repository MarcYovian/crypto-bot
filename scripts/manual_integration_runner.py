import asyncio
from datetime import datetime
from src.database.connection import init_db, AsyncSessionLocal
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService, SymbolInfo


async def test_repositories():
    await init_db()

    async with AsyncSessionLocal() as session:
        signal_repo = SignalRepository(session)
        trade_repo = TradeRepository(session)

        # 1. Simpan Daily Risk
        today = datetime.now().strftime("%Y-%m-%d")
        daily_risk = await trade_repo.create_daily_risk_snapshot(today, balance=1000.0, risk_percent=2.0)
        print(f"✅ Snapshot Risk Created: {daily_risk.date} | Risk Amount: ${daily_risk.risk_amount}")

        # 2. Parse & Simpan Signal
        raw_text = "#BTCUSDT LONG Entry: 65000 SL: 64000 TP1: 67000 Confidence: 85%"
        parsed = SignalParserService.parse(raw_text)
        signal = await signal_repo.create_signal_from_parsed(parsed)
        print(f"✅ Signal Saved: ID={signal.id} | Symbol={signal.symbol} | Confirm Status={signal.confirmation_status}")

        # 3. Hitung Risk & Buat Trade Record
        btc_info = SymbolInfo("BTCUSDT", 2, 3, 0.10, 0.001, 0.001, 5.0)
        risk_res = RiskCalculatorService.calculate_position(
            daily_risk_amount=daily_risk.risk_amount,
            entry_price=parsed.entry_min,
            stop_loss_price=parsed.sl_price,
            side=parsed.side,
            max_leverage=20,
            symbol_info=btc_info
        )

        trade = await trade_repo.create_trade_with_risk(
            signal_id=signal.id,
            symbol=signal.symbol,
            side=signal.side,
            leverage=20,
            risk_date=today,
            risk_res=risk_res,
            tp1_price=parsed.tp_prices[0]
        )
        print(f"✅ Trade & TradeRisk Created: Trade ID={trade.id} | Qty={trade.position_size} BTC")

        # 4. Catat Order
        entry_order = await trade_repo.create_order(
            trade_id=trade.id,
            purpose="ENTRY",
            order_type="LIMIT",
            side="BUY",
            qty=trade.position_size,
            price=trade.entry_price,
            binance_order_id="BINANCE_ORD_998123"
        )
        print(f"✅ Order Created: Purpose={entry_order.purpose} | Binance ID={entry_order.binance_order_id}")

        # 5. Log Event
        await trade_repo.log_event(trade.id, "ENTRY", payload_json='{"status": "FILLED"}')
        print(f"✅ Trade Event Logged!")

if __name__ == "__main__":
    asyncio.run(test_repositories())
