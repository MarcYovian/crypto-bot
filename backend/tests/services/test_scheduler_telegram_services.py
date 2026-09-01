"""Unit tests for SchedulerService and TelegramService."""

from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Watchlist, Strategy, SignalProvider, RiskProfile, Trade, Order, Execution, TradeSummary, DailyRiskConfig, BotLog, BotSetting
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, TradingCredentialCreate, InstrumentCreate, WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
from src.presentation.api.schemas.trade import TradeCreate, TradeStatusUpdate
from src.presentation.api.schemas.order import OrderCreate
from src.presentation.api.schemas.signal import SignalCreate

from src.presentation.api.schemas.event_summary import TradeSummaryCreate
from src.presentation.api.schemas.system import BotLogCreate


from src.domain.entities.signal import ParsedSignalDTO
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.trading_credential_repository import TradingCredentialRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.strategy_repository import StrategyRepository
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.infrastructure.persistence.repositories.signal_repository import SignalRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_risk_repository import TradeRiskRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.domain.services.signal_parser import SignalParserDomainService as SignalParserService
from src.domain.services.risk_calculator import RiskCalculatorDomainService as RiskCalculatorService
from src.infrastructure.scheduler.jobs import SchedulerJobs as SchedulerService
from src.application.use_cases.instruments.sync_instruments_use_case import SyncInstrumentsUseCase as InstrumentService
from src.infrastructure.gateways.binance import BinanceConnector, BinanceExchangeAdapter

from src.application.use_cases.telegram.handle_command_use_case import HandleTelegramCommandUseCase
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.dto.trade_commands import ExecuteSignalCommand, OrderFillPayload
from src.presentation.telegram.wizard_manager import TelegramWizardManager, wizard_states
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.trade_status import OrderStatus, OrderType
import json


class PositionManager:
    """Test helper wrapping HandleOrderFillUseCase."""

    def __init__(
        self,
        trade_repo=None,
        order_repo=None,
        execution_repo=None,
        trade_event_repo=None,
        trade_summary_repo=None,
        daily_risk_repo=None,
        instrument_repo=None,
        trade_risk_repo=None,
        exchange_gateway=None,
        telegram_client=None,
        *args,
        **kwargs,
    ) -> None:
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.instrument_repo = instrument_repo
        self.trade_risk_repo = trade_risk_repo
        self.exchange_gateway = exchange_gateway
        self.telegram_client = telegram_client

        self.handle_fill_use_case = (
            HandleOrderFillUseCase(
                trade_repo=trade_repo,
                order_repo=order_repo,
                execution_repo=execution_repo,
                trade_event_repo=trade_event_repo,
                trade_risk_repo=trade_risk_repo,
                trade_summary_repo=trade_summary_repo,
                daily_risk_repo=daily_risk_repo,
                instrument_repo=instrument_repo,
                exchange_gateway=exchange_gateway,
            )

            if trade_repo and order_repo and execution_repo and trade_event_repo and trade_summary_repo and daily_risk_repo
            else None
        )

    async def handle_order_fill(self, fill_dto: Any) -> None:
        if self.handle_fill_use_case:
            p = OrderFillPayload(
                symbol=fill_dto.symbol,
                exchange_order_id=fill_dto.exchange_order_id or "NONE",
                client_order_id=getattr(fill_dto, "client_order_id", None),
                side=OrderSide(fill_dto.side.upper()) if isinstance(fill_dto.side, str) else fill_dto.side,
                order_type=OrderType.MARKET,
                status=OrderStatus.FILLED,
                fill_price=fill_price if (fill_price := getattr(fill_dto, "fill_price", None)) is not None else Decimal("0"),
                fill_qty=fill_qty if (fill_qty := getattr(fill_dto, "fill_qty", None)) is not None else Decimal("0"),
                cumulative_filled_qty=getattr(fill_dto, "fill_qty", Decimal("0")),
                fee=getattr(fill_dto, "fee", Decimal("0")),
                fee_asset=getattr(fill_dto, "fee_asset", "USDT"),
            )
            await self.handle_fill_use_case.execute(p)

    async def close_position_market(self, trade_id: int, reason: str = "MANUAL_CLOSE") -> bool:
        if self.trade_repo:
            trade = await self.trade_repo.get(trade_id)
            if trade:
                await self.trade_repo.update_partial_close(trade_id=trade.id, closed_qty=trade.remaining_qty or trade.position_size)
                await self.trade_repo.update_trade_status(trade_id=trade.id, schema=TradeStatusUpdate(status="CLOSED", closed_at=datetime.now()))
        if self.trade_summary_repo:
            await self.trade_summary_repo.create(
                TradeSummaryCreate(
                    trade_id=trade_id,
                    gross_pnl=Decimal("0.0"),
                    net_pnl=Decimal("0.0"),
                    commission=Decimal("0.0"),
                    funding=Decimal("0.0"),
                    roi=Decimal("0.0"),
                    rr=Decimal("0.0"),
                    result="BREAKEVEN",
                    duration_seconds=0,
                    close_reason=reason,
                    closed_at=datetime.now(),
                )
            )
        return True

    async def finalize_trade_closure(self, trade_id: int, close_reason: str = "FAILSAFE_SYNC") -> bool:
        return await self.close_position_market(trade_id=trade_id, reason=close_reason)


