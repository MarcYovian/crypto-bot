from config.settings import settings
import logging
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from pytz import timezone

from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.services.signal_parser import ParsedSignal
from src.services.execution_engine import BinanceExecutionEngine, ExecutionResponse
from src.services.precision_filter import SymbolInfo
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult

logger = logging.getLogger(__name__)
WIB_TZ = timezone("Asia/Jakarta")

@dataclass
class PreparedTrade:
    """A trade that has been risk-calculated and is ready for execution.

    Attributes:
        trade_id: Database ID of the created trade record.
        signal_id: Associated signal ID.
        parsed: Parsed signal data (symbol, side, entry, TP levels, etc.).
        risk_res: Result of the risk calculation (position size, margin, etc.).
        symbol_info: Binance exchange filters for the symbol.
        remaining_balance: Account balance minus required margin for this trade.
        loss_pct: Risk amount as a percentage of the total daily balance.
    """
    trade_id: int
    signal_id: int
    parsed: ParsedSignal
    risk_res: RiskCalculationResult
    symbol_info: SymbolInfo
    remaining_balance: float
    loss_pct: float

class TradeService:
    """Orchestrates the trade lifecycle: risk calculation, DB persistence, and execution.

    Coordinates between the risk calculator, execution engine, and repositories
    to convert a parsed signal into an executed Binance Futures position.
    """

    def __init__(self, execution_engine: BinanceExecutionEngine, trade_repo: TradeRepository, signal_repo: SignalRepository):
        self.execution_engine = execution_engine
        self.trade_repo = trade_repo
        self.signal_repo = signal_repo

    async def prepare_trade(self, signal_id: int, parsed: ParsedSignal) -> tuple[bool, str, Optional[PreparedTrade]]:
        """Calculate risk, persist trade record, and return a PreparedTrade.

        Steps:
        1. Load today's daily risk snapshot (or create one from the current
           USDT balance and a 2 % risk-per-trade default).
        2. Fetch symbol info (price precision, LOT_SIZE, etc.) from Binance.
        3. Run :meth:`RiskCalculatorService.calculate_position` to derive
           position size, margin, and actual risk.
        4. If the risk calculation is invalid, mark the signal as ``REJECTED``.
        5. Insert a trade row into the database with all calculated parameters.
        6. Return a ``PreparedTrade`` ready for execution.

        Args:
            signal_id:
                Primary key of the signal in the database.
            parsed:
                Parsed signal with entry, stop-loss, TP levels, and side.

        Returns:
            A 3-tuple ``(success, message, prepared_trade)``.  If the balance
            is below $1 or risk calculation fails, ``prepared_trade`` is
            ``None``.
        """
        try:
            today_str = datetime.now(WIB_TZ).strftime("%Y-%m-%d")

            daily_risk = await self.trade_repo.get_daily_risk(today_str)
            if not daily_risk:
                balance_data = await self.execution_engine.fetch_balance()
                usdt_balance = float(balance_data.get('USDT', {}).get('total', 0.0))
                if usdt_balance <= 0:
                    logger.error("USDT Balance < $1, STOP Trading")
                    return False, "USDT Balance < $1, STOP Trading", None

                daily_risk = await self.trade_repo.create_daily_risk_snapshot(
                    date_str=today_str,
                    balance=usdt_balance,
                    risk_percent=2.0
                )

                logger.info(f"Daily Risk Snapshot Saved! Balance: ${daily_risk.balance:.2f} | Risk Amount: ${daily_risk.risk_amount:.2f}")

            symbol_info = await self.execution_engine.fetch_symbol_info(parsed.symbol)

            risk_res = RiskCalculatorService.calculate_position(
                daily_risk_amount=daily_risk.risk_amount,
                entry_price=parsed.entry_min,
                stop_loss_price=parsed.sl_price,
                side=parsed.side,
                max_leverage=settings.DEFAULT_LEVERAGE,
                symbol_info=symbol_info
            )

            if not risk_res.is_valid:
                await self.signal_repo.update_signal_status(signal_id=signal_id, status="REJECTED")
                return False, risk_res.error_message, None

            trade = await self.trade_repo.create_trade_with_risk(
                signal_id=signal_id,
                symbol=parsed.symbol,
                side=parsed.side,
                leverage=risk_res.leverage,
                risk_date=today_str,
                risk_res=risk_res,
                tp1_price=parsed.tp_prices[0] if len(parsed.tp_prices) > 0 else None,
                tp2_price=parsed.tp_prices[1] if len(parsed.tp_prices) > 1 else None,
                tp3_price=parsed.tp_prices[2] if len(parsed.tp_prices) > 2 else None,
            )

            remaining_balance = daily_risk.balance - risk_res.required_margin
            loss_pct = (risk_res.risk_amount / daily_risk.balance) * 100

            prepared = PreparedTrade(
                trade_id=trade.id,
                signal_id=signal_id,
                parsed=parsed,
                risk_res=risk_res,
                symbol_info=symbol_info,
                remaining_balance=remaining_balance,
                loss_pct=loss_pct
            )

            return True, "Trade Prepared Successfully", prepared

        except Exception:
            logger.error(f"Failed to prepare trade for signal {signal_id}: {traceback.format_exc()}")
            await self.signal_repo.update_signal_status(signal_id=signal_id, status="REJECTED")
            return False, "Internal error during trade preparation.", None

    
    async def execute_trade(self, prepared: PreparedTrade) -> tuple[bool, str, ExecutionResponse]:
        """Submit the prepared trade to the Binance execution pipeline.

        Delegates to :meth:`BinanceExecutionEngine.execute_trade_pipeline`
        which places the entry order and TP limit orders.  On success the
        signal status is updated to ``EXECUTED``; on failure it is set to
        ``REJECTED``.

        Args:
            prepared:
                A ``PreparedTrade`` returned by :meth:`prepare_trade`.

        Returns:
            A 3-tuple ``(success, message, execution_response)``.
        """
        try:
            self.execution_engine.trade_repo = self.trade_repo
            exec_res = await self.execution_engine.execute_trade_pipeline(
                trade_id=prepared.trade_id,
                symbol=prepared.parsed.symbol,
                side=prepared.parsed.side,
                risk_res=prepared.risk_res,
                tp_prices=prepared.parsed.tp_prices,
                leverage=settings.DEFAULT_LEVERAGE,
                symbol_info=prepared.symbol_info
            )

            if exec_res.success:
                await self.signal_repo.update_signal_status(prepared.signal_id, 'EXECUTED')
                return True, "Trade Executed Successfully", exec_res
            else:
                await self.signal_repo.update_signal_status(prepared.signal_id, 'REJECTED')
                return False, f"Execution Failed: {exec_res.error_message}", exec_res

        except Exception:
            logger.error(f"Failed to execute trade {prepared.trade_id}: {traceback.format_exc()}")
            await self.signal_repo.update_signal_status(prepared.signal_id, 'REJECTED')
            return False, "Internal error during trade execution.", ExecutionResponse(success=False, trade_id=prepared.trade_id, error_message="Internal error")
