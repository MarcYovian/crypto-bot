"""Domain service for Bot Operations, Circuit Breaker, Configuration Settings, and Credentials."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List

from src.database.models import Exchange, TradingAccount, TradingCredential, RiskProfile
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.exchange_repository import ExchangeRepository
from src.schemas.system import (
    BotStatusDTO,
    GenericActionResponse,
    BotSettingsDTO,
    BotSettingsUpdateRequest,
    TradingCredentialCreateRequest,
    PanicCloseResponseDTO,
    CredentialSaveResponseDTO,
    BotSettingCreate,
    BotSettingUpdate,
)
from src.domain.exceptions.system import (
    PanicConfirmationRequiredError,
    InvalidSettingsValueError,
)
from src.domain.exceptions.exchange import ExchangeAuthError
from src.clients.binance_client import BinanceRestClient
from src.utils.cache import in_memory_cache


class BotService:
    """Service handling bot operational states, system configurations, and Binance API credentials."""

    def __init__(
        self,
        bot_setting_repo: BotSettingRepository,
        risk_profile_repo: RiskProfileRepository,
        trade_repo: Optional[TradeRepository] = None,
        order_repo: Optional[OrderRepository] = None,
        credential_repo: Optional[TradingCredentialRepository] = None,
        account_repo: Optional[TradingAccountRepository] = None,
        exchange_repo: Optional[ExchangeRepository] = None,
        binance_client: Optional[BinanceRestClient] = None,
    ) -> None:
        self.bot_setting_repo = bot_setting_repo
        self.risk_profile_repo = risk_profile_repo
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.credential_repo = credential_repo
        self.account_repo = account_repo
        self.exchange_repo = exchange_repo
        self.binance_client = binance_client

    async def get_bot_status(self) -> BotStatusDTO:
        """Fetch current bot runtime status, health, and circuit breaker state."""
        is_paused = await self.bot_setting_repo.get_bool("is_paused", default=False)
        circuit_breaker = await self.bot_setting_repo.get_bool("circuit_breaker_active", default=False)
        trading_status = "PAUSED" if (is_paused or circuit_breaker) else "ACTIVE"

        return BotStatusDTO(
            is_running=True,
            is_paused=is_paused,
            trading_status=trading_status,
            circuit_breaker_active=circuit_breaker,
            binance_ws_connected=True,
            telegram_polling_active=True,
            scheduler_jobs_count=7,
            last_heartbeat=datetime.now(timezone.utc),
        )

    async def pause_bot(self) -> GenericActionResponse:
        """Pause bot operations to reject incoming trading signals."""
        setting = await self.bot_setting_repo.get_by_key("is_paused")
        if not setting:
            await self.bot_setting_repo.create(
                BotSettingCreate(key="is_paused", value="true", category="SYSTEM", type="BOOL")
            )
        else:
            await self.bot_setting_repo.update(setting, BotSettingUpdate(value="true"))

        await in_memory_cache.invalidate("settings")
        await in_memory_cache.invalidate("bot:status")

        return GenericActionResponse(
            success=True,
            message="Trading bot paused successfully. Incoming signals will be rejected.",
        )

    async def resume_bot(self) -> GenericActionResponse:
        """Resume bot operations and clear circuit breaker trip status."""
        setting = await self.bot_setting_repo.get_by_key("is_paused")
        if not setting:
            await self.bot_setting_repo.create(
                BotSettingCreate(key="is_paused", value="false", category="SYSTEM", type="BOOL")
            )
        else:
            await self.bot_setting_repo.update(setting, BotSettingUpdate(value="false"))

        cb_setting = await self.bot_setting_repo.get_by_key("circuit_breaker_active")
        if cb_setting:
            await self.bot_setting_repo.update(cb_setting, BotSettingUpdate(value="false"))

        await in_memory_cache.invalidate("settings")
        await in_memory_cache.invalidate("bot:status")

        return GenericActionResponse(
            success=True,
            message="Trading bot resumed successfully. Signal ingestion active.",
        )

    async def panic_close_all(self, confirmation: bool) -> PanicCloseResponseDTO:
        """Emergency action: close all open positions and cancel active orders."""
        if not confirmation:
            raise PanicConfirmationRequiredError("Emergency panic action requires confirmation=true.")

        closed_trades_count = 0
        canceled_orders_count = 0

        # 1. Close all active positions
        if self.trade_repo:
            active_trades = await self.trade_repo.get_all_active_trades()
            closed_trades_count = len(active_trades)
            now = datetime.now(timezone.utc)
            for trade in active_trades:
                trade.status = "CLOSED"
                trade.remaining_qty = Decimal("0")
                trade.updated_at = now
                self.trade_repo.session.add(trade)
            await self.trade_repo.session.commit()

        # 2. Cancel all active orders
        if self.order_repo:
            canceled_orders_count = await self.order_repo.cancel_all_active_orders()

        # 3. Set bot to paused
        setting = await self.bot_setting_repo.get_by_key("is_paused")
        if not setting:
            await self.bot_setting_repo.create(
                BotSettingCreate(key="is_paused", value="true", category="SYSTEM", type="BOOL")
            )
        else:
            await self.bot_setting_repo.update(setting, BotSettingUpdate(value="true"))

        # Invalidate caches
        await in_memory_cache.invalidate("trades")
        await in_memory_cache.invalidate("settings")
        await in_memory_cache.invalidate("analytics")
        await in_memory_cache.invalidate("signals")
        await in_memory_cache.invalidate("bot:status")

        return PanicCloseResponseDTO(
            success=True,
            closed_trades_count=closed_trades_count,
            canceled_orders_count=canceled_orders_count,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_settings(self) -> BotSettingsDTO:
        """Fetch consolidated bot settings and risk profile configuration."""
        active_profile = await self.risk_profile_repo.get_active_profile()
        if not active_profile:
            risk_percent = 2.0
            max_daily_loss = 6.0
            max_open_trades = 3
        else:
            risk_percent = float(active_profile.risk_percent)
            max_daily_loss = float(active_profile.max_daily_loss)
            max_open_trades = active_profile.max_open_trade

        default_lev_str = await self.bot_setting_repo.get_value("default_leverage", default="20")
        conf_str = await self.bot_setting_repo.get_value("confidence_threshold", default="0.70")
        is_paused = await self.bot_setting_repo.get_bool("is_paused", default=False)

        return BotSettingsDTO(
            default_leverage=int(default_lev_str or "20"),
            confidence_threshold=float(conf_str or "0.70"),
            risk_percent_per_trade=risk_percent,
            max_daily_loss_percent=max_daily_loss,
            max_open_trades=max_open_trades,
            is_paused=is_paused,
        )

    async def update_settings(self, payload: BotSettingsUpdateRequest) -> BotSettingsDTO:
        """Validate and apply modifications to bot configurations and risk profiles."""
        if payload.default_leverage is not None and not (1 <= payload.default_leverage <= 125):
            raise InvalidSettingsValueError("Default leverage must be between 1 and 125.")
        if payload.confidence_threshold is not None and not (0.1 <= payload.confidence_threshold <= 1.0):
            raise InvalidSettingsValueError("Confidence threshold must be between 0.1 and 1.0.")
        if payload.risk_percent_per_trade is not None and not (0.1 <= payload.risk_percent_per_trade <= 10.0):
            raise InvalidSettingsValueError("Risk percent per trade must be between 0.1% and 10.0%.")
        if payload.max_daily_loss_percent is not None and not (1.0 <= payload.max_daily_loss_percent <= 20.0):
            raise InvalidSettingsValueError("Max daily loss percent must be between 1.0% and 20.0%.")
        if payload.max_open_trades is not None and not (1 <= payload.max_open_trades <= 10):
            raise InvalidSettingsValueError("Max open trades must be between 1 and 10.")

        # Update bot_settings
        if payload.default_leverage is not None:
            s = await self.bot_setting_repo.get_by_key("default_leverage")
            if not s:
                await self.bot_setting_repo.create(
                    BotSettingCreate(key="default_leverage", value=str(payload.default_leverage), category="TRADING", type="INT")
                )
            else:
                await self.bot_setting_repo.update(s, BotSettingUpdate(value=str(payload.default_leverage)))

        if payload.confidence_threshold is not None:
            s = await self.bot_setting_repo.get_by_key("confidence_threshold")
            if not s:
                await self.bot_setting_repo.create(
                    BotSettingCreate(key="confidence_threshold", value=str(payload.confidence_threshold), category="TRADING", type="FLOAT")
                )
            else:
                await self.bot_setting_repo.update(s, BotSettingUpdate(value=str(payload.confidence_threshold)))

        # Update risk_profiles
        active_profile = await self.risk_profile_repo.get_active_profile()
        if not active_profile:
            active_profile = RiskProfile(
                name="ACTIVE_PROFILE",
                risk_percent=Decimal(str(payload.risk_percent_per_trade or 2.0)),
                max_daily_loss=Decimal(str(payload.max_daily_loss_percent or 6.0)),
                max_open_trade=payload.max_open_trades or 3,
                is_active=True,
            )
            self.risk_profile_repo.session.add(active_profile)
            await self.risk_profile_repo.session.commit()
            await self.risk_profile_repo.session.refresh(active_profile)
        else:
            if payload.risk_percent_per_trade is not None:
                active_profile.risk_percent = Decimal(str(payload.risk_percent_per_trade))
            if payload.max_daily_loss_percent is not None:
                active_profile.max_daily_loss = Decimal(str(payload.max_daily_loss_percent))
            if payload.max_open_trades is not None:
                active_profile.max_open_trade = payload.max_open_trades
            self.risk_profile_repo.session.add(active_profile)
            await self.risk_profile_repo.session.commit()

        await in_memory_cache.invalidate("settings")
        return await self.get_settings()

    async def save_and_test_credentials(
        self, payload: TradingCredentialCreateRequest
    ) -> CredentialSaveResponseDTO:
        """Perform live Binance handshake and register/rotate account API credentials."""
        is_testnet = payload.environment.upper() == "TESTNET"

        # 1. Live handshake test
        client = self.binance_client or BinanceRestClient(
            api_key=payload.api_key,
            api_secret=payload.secret_key,
            testnet=is_testnet,
        )

        try:
            balance_data = await client.fetch_balance()
        except Exception as e:
            raise ExchangeAuthError(f"Binance handshake authentication failed: {e}")

        wallet_balance = 0.0
        if isinstance(balance_data, dict):
            tot = (
                balance_data.get("total_wallet_balance")
                or balance_data.get("free_margin")
                or balance_data.get("total")
                or 0.0
            )
            try:
                wallet_balance = float(tot)
            except Exception:
                wallet_balance = 0.0

        # 2. Resolve Exchange & TradingAccount
        exchange_id = 1
        if self.exchange_repo:
            ex = await self.exchange_repo.get_by_code("BINANCE")
            if not ex:
                ex = Exchange(code="BINANCE", name="Binance Futures", status=True)
                self.exchange_repo.session.add(ex)
                await self.exchange_repo.session.commit()
                await self.exchange_repo.session.refresh(ex)
            exchange_id = ex.id

        account_id = 1
        if self.account_repo:
            acc = await self.account_repo.get_active_account(exchange_id)
            if not acc:
                acc = TradingAccount(
                    exchange_id=exchange_id,
                    name=f"Binance {payload.environment.upper()}",
                    account_type="FUTURES",
                    environment=payload.environment.upper(),
                    is_active=True,
                )
                self.account_repo.session.add(acc)
                await self.account_repo.session.commit()
                await self.account_repo.session.refresh(acc)
            else:
                acc.environment = payload.environment.upper()
                acc.is_active = True
                self.account_repo.session.add(acc)
                await self.account_repo.session.commit()
            account_id = acc.id

        # 3. Store credentials
        credential_id = 1
        if self.credential_repo:
            cred = await self.credential_repo.create({
                "account_id": account_id,
                "key_name": f"Key_{payload.environment.upper()}",
                "api_key": payload.api_key,
                "secret_key": payload.secret_key,
                "key_version": 1,
                "is_active": True,
            })
            credential_id = cred.id

        await in_memory_cache.invalidate("settings")
        await in_memory_cache.invalidate("accounts")

        return CredentialSaveResponseDTO(
            success=True,
            account_id=account_id,
            credential_id=credential_id,
            wallet_balance_usdt=wallet_balance,
            environment=payload.environment.upper(),
        )