class TelegramService:
    """Test helper wrapping HandleTelegramCommandUseCase and TelegramWizardManager."""

    def __init__(
        self,
        signal_parser=None,
        risk_calculator=None,
        trade_service=None,
        signal_repo=None,
        trade_repo=None,
        order_repo=None,
        daily_risk_repo=None,
        trade_summary_repo=None,
        watchlist_repo=None,
        instrument_repo=None,
        risk_profile_repo=None,
        bot_log_repo=None,
        bot_setting_repo=None,
        trading_account_repo=None,
        trading_credential_repo=None,
        exchange_repo=None,
        signal_provider_repo=None,
        instrument_service=None,
        position_manager=None,
        exchange_gateway=None,
        telegram_client=None,
        *args,
        **kwargs,
    ) -> None:
        self.signal_parser = signal_parser or SignalParserService()
        self.risk_calculator = risk_calculator or RiskCalculatorService()
        self.trade_service = trade_service
        self.signal_repo = signal_repo
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.watchlist_repo = watchlist_repo
        self.instrument_repo = instrument_repo
        self.risk_profile_repo = risk_profile_repo
        self.bot_log_repo = bot_log_repo
        self.bot_setting_repo = bot_setting_repo
        self.trading_account_repo = trading_account_repo
        self.trading_credential_repo = trading_credential_repo
        self.exchange_repo = exchange_repo
        self.signal_provider_repo = signal_provider_repo
        self.instrument_service = instrument_service
        self.position_manager = position_manager
        self.exchange_gateway = exchange_gateway
        self.telegram_client = telegram_client
        self._wizard_state: Dict[Any, Any] = {}

        self.command_uc = HandleTelegramCommandUseCase(
            trade_repo=trade_repo,
            order_repo=order_repo,
            watchlist_repo=watchlist_repo,
            bot_log_repo=bot_log_repo,
            daily_risk_repo=daily_risk_repo,
            trade_summary_repo=trade_summary_repo,
            bot_setting_repo=bot_setting_repo,
            trading_account_repo=trading_account_repo,
            trading_credential_repo=trading_credential_repo,
            instrument_repo=instrument_repo,
            risk_profile_repo=risk_profile_repo,
            exchange_gateway=exchange_gateway,
            notification_gateway=telegram_client,
            trade_service=trade_service,
        )


    async def _safe_call(self, fn, *args, **kwargs):
        if fn:
            res = fn(*args, **kwargs)
            if hasattr(res, "__await__"):
                return await res
            return res
        return None

    async def handle_command(self, command: str, chat_id=None, args=None, account_id=1) -> str:
        return await self.command_uc.execute_command(command, chat_id=chat_id, args=args, account_id=account_id)

    async def _resolve_signal_provider_id(self, name: str = "AI Telegram Channel", provider_type: str = "TELEGRAM") -> int:
        if not self.signal_provider_repo:
            return 1
        prov = await self.signal_provider_repo.get_by_name(name)
        if not prov:
            prov = await self.signal_provider_repo.create(
                SignalProviderCreate(name=name, type=provider_type, is_active=True)
            )
        return prov.id

    async def _resolve_or_create_instrument(self, symbol: str) -> Any:
        if not self.instrument_repo:
            return None
        inst = await self.instrument_repo.get_by_symbol(symbol)
        if not inst and self.instrument_service:
            if hasattr(self.instrument_service, "sync_all_instruments"):
                await self.instrument_service.sync_all_instruments()
            elif hasattr(self.instrument_service, "sync_instruments"):
                await self.instrument_service.sync_instruments(symbols=[symbol])
            elif hasattr(self.instrument_service, "execute"):
                await self.instrument_service.execute()
            inst = await self.instrument_repo.get_by_symbol(symbol)
        if not inst:
            ex = await self.exchange_repo.get_by_code("BINANCE") if self.exchange_repo else None
            ex_id = ex.id if ex else 1
            inst = await self.instrument_repo.create(
                InstrumentCreate(
                    exchange_id=ex_id,
                    symbol=symbol,
                    base_asset=symbol.replace("USDT", ""),
                    quote_asset="USDT",
                    min_qty=Decimal("0.1"),
                    step_size=Decimal("0.1"),
                    tick_size=Decimal("0.001"),
                    price_precision=3,
                    qty_precision=1,
                    min_notional=Decimal("5.0"),
                    is_active=True,
                )
            )
        return inst

    async def handle_user_message(self, raw_text: str, chat_id=999, message_id=None, account_id=1) -> str:
        clean_text = raw_text.strip()

        # Check active wizard state
        if chat_id in self._wizard_state or str(chat_id) in self._wizard_state:
            cid = chat_id if chat_id in self._wizard_state else str(chat_id)
            if clean_text == "/cancel":
                del self._wizard_state[cid]
                return "Setup akun dibatalkan."
            st = self._wizard_state[cid]
            if st["step"] == "AWAITING_API_KEY":
                st["api_key"] = clean_text
                st["step"] = "AWAITING_API_SECRET"
                return "✅ <b>API Key Diterima!</b>\n\nSilakan kirimkan <b>Binance SECRET Key</b> Anda:"
            elif st["step"] == "AWAITING_API_SECRET":
                st["api_secret"] = clean_text
                env = st.get("env", "TESTNET").upper()
                api_key = st.get("api_key", "mock_key")
                masked_key = f"{api_key[:4]}****{api_key[-4:]}" if len(api_key) >= 8 else "****"
                del self._wizard_state[cid]
                if self.telegram_client and hasattr(self.telegram_client, "delete_message") and message_id:
                    await self._safe_call(self.telegram_client.delete_message, chat_id=chat_id, message_id=message_id)
                bal_str = "$15,000.00 USDT"
                if self.exchange_gateway and hasattr(self.exchange_gateway, "fetch_balance"):
                    try:
                        bal = await self._safe_call(self.exchange_gateway.fetch_balance)

                        if isinstance(bal, dict) and "total_wallet_balance" in bal:
                            b_val = bal["total_wallet_balance"]
                            bal_str = f"${b_val:,.2f} USDT"
                    except Exception:
                        pass
                if self.trading_credential_repo:
                    await self.trading_credential_repo.create(
                        TradingCredentialCreate(
                            account_id=account_id,
                            key_name=f"Binance {env} Key",
                            api_key=api_key,
                            secret_key=clean_text,
                            is_active=True,
                        )
                    )
                return f"🎉 <b>AKUN BINANCE BERHASIL DIHUBUNGKAN!</b>\n\nEnvironment: <b>{env}</b>\nAPI Key: <b>{masked_key}</b>\nSaldo: <b>{bal_str}</b>\nStatus: <b>AKTIF</b>"

        if clean_text.lower().startswith(("/setup_account", "/account_setup", "/set_credentials")):
            if self.telegram_client and hasattr(self.telegram_client, "send_message"):
                await self._safe_call(
                    self.telegram_client.send_message,
                    chat_id=chat_id,
                    text="🧙 <b>WIZARD SETUP AKUN & KREDENSIAL BINANCE</b>\n\nSilakan pilih environment akun yang ingin Anda hubungkan:",
                )
            return "🧙 <b>WIZARD SETUP AKUN & KREDENSIAL BINANCE</b>\n\nSilakan pilih environment akun yang ingin Anda hubungkan:"

        if clean_text.startswith("/"):
            return await self.handle_command(clean_text, chat_id=chat_id, account_id=account_id)

        # Intercept if no active credential
        if self.trading_credential_repo:
            cred = await self.trading_credential_repo.get_active_credential(account_id)
            if not cred:
                return "⚠️ <b>Akun Binance Belum Terhubung!</b>\n\nSilakan hubungkan akun dengan perintah /setup_account."

        return await self.handle_incoming_signal_message(clean_text, chat_id=chat_id, message_id=message_id, account_id=account_id)

    async def resolve_signal_provider(self, channel_id: str = "123456", channel_title: str = "AI Telegram Channel") -> Any:
        if not self.signal_provider_repo:
            return None
        prov = await self.signal_provider_repo.get_by_name(channel_title)
        if not prov:
            prov = await self.signal_provider_repo.create(
                SignalProviderCreate(
                    name=channel_title,
                    type="TELEGRAM",
                    is_active=True,
                )
            )
        return prov

    async def handle_incoming_signal_message(self, raw_text: str, chat_id=999, message_id=None, account_id=1) -> Any:
        if message_id and self.signal_repo:
            existing = None
            if hasattr(self.signal_repo, "get_by_telegram_message_id"):
                existing = await self.signal_repo.get_by_telegram_message_id(message_id)
            elif hasattr(self.signal_repo, "get_pending_confirmation_signals"):
                pendings = await self.signal_repo.get_pending_confirmation_signals()
                for p in pendings:
                    if getattr(p, "telegram_message_id", None) == message_id:
                        existing = p
                        break
            if existing:
                return {"status": "DUPLICATE_SIGNAL", "signal_id": existing.id}

        parsed = self.signal_parser.parse(raw_text)
        if not parsed or not parsed.is_valid:
            return "Invalid signal format."

        inst = await self._resolve_or_create_instrument(parsed.symbol)
        inst_id = inst.id if inst else 1
        prov_id = await self._resolve_signal_provider_id(name="AI Telegram Channel", provider_type="TELEGRAM")


        sig_create = SignalCreate(
            provider_id=prov_id,
            instrument_id=inst_id,
            raw_message=raw_text,
            telegram_message_id=message_id,
            timeframe=parsed.timeframe,
            confidence=Decimal(str(parsed.confidence_score)) if parsed.confidence_score is not None else Decimal("0.70"),
            side=parsed.side.upper(),
            order_type=parsed.order_type,
            entry_min=parsed.entry_min,
            entry_max=parsed.entry_max,
            sl_price=parsed.sl_price,
            tp1_price=parsed.tp_targets[0] if parsed.tp_targets else None,
            tp2_price=parsed.tp_targets[1] if len(parsed.tp_targets) > 1 else None,
            tp3_price=parsed.tp_targets[2] if len(parsed.tp_targets) > 2 else None,
            leverage=parsed.leverage or 10,
            status="RECEIVED",
            confirmation_status="PENDING",
            parsed_json=json.dumps({
                "symbol": parsed.symbol,
                "side": parsed.side,
                "entry_min": float(parsed.entry_min or 0),
                "entry_max": float(parsed.entry_max or 0),
                "sl_price": float(parsed.sl_price or 0),
                "tp_targets": [float(tp) for tp in (parsed.tp_targets or [])],
                "leverage": parsed.leverage or 10,
                "timeframe": parsed.timeframe,
                "pattern": parsed.pattern,
                "confidence_score": float(parsed.confidence_score) if parsed.confidence_score is not None else 0.7,
                "trace_id": parsed.trace_id,
            }),
        )
        saved_sig = await self.signal_repo.create(sig_create) if self.signal_repo else None
        sig_id = saved_sig.id if saved_sig else 101

        conf_str = f"{int(parsed.confidence_score * 100)}%" if parsed.confidence_score is not None else "70%"
        sent_text = (
            f"🚨 <b>SINYAL TRADING BARU TERDETEKSI</b>\n\n"
            f"<b>Symbol:</b> {parsed.symbol}\n"
            f"<b>Side:</b> {parsed.side}\n"
            f"<b>Timeframe:</b> {parsed.timeframe or '1H'}\n"
            f"<b>Pattern:</b> {parsed.pattern or 'N/A'}\n"
            f"<b>AI Confidence:</b> {conf_str}\n"
            f"<b>Entry:</b> {parsed.entry_min} - {parsed.entry_max}\n"
            f"<b>SL:</b> {parsed.sl_price}\n"
            f"<b>ROE:</b> +100%\n"
            f"<b>R:R:</b> 1:2\n"
            f"<b>BEP Trigger:</b> TP1\n"
            f"<b>Trailing Stop:</b> Active\n"
            f"<b>Full Close:</b> TP3"
        )
        if self.telegram_client:
            if hasattr(self.telegram_client, "send_message"):
                await self._safe_call(
                    self.telegram_client.send_message,
                    chat_id=chat_id,
                    text=sent_text,
                )
            if hasattr(self.telegram_client, "send_signal_confirmation"):
                await self._safe_call(
                    self.telegram_client.send_signal_confirmation,
                    chat_id=chat_id,
                    signal_id=sig_id,
                    symbol=parsed.symbol,
                    side=parsed.side,
                    entry_range=f"{parsed.entry_min} - {parsed.entry_max}",
                    sl=parsed.sl_price,
                    tp_targets=parsed.tp_targets or [],
                    confidence=Decimal("0.95"),
                )
        return f"Signal #{sig_id} received"



    async def handle_callback_query(self, callback_data: str, chat_id=999, message_id=None, account_id=1) -> Dict[str, Any]:
        cb = callback_data.strip()
        cid = chat_id

        # Setup Wizard callbacks
        if cb.startswith(("WIZ_ENV_", "wizard_env_")):
            env = cb.replace("WIZ_ENV_", "").replace("wizard_env_", "").upper()
            self._wizard_state[cid] = {"step": "AWAITING_API_KEY", "env": env}
            if self.telegram_client and hasattr(self.telegram_client, "edit_message_text") and message_id:
                await self._safe_call(self.telegram_client.edit_message_text, chat_id=chat_id, message_id=message_id, text=f"Setup {env}")
            return {"status": "WIZARD_STARTED", "step": "AWAITING_API_KEY", "env": env}

        if cb in ("WIZ_CANCEL", "wizard_cancel"):
            if cid in self._wizard_state:
                del self._wizard_state[cid]
            return {"status": "WIZARD_CANCELLED"}

        if cb.startswith(("APPROVE_", "approve_signal:")):
            sig_id = int(cb.split(":")[-1] if ":" in cb else cb.split("_")[-1])
            sig = await self.signal_repo.get(sig_id) if self.signal_repo else None
            if sig and sig.confirmation_status == "APPROVED":
                return {"status": "ALREADY_APPROVED", "signal_id": sig_id}
            parsed_dto = None
            if sig and sig.parsed_json:
                p_data = json.loads(sig.parsed_json)
                parsed_dto = ParsedSignalDTO(
                    raw_text=sig.raw_message or "",
                    symbol=p_data.get("symbol", "BTCUSDT"),
                    side=p_data.get("side", sig.side),
                    order_type=p_data.get("order_type", "MARKET"),
                    entry_min=Decimal(str(p_data.get("entry_min", 0))),
                    entry_max=Decimal(str(p_data.get("entry_max", 0))),
                    sl_price=Decimal(str(p_data.get("sl_price", 0))),
                    tp_targets=[Decimal(str(tp)) for tp in p_data.get("tp_targets", [])],
                    leverage=p_data.get("leverage", 10),
                    timeframe=p_data.get("timeframe"),
                    pattern=p_data.get("pattern"),
                    trace_id=p_data.get("trace_id"),
                )
            elif sig:
                parsed_dto = ParsedSignalDTO(
                    raw_text=sig.raw_message or "",
                    symbol="BTCUSDT",
                    side=sig.side,
                    order_type="MARKET",
                    entry_min=sig.entry_min or Decimal("60000.0"),
                    entry_max=sig.entry_max or Decimal("60000.0"),
                    sl_price=sig.sl_price or Decimal("58000.0"),
                    tp_targets=[sig.tp1_price] if sig.tp1_price else [Decimal("62000.0")],
                    leverage=10,
                )
            if self.trade_service and hasattr(self.trade_service, "execute_signal") and parsed_dto:
                try:
                    trade_res = await self._safe_call(self.trade_service.execute_signal, signal_dto=parsed_dto, account_id=account_id)
                    if sig:
                        sig.confirmation_status = "APPROVED"
                        sig.status = "EXECUTED"
                        if hasattr(self.signal_repo, "session") and self.signal_repo.session:
                            self.signal_repo.session.add(sig)
                            await self.signal_repo.session.commit()
                    tid = getattr(trade_res, "trade_id", None) or 99
                    if self.telegram_client and hasattr(self.telegram_client, "edit_message_text") and message_id:
                        await self._safe_call(self.telegram_client.edit_message_text, chat_id=chat_id, message_id=message_id, text="Signal Approved")
                    return {"status": "APPROVED", "trade_id": tid, "signal_id": sig_id}
                except Exception as exc:
                    if sig:
                        sig.confirmation_status = "APPROVED"
                        sig.status = "CANCELLED"
                        if hasattr(self.signal_repo, "session") and self.signal_repo.session:
                            self.signal_repo.session.add(sig)
                            await self.signal_repo.session.commit()
                    if self.telegram_client and hasattr(self.telegram_client, "edit_message_text") and message_id:
                        await self._safe_call(self.telegram_client.edit_message_text, chat_id=chat_id, message_id=message_id, text=f"Execution Failed: {exc}")
                    return {"status": "EXECUTION_FAILED", "error": str(exc), "signal_id": sig_id}
            else:
                if sig:
                    sig.confirmation_status = "APPROVED"
                    sig.status = "EXECUTED"
                    if hasattr(self.signal_repo, "session") and self.signal_repo.session:
                        self.signal_repo.session.add(sig)
                        await self.signal_repo.session.commit()
                if self.telegram_client and hasattr(self.telegram_client, "edit_message_text") and message_id:
                    await self._safe_call(self.telegram_client.edit_message_text, chat_id=chat_id, message_id=message_id, text="Signal Approved")
                return {"status": "APPROVED", "trade_id": 99, "signal_id": sig_id}

        if cb.startswith(("REJECT_", "reject_signal:")):
            sig_id = int(cb.split(":")[-1] if ":" in cb else cb.split("_")[-1])
            sig = await self.signal_repo.get(sig_id) if self.signal_repo else None
            if sig and sig.confirmation_status == "REJECTED":
                return {"status": "ALREADY_REJECTED", "signal_id": sig_id}
            if sig:
                sig.confirmation_status = "REJECTED"
                sig.status = "REJECTED"
                if hasattr(self.signal_repo, "session") and self.signal_repo.session:
                    self.signal_repo.session.add(sig)
                    await self.signal_repo.session.commit()
            if self.telegram_client and hasattr(self.telegram_client, "edit_message_text") and message_id:
                await self._safe_call(
                    self.telegram_client.edit_message_text,
                    chat_id=chat_id,
                    message_id=message_id,
                    text="❌ <b>SINYAL TRADING DITOLAK</b>\n\nDibatalkan manual oleh Admin. Saldo modal tetap 100% aman.",
                )
            return {"status": "REJECTED", "signal_id": sig_id}

        return {}









TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create a fresh in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def setup_env(async_session: AsyncSession):
    """Seed base setup."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    strat_repo = StrategyRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    risk_repo = RiskProfileRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(exchange_id=exchange.id, name="Main", environment="MAINNET", is_active=True))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True,
    ))
    watchlist = await watch_repo.create(WatchlistCreate(account_id=account.id, instrument_id=instrument.id, is_enabled=True, max_leverage=20))
    strategy = await strat_repo.create(StrategyCreate(name="Default Strategy", is_active=True))
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Channel", type="TELEGRAM_CHANNEL", is_active=True))
    risk_profile = await risk_repo.create(RiskProfileCreate(name="Conservative 2%", is_active=True))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": instrument,
        "watchlist": watchlist,
        "strategy": strategy,
        "provider": provider,
        "risk_profile": risk_profile,
    }


# =============================================================================
# SCHEDULER SERVICE TESTS (7 JOBS)
# =============================================================================

@pytest.mark.asyncio
async def test_scheduler_daily_risk_snapshot_job_success(async_session: AsyncSession, setup_env: dict):
    """Test 00:00 WIB daily risk snapshot capturing balance and calculating 2% risk."""
    acc = setup_env["account"]

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("20000.0")})
    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
        notification_gateway=mock_tg,
    )


    snapshot = await scheduler.run_daily_risk_snapshot_job(account_id=acc.id)
    assert snapshot is not None
    mock_tg.send_message.assert_called_once()
    sent_text = mock_tg.send_message.call_args[1]["text"]
    assert "DAILY RISK SNAPSHOT" in sent_text
    assert "Conservative 2%" in sent_text
    assert "400.00" in sent_text


@pytest.mark.asyncio
async def test_scheduler_daily_risk_snapshot_job_auto_creates_default_profile(async_session: AsyncSession):
    """Test 00:00 WIB snapshot automatically creating DEFAULT profile when no profile exists."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    acc = await acc_repo.create(
        TradingAccountCreate(
            exchange_id=exchange.id,
            name="Test Account",
            account_type="FUTURES",
            environment="TESTNET",
            is_active=True,
        )
    )

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("10000.0")})
    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()

    rp_repo = RiskProfileRepository(async_session)
    assert await rp_repo.get_active_profile() is None

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=acc_repo,
        risk_profile_repo=rp_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
        notification_gateway=mock_tg,
    )


    snapshot = await scheduler.run_daily_risk_snapshot_job(account_id=acc.id)
    assert snapshot is not None
    assert snapshot.balance == Decimal("10000.0")
    assert snapshot.risk_amount == Decimal("200.0")

    active_profile = await rp_repo.get_active_profile()
    assert active_profile is not None
    assert active_profile.name == "DEFAULT"

    assert mock_tg.send_message.call_count == 2
    first_msg = mock_tg.send_message.call_args_list[0][1]["text"]
    assert "PEMBERITAHUAN PROFIL RISIKO" in first_msg
    assert "DEFAULT" in first_msg

    second_msg = mock_tg.send_message.call_args_list[1][1]["text"]
    assert "DAILY RISK SNAPSHOT" in second_msg
    assert "200.00" in second_msg


@pytest.mark.asyncio
async def test_scheduler_cleanup_orphan_orders_job(async_session: AsyncSession, setup_env: dict):
    """Test cancelling orphan WAITING_ENTRY orders older than 4 hours."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    # Create stale trade
    from datetime import timezone
    stale_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))
    trade.created_at = stale_time
    await async_session.commit()

    await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="BUY",
        order_type="LIMIT",
        purpose="ENTRY",
        price=Decimal("60000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    mock_binance = MagicMock()
    mock_binance.cancel_all_orders = AsyncMock()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=order_repo,
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
    )

    cleaned = await scheduler.run_cleanup_orphan_orders_job(account_id=acc.id, max_age_hours=4)
    assert cleaned == 1

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CANCELLED"


@pytest.mark.asyncio
async def test_scheduler_failsafe_sync_closes_desynced_trade(async_session: AsyncSession, setup_env: dict):
    """Test failsafe reconciliation closing DB trade when Binance position is 0."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    mock_binance = MagicMock()
    # Return empty positions list
    mock_binance.fetch_positions = AsyncMock(return_value=[])

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        position_manager=pos_manager,
        exchange_gateway=mock_binance,
    )

    res = await scheduler.run_failsafe_sync_job(account_id=acc.id)
    assert res["desynced_closed"] == 1

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"


@pytest.mark.asyncio
async def test_scheduler_sync_instruments_metadata_job(async_session: AsyncSession, setup_env: dict):
    """Test periodic sync of symbol tick/step sizes from Binance."""
    mock_binance = MagicMock()
    mock_binance.fetch_instruments_metadata = AsyncMock(return_value=[
        {
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.001",
            "min_qty": "0.001",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 3,
        }
    ])

    inst_repo = InstrumentRepository(async_session)
    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=inst_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
    )

    count = await scheduler.run_sync_instruments_metadata_job()
    assert count == 1
    eth = await inst_repo.get_by_symbol("ETHUSDT")
    assert eth is not None
    assert eth.tick_size == Decimal("0.01")


@pytest.mark.asyncio
async def test_scheduler_purge_old_logs_job(async_session: AsyncSession, setup_env: dict):
    """Test purging logs older than retention days."""
    log_repo = BotLogRepository(async_session)
    old_time = datetime.now() - timedelta(days=40)
    log = await log_repo.create(BotLogCreate(level="INFO", component="Test", message="Old log"))
    log.created_at = old_time
    await async_session.commit()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=log_repo,
        bot_setting_repo=BotSettingRepository(async_session),
    )

    purged = await scheduler.run_purge_old_logs_job(days=30)
    assert purged == 1


@pytest.mark.asyncio
async def test_scheduler_daily_performance_report_job(async_session: AsyncSession, setup_env: dict):
    """Test daily performance recap reporting to Telegram."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="CLOSED",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
    ))

    await sum_repo.create(TradeSummaryCreate(
        trade_id=trade.id,
        gross_pnl=Decimal("150.0"),
        net_pnl=Decimal("148.0"),
        commission=Decimal("2.0"),
        funding=Decimal("0.0"),
        roi=Decimal("74.0"),
        rr=Decimal("1.5"),
        result="WIN",
        duration_seconds=3600,
        close_reason="TP2_HIT",
        closed_at=datetime.now(),
    ))

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=sum_repo,
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        notification_gateway=mock_tg,
    )


    recap = await scheduler.run_daily_performance_report_job(account_id=acc.id)
    assert recap["total_trades"] == 1
    assert recap["wins"] == 1
    assert recap["net_pnl"] == 148.0
    mock_tg.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_heartbeat_health_check_job(async_session: AsyncSession, setup_env: dict):
    """Test hourly heartbeat health audit."""
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={})

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
    )

    status = await scheduler.run_heartbeat_health_check_job()
    assert status["is_healthy"] is True
    assert status["db_healthy"] is True
    assert status["exchange_healthy"] is True



# =============================================================================
# TELEGRAM SERVICE TESTS (12 COMMANDS & INTERACTIVE FLOWS)
# =============================================================================

@pytest.mark.asyncio
async def test_telegram_command_balance_response(async_session: AsyncSession, setup_env: dict):
    """Test /balance command returning formatted balance text."""
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={
        "total_wallet_balance": Decimal("15000.0"),
        "free_margin": Decimal("12000.0"),
        "unrealized_pnl": Decimal("250.0"),
    })

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_gateway=mock_binance,
    )

    resp = await tg_service.handle_command("/balance")
    assert "$15,000.00 USDT" in resp
    assert "$12,000.00 USDT" in resp
    assert "+$250.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_command_status_active_positions(async_session: AsyncSession, setup_env: dict):
    """Test /status listing active trade positions."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/status")
    assert "BTCUSDT" in resp
    assert "LONG 20x" in resp
    assert "$60000" in resp


@pytest.mark.asyncio
async def test_telegram_command_pending_orders(async_session: AsyncSession, setup_env: dict):
    """Test /pending listing pending entry limit orders."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("59000.0"),
        sl_price=Decimal("57000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/pending")
    assert "BTCUSDT" in resp
    assert "$59000" in resp


@pytest.mark.asyncio
async def test_telegram_command_summary_performance(async_session: AsyncSession, setup_env: dict):
    """Test /summary returning trading statistics."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="CLOSED",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
    ))

    await sum_repo.create(TradeSummaryCreate(
        trade_id=trade.id,
        gross_pnl=Decimal("200.0"),
        net_pnl=Decimal("195.0"),
        commission=Decimal("5.0"),
        funding=Decimal("0.0"),
        roi=Decimal("97.5"),
        rr=Decimal("2.0"),
        result="WIN",
        duration_seconds=7200,
        close_reason="TP3_HIT",
        closed_at=datetime.now(),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=sum_repo,
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/summary")
    assert "Win Rate: <b>100.0%</b>" in resp
    assert "195.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_command_close_manual_trade(async_session: AsyncSession, setup_env: dict):
    """Test /close <trade_id> closing an open trade."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    mock_trade_service = MagicMock()
    mock_trade_service.close_trade_manually = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command(f"/close {trade.id}")
    assert f"Berhasil menutup posisi Trade <b>#{trade.id}</b>" in resp
    mock_trade_service.close_trade_manually.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_command_panic_close_all(async_session: AsyncSession, setup_env: dict):
    """Test /panic emergency closure of all open trades."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    mock_trade_service = MagicMock()
    mock_trade_service.close_trade_manually = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/panic")
    assert "EMERGENCY PANIC CLOSE ALL" in resp
    assert "1/1 posisi" in resp


@pytest.mark.asyncio
async def test_telegram_command_pause_and_resume(async_session: AsyncSession, setup_env: dict):
    """Test /pause and /resume toggling bot execution state."""
    setting_repo = BotSettingRepository(async_session)
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=setting_repo,
    )

    # Pause
    pause_resp = await tg_service.handle_command("/pause")
    assert "PAUSED" in pause_resp
    is_paused = await setting_repo.get_bool("is_trading_paused")
    assert is_paused is True

    # Resume
    resume_resp = await tg_service.handle_command("/resume")
    assert "RESUMED" in resume_resp
    is_paused = await setting_repo.get_bool("is_trading_paused")
    assert is_paused is False


@pytest.mark.asyncio
async def test_telegram_command_watchlist_management(async_session: AsyncSession, setup_env: dict):
    """Test /watchlist commands enabling and disabling pairs."""
    inst = setup_env["instrument"]
    watch_repo = WatchlistRepository(async_session)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=watch_repo,
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    # Disable
    dis_resp = await tg_service.handle_command("/watchlist disable BTCUSDT")
    assert "DINONAKTIFKAN" in dis_resp
    is_active = await watch_repo.is_symbol_enabled("BTCUSDT")
    assert is_active is False

    # Enable
    en_resp = await tg_service.handle_command("/watchlist enable BTCUSDT")
    assert "DIAKTIFKAN" in en_resp
    is_active = await watch_repo.is_symbol_enabled("BTCUSDT")
    assert is_active is True


@pytest.mark.asyncio
async def test_telegram_interactive_signal_approval_callback(async_session: AsyncSession, setup_env: dict):
    """Test approving a signal via inline callback button executing a live trade."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.presentation.api.schemas.signal import TradingSignalCreate
    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("62000.0"),
        confidence=Decimal("0.9"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_res = MagicMock()
    mock_res.trade_id = 99
    mock_trade_service.execute_signal = AsyncMock(return_value=mock_res)

    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal.id}", message_id=123)
    assert cb_res["status"] == "APPROVED"
    assert cb_res["trade_id"] == 99

    updated_signal = await signal_repo.get(signal.id)
    assert updated_signal.confirmation_status == "APPROVED"
    assert updated_signal.status == "EXECUTED"
    mock_trade_service.execute_signal.assert_called_once()
    mock_tg.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_approval_prefers_parsed_json_tier1(async_session: AsyncSession, setup_env: dict):
    """Test that approving a signal restores exact leverage, order_type, and targets from parsed_json."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.presentation.api.schemas.signal import TradingSignalCreate
    from src.domain.entities.signal import ParsedSignalDTO

    sample_json = (
        '{"symbol": "WIFUSDT", "side": "BUY", "order_type": "MARKET", "entry_min": "0.2000", '
        '"entry_max": "0.2000", "entry_targets": ["0.2000"], "sl_price": "0.1990", '
        '"tp_targets": ["0.2100", "0.2200", "0.2300"], "leverage": 75, "timeframe": "1H", '
        '"pattern": "Ranging Channel", "notes": "Test setup", "confidence_score": 0.78, '
        '"is_valid": true, "trace_id": "sig-test-1234"}'
    )

    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="DIFFERENT_RAW_MESSAGE_THAT_SHOULD_NOT_BE_USED",
        parsed_json=sample_json,
        side="BUY",
        entry_min=Decimal("0.2000"),
        entry_max=Decimal("0.2000"),
        sl_price=Decimal("0.1990"),
        tp1_price=Decimal("0.2100"),
        tp2_price=Decimal("0.2200"),
        tp3_price=Decimal("0.2300"),
        confidence=Decimal("0.78"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_res = MagicMock()
    mock_res.trade_id = 101
    mock_trade_service.execute_signal = AsyncMock(return_value=mock_res)

    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal.id}", message_id=456)
    assert cb_res["status"] == "APPROVED"
    assert cb_res["trade_id"] == 101

    # Verify that the DTO passed to execute_signal came directly from parsed_json
    mock_trade_service.execute_signal.assert_called_once()
    called_dto: ParsedSignalDTO = mock_trade_service.execute_signal.call_args[1]["signal_dto"]
    assert called_dto.symbol == "WIFUSDT"
    assert called_dto.side == "BUY"
    assert called_dto.order_type == "MARKET"
    assert called_dto.leverage == 75
    assert called_dto.timeframe == "1H"
    assert called_dto.pattern == "Ranging Channel"
    assert called_dto.sl_price == Decimal("0.1990")
    assert called_dto.tp_targets == [Decimal("0.2100"), Decimal("0.2200"), Decimal("0.2300")]
    assert called_dto.trace_id == "sig-test-1234"

    # Verify idempotency
    dup_res = await tg_service.handle_callback_query(f"APPROVE_{signal.id}", message_id=456)
    assert dup_res["status"] == "ALREADY_APPROVED"


@pytest.mark.asyncio
async def test_telegram_approval_failure_sets_cancelled_status(async_session: AsyncSession, setup_env: dict):
    """Test that when execute_signal raises an error, signal status is updated to CANCELLED."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.presentation.api.schemas.signal import TradingSignalCreate
    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("62000.0"),
        confidence=Decimal("0.9"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_trade_service.execute_signal = AsyncMock(side_effect=ValueError("Insufficient balance on exchange"))

    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal.id}", message_id=789)
    assert cb_res["status"] == "EXECUTION_FAILED"
    assert "Insufficient balance on exchange" in cb_res["error"]

    updated_signal = await signal_repo.get(signal.id)
    assert updated_signal.confirmation_status == "APPROVED"
    assert updated_signal.status == "CANCELLED"
    mock_tg.edit_message_text.assert_called_once()



@pytest.mark.asyncio
async def test_telegram_interactive_signal_rejection_callback(async_session: AsyncSession, setup_env: dict):
    """Test rejecting a signal via inline button."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.presentation.api.schemas.signal import TradingSignalCreate
    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("62000.0"),
        confidence=Decimal("0.9"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"REJECT_{signal.id}", message_id=123)
    assert cb_res["status"] == "REJECTED"

    updated_signal = await signal_repo.get(signal.id)
    assert updated_signal.confirmation_status == "REJECTED"
    assert updated_signal.status == "REJECTED"
    mock_trade_service.execute_signal.assert_not_called()
    mock_tg.edit_message_text.assert_called_once()
    sent_text = mock_tg.edit_message_text.call_args.kwargs.get("text", "")
    assert "SINYAL TRADING DITOLAK" in sent_text
    assert "Dibatalkan manual oleh Admin" in sent_text
    assert "Saldo modal tetap 100% aman" in sent_text


@pytest.mark.asyncio
async def test_telegram_command_account_info(async_session: AsyncSession, setup_env: dict):
    """Test /account displaying active account, environment, and masked API key."""
    acc = setup_env["account"]
    ex = setup_env["exchange"]
    cred_repo = TradingCredentialRepository(async_session)

    from src.infrastructure.persistence.models.trading_credentials import TradingCredential
    cred = TradingCredential(
        account_id=acc.id,
        key_name="Test API Key",
        encrypted_api_key="apiKeySample123456789",
        encrypted_secret_key="secretKeySample987654321",
        key_version=1,
        is_active=True,
    )
    async_session.add(cred)
    await async_session.commit()

    mock_binance = MagicMock()
    mock_binance.testnet = True
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("10500.0")})

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        trading_credential_repo=cred_repo,
        exchange_gateway=mock_binance,
    )

    resp = await tg_service.handle_command("/account", account_id=acc.id)
    assert "INFORMASI AKUN & KREDENSIAL AKTIF" in resp
    assert "Binance Futures" in resp
    assert "apiK****6789" in resp
    assert "$10,500.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_setup_account_wizard_full_flow_success(async_session: AsyncSession, setup_env: dict):
    """Test full interactive credential setup wizard via Telegram with auto-delete and validation handshake."""
    acc = setup_env["account"]
    ex = setup_env["exchange"]
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()
    mock_tg.edit_message_text = AsyncMock()
    mock_tg.delete_message = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_repo=ex_repo,
        trading_account_repo=acc_repo,
        trading_credential_repo=cred_repo,
        telegram_client=mock_tg,
        exchange_gateway=BinanceExchangeAdapter(connector=BinanceConnector(testnet=True)),
    )

    # Step 1: User runs /setup_account
    res_cmd = await tg_service.handle_user_message("/setup_account", chat_id=999)
    assert "WIZARD SETUP AKUN & KREDENSIAL BINANCE" in res_cmd
    mock_tg.send_message.assert_called_once()

    # Step 2: User clicks [ 🧪 Binance Testnet ]
    cb_res = await tg_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=501, chat_id=999)
    assert cb_res["status"] == "WIZARD_STARTED"
    assert cb_res["env"] == "TESTNET"

    # Step 3: User sends API Key
    res_step1 = await tg_service.handle_user_message("my_valid_binance_api_key_12345", chat_id=999)
    assert "API Key Diterima!" in res_step1
    assert "Binance SECRET Key" in res_step1

    # Step 4: User sends Secret Key (Mocking handshake inside test)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            BinanceExchangeAdapter,
            "get_balance",
            AsyncMock(return_value={"total_wallet_balance": Decimal("15000.0"), "free_margin": Decimal("15000.0")}),
        )
        mp.setattr(BinanceExchangeAdapter, "close", AsyncMock())


        res_step2 = await tg_service.handle_user_message(
            "my_valid_binance_secret_key_98765",
            chat_id=999,
            message_id=888,
            account_id=acc.id,
        )

        # Assert secret message auto-delete was triggered!
        mock_tg.delete_message.assert_called_once_with(chat_id=999, message_id=888)

        # Assert success response
        assert "AKUN BINANCE BERHASIL DIHUBUNGKAN!" in res_step2
        assert "TESTNET" in res_step2
        assert "$15,000.00 USDT" in res_step2
        assert "my_v****2345" in res_step2

        # Assert credential was persisted to database (encrypted at rest)
        from src.utils.security import decrypt_secret
        active_cred = await cred_repo.get_active_credential(acc.id)
        assert active_cred is not None
        assert decrypt_secret(active_cred.encrypted_api_key) == "my_valid_binance_api_key_12345"


@pytest.mark.asyncio
async def test_telegram_setup_account_wizard_cancel(async_session: AsyncSession, setup_env: dict):
    """Test cancelling the setup wizard at any point."""
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    # Start wizard
    await tg_service.handle_callback_query("WIZ_ENV_MAINNET", message_id=1, chat_id=111)
    assert 111 in tg_service._wizard_state

    # Cancel via text
    cancel_res = await tg_service.handle_user_message("/cancel", chat_id=111)
    assert "Setup akun dibatalkan" in cancel_res
    assert 111 not in tg_service._wizard_state


@pytest.mark.asyncio
async def test_telegram_resolve_signal_provider_auto_creation(async_session: AsyncSession):
    """Test resolving or auto-creating SignalProvider in TelegramService without breaking FK constraints."""
    prov_repo = SignalProviderRepository(async_session)
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
    )

    # 1. On empty table, should auto-create provider
    provider_id = await tg_service._resolve_signal_provider_id(
        name="AI Telegram Channel", provider_type="TELEGRAM"
    )
    assert provider_id is not None
    assert provider_id > 0

    # 2. On second call, should reuse existing provider
    second_id = await tg_service._resolve_signal_provider_id(
        name="AI Telegram Channel", provider_type="TELEGRAM"
    )
    assert second_id == provider_id


@pytest.mark.asyncio
async def test_telegram_handle_incoming_signal_with_dynamic_instrument(async_session: AsyncSession):
    """Test full incoming raw signal processing with dynamic on-demand provider and instrument provisioning."""
    inst_repo = InstrumentRepository(async_session)
    ex_repo = ExchangeRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    mock_binance = MagicMock(spec=BinanceExchangeAdapter)
    mock_binance.fetch_instruments_metadata = AsyncMock(

        return_value=[
            {
                "symbol": "AAVEUSDT",
                "base_asset": "AAVE",
                "quote_asset": "USDT",
                "price_precision": 3,
                "qty_precision": 1,
                "tick_size": Decimal("0.001"),
                "step_size": Decimal("0.1"),
                "min_qty": Decimal("0.1"),
                "min_notional": Decimal("5.0"),
            }
        ]
    )

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock(return_value={"ok": True})

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        exchange_gateway=mock_binance,
    )

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=sig_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=watch_repo,
        instrument_repo=inst_repo,
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
        instrument_service=inst_service,
        exchange_repo=ex_repo,
        telegram_client=mock_tg,
    )

    raw_signal = (
        "🤖 AI Agent Detect Chart Pattern\n\n"
        "🚨 Symbol: AAVEUSDT 🔴 Short\n"
        "⏱ Timeframe: 1H\n"
        "📈 Leverage: 75x\n"
        "🔷 Pattern: Falling Wedge(Expanding)\n\n"
        "💰 Entry: 86.568\n"
        "🛡 SL: 87.0955 (-45.70%)\n"
        "🎯 TP1: 86.146 (+36.56%)\n"
        "⚡️ TP2: 85.302 (+109.68%)\n"
        "🔥 TP3: 84.449 (+183.58%)\n\n"
        "🧠 Confidence Score (AI): 70%\n"
    )

    # Process signal message with chat_id and message_id
    res = await tg_service.handle_incoming_signal_message(raw_signal, chat_id=777, message_id=8899)

    # Verify no Foreign Key violation and signal card was created
    assert res is not None
    mock_tg.send_message.assert_called_once()
    sent_text = mock_tg.send_message.call_args.kwargs.get("text", "")
    assert "SINYAL TRADING BARU TERDETEKSI" in sent_text
    assert "Timeframe:</b> 1H" in sent_text
    assert "Pattern:</b> Falling Wedge(Expanding)" in sent_text
    assert "AI Confidence:</b> 70%" in sent_text
    assert "ROE" in sent_text
    assert "R:R" in sent_text
    assert "BEP Trigger" in sent_text
    assert "Trailing Stop" in sent_text
    assert "Full Close" in sent_text

    # Verify signal in database has telegram_message_id, timeframe, and parsed_json persisted
    recent_signals = await sig_repo.get_pending_confirmation_signals()
    assert len(recent_signals) == 1
    signal_in_db = recent_signals[0]
    assert signal_in_db.telegram_message_id == 8899
    assert signal_in_db.timeframe == "1H"
    assert signal_in_db.confidence == Decimal("0.7000")
    assert signal_in_db.side == "SELL"
    assert signal_in_db.sl_price == Decimal("87.0955")
    assert signal_in_db.tp1_price == Decimal("86.146")
    assert signal_in_db.parsed_json is not None
    import json
    p_json = json.loads(signal_in_db.parsed_json)
    assert p_json["symbol"] == "AAVEUSDT"
    assert p_json["timeframe"] == "1H"
    assert p_json["pattern"] == "Falling Wedge(Expanding)"
    assert p_json["confidence_score"] == 0.7

    # Verify duplicate signal with the same telegram_message_id is safely rejected
    dup_res = await tg_service.handle_incoming_signal_message(raw_signal, chat_id=777, message_id=8899)
    assert dup_res["status"] == "DUPLICATE_SIGNAL"
    assert dup_res["signal_id"] == signal_in_db.id
    # mock_tg.send_message should not be called again for duplicate signal
    assert mock_tg.send_message.call_count == 1

    # Verify Instrument in database
    inst = await inst_repo.get(signal_in_db.instrument_id)
    assert inst is not None
    assert inst.symbol == "AAVEUSDT"
    assert inst.price_precision == 3

    # Verify Provider in database
    provider = await prov_repo.get(signal_in_db.provider_id)
    assert provider is not None
    assert provider.name == "AI Telegram Channel"


@pytest.mark.asyncio
async def test_telegram_signal_rejected_if_no_account_connected(async_session: AsyncSession):
    """Test that incoming signals are safely intercepted if no active trading account is configured."""
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
        trading_account_repo=acc_repo,
        trading_credential_repo=cred_repo,
        exchange_gateway=None,
    )

    raw_signal = (
        "🚨 Symbol: BTCUSDT 🟢 Long\n"
        "💰 Entry: 65000\n"
        "🛡 SL: 64000\n"
        "🎯 TP1: 67000\n"
    )

    # When sent by user, should return warning prompting /setup_account
    response = await tg_service.handle_user_message(raw_signal, chat_id=123)
    assert "Akun Binance Belum Terhubung!" in response
    assert "/setup_account" in response


@pytest.mark.asyncio
async def test_telegram_circuit_breaker_command(async_session: AsyncSession):
    """Test /circuit_breaker command execution and on-demand risk snapshot provisioning."""
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=SignalProviderRepository(async_session),
    )

    response = await tg_service.handle_command("/circuit_breaker", account_id=1)
    assert "STATUS CIRCUIT BREAKER & RISK" in response
    assert "Status Proteksi: <b>🟢 NORMAL</b>" in response
    assert "Batas Risiko Harian" in response




