"""Instrument service for managing trading pair metadata, precision sync, and watchlist orchestration."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from src.database.models import Instrument
from src.schemas.master import (
    InstrumentCreate,
    ExchangeCreate,
    InstrumentDTO,
    LeverageBracketDTO,
    SyncInstrumentsResponseDTO,
)
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.exchange_repository import ExchangeRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.clients.binance_client import BinanceRestClient

logger = logging.getLogger(__name__)


class InstrumentService:
    """Orchestrates instrument metadata synchronization from Binance, on-demand symbol resolution, and watchlist enrollment."""

    def __init__(
        self,
        instrument_repo: InstrumentRepository,
        exchange_repo: Optional[ExchangeRepository] = None,
        watchlist_repo: Optional[WatchlistRepository] = None,
        bracket_repo: Optional[InstrumentLeverageBracketRepository] = None,
        credential_repo: Optional[TradingCredentialRepository] = None,
        account_repo: Optional[TradingAccountRepository] = None,
        binance_client: Optional[BinanceRestClient] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.exchange_repo = exchange_repo
        self.watchlist_repo = watchlist_repo
        self.bracket_repo = bracket_repo
        self.credential_repo = credential_repo
        self.account_repo = account_repo
        self.binance_client = binance_client

    async def _ensure_authenticated_client(self) -> None:
        """Dynamically configure Binance client with active credentials for authenticated endpoints."""
        if not self.binance_client:
            self.binance_client = BinanceRestClient()

        api_key = getattr(self.binance_client, "api_key", None)
        secret_key = getattr(self.binance_client, "secret_key", None)

        if (not api_key or not secret_key) and self.credential_repo:
            try:
                active_cred = await self.credential_repo.get_active_credential(account_id=1)
                if active_cred and active_cred.encrypted_api_key:
                    is_testnet = True
                    if self.account_repo:
                        acc = await self.account_repo.get(active_cred.account_id)
                        if acc and acc.environment:
                            is_testnet = acc.environment.upper() == "TESTNET"
                    if hasattr(self.binance_client, "reconfigure"):
                        self.binance_client.reconfigure(
                            api_key=active_cred.encrypted_api_key,
                            secret_key=active_cred.encrypted_secret_key,
                            testnet=is_testnet,
                        )
            except Exception as e:
                logger.warning(f"Could not auto-configure credentials for Binance client: {e}")

    async def _ensure_exchange_id(self, exchange_id: Optional[int] = None) -> int:
        """Resolve or provision the default Binance exchange entity ID."""
        if exchange_id is not None:
            return exchange_id

        if self.exchange_repo:
            exchange = await self.exchange_repo.get_by_code("BINANCE")
            if not exchange:
                exchange = await self.exchange_repo.create(
                    ExchangeCreate(code="BINANCE", name="Binance Futures", status=True)
                )
            return exchange.id

        return 1

    async def get_or_sync_instrument(
        self, symbol: str, exchange_id: Optional[int] = None
    ) -> Optional[Instrument]:
        """Fetch instrument from database, or dynamically fetch authentic specifications from Binance if not yet stored.
        
        Args:
            symbol: Trading pair symbol, e.g. "BTCUSDT".
            exchange_id: Optional exchange FK.
            
        Returns:
            Resolved Instrument instance or None if non-existent on exchange.
        """
        clean_sym = symbol.strip().upper().replace("/", "").replace(":USDT", "")
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)

        # 1. Look up existing in DB
        inst = await self.instrument_repo.get_by_symbol(clean_sym, exchange_id=resolved_ex_id)
        if inst:
            # Re-enable in watchlist if disabled
            if self.watchlist_repo:
                await self.watchlist_repo.set_symbol_enabled(inst.id, True)

            # Ensure leverage brackets are populated
            if self.bracket_repo and self.binance_client:
                existing_brackets = await self.bracket_repo.get_brackets_by_instrument(inst.id)
                if not existing_brackets:
                    try:
                        await self._ensure_authenticated_client()
                        b_data = await self.binance_client.fetch_leverage_brackets(clean_sym)
                        if b_data:
                            await self.bracket_repo.bulk_upsert_brackets(inst.id, b_data[0].get("brackets", []))
                    except Exception as e:
                        logger.warning(f"Could not fetch leverage brackets for {clean_sym}: {e}")

            return inst

        # 2. On-demand sync from Binance REST API
        if self.binance_client:
            logger.info(f"Symbol {clean_sym} not in database. Fetching live specifications from Binance...")
            try:
                metadata_list = await self.binance_client.fetch_instruments_metadata()
                matched_item: Optional[Dict[str, Any]] = None

                for item in metadata_list:
                    item_sym = item.get("symbol", "").strip().upper().replace("/", "").replace(":USDT", "")
                    if item_sym == clean_sym:
                        matched_item = item
                        break

                if matched_item:
                    base_asset = matched_item.get("base_asset") or clean_sym.replace("USDT", "")
                    quote_asset = matched_item.get("quote_asset") or "USDT"

                    create_dto = InstrumentCreate(
                        exchange_id=resolved_ex_id,
                        symbol=clean_sym,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        tick_size=Decimal(str(matched_item.get("tick_size", "0.01"))),
                        step_size=Decimal(str(matched_item.get("step_size", "0.001"))),
                        min_qty=Decimal(str(matched_item.get("min_qty", "0.001"))),
                        min_notional=Decimal(str(matched_item.get("min_notional", "5.0"))),
                        price_precision=int(matched_item.get("price_precision", 2)),
                        qty_precision=int(matched_item.get("qty_precision", 3)),
                        is_active=True,
                    )
                    inst = await self.instrument_repo.create(create_dto)
                    logger.info(f"Successfully registered and synced new Instrument: {clean_sym} (ID: {inst.id})")

                    # Fetch and save leverage brackets for the new instrument
                    if self.bracket_repo:
                        try:
                            await self._ensure_authenticated_client()
                            b_data = await self.binance_client.fetch_leverage_brackets(clean_sym)
                            if b_data:
                                await self.bracket_repo.bulk_upsert_brackets(inst.id, b_data[0].get("brackets", []))
                                logger.info(f"Synced leverage brackets for new Instrument {clean_sym}")
                        except Exception as e:
                            logger.warning(f"Could not fetch leverage brackets for new instrument {clean_sym}: {e}")

                    if self.watchlist_repo:
                        await self.watchlist_repo.set_symbol_enabled(inst.id, True)

                    refetched = await self.instrument_repo.get_by_symbol(clean_sym, exchange_id=resolved_ex_id)
                    return refetched or inst
                else:
                    logger.warning(f"Symbol {clean_sym} is not a valid active USDT contract on Binance Futures.")
            except Exception as e:
                logger.error(f"Failed to fetch live instrument specifications from Binance for {clean_sym}: {e}")

        return None

    async def list_all_instruments(self, exchange_id: Optional[int] = None) -> List[InstrumentDTO]:
        """Fetch all active instruments with leverage brackets mapped to InstrumentDTOs.

        Returns:
            List of InstrumentDTO instances.
        """
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)
        instruments = await self.instrument_repo.get_all_instruments_with_brackets(resolved_ex_id)

        result: List[InstrumentDTO] = []
        for inst in instruments:
            max_lev = 125
            brackets_dto: List[LeverageBracketDTO] = []
            if inst.leverage_brackets:
                max_lev = max(b.initial_leverage for b in inst.leverage_brackets)
                for b in inst.leverage_brackets:
                    brackets_dto.append(
                        LeverageBracketDTO(
                            bracket=b.bracket,
                            initial_leverage=b.initial_leverage,
                            notional_cap=float(b.notional_cap),
                            notional_floor=float(b.notional_floor),
                            maint_margin_ratio=float(b.maint_margin_ratio),
                            cum=float(b.cum),
                        )
                    )

            result.append(
                InstrumentDTO(
                    symbol=inst.symbol,
                    base_asset=inst.base_asset,
                    quote_asset=inst.quote_asset,
                    price_precision=inst.price_precision,
                    qty_precision=inst.qty_precision,
                    tick_size=float(inst.tick_size),
                    step_size=float(inst.step_size),
                    min_notional=float(inst.min_notional),
                    max_leverage=max_lev,
                    brackets=brackets_dto if brackets_dto else None,
                )
            )

        return result

    async def sync_all_instruments(self, exchange_id: Optional[int] = None) -> int:
        """Fetch all active USDT-M contracts from Binance and bulk upsert them into database & watchlist.
        
        Returns:
            Number of synchronized instruments.
        """
        if not self.binance_client:
            return 0

        resolved_ex_id = await self._ensure_exchange_id(exchange_id)
        await self._ensure_authenticated_client()
        try:
            metadata_list = await self.binance_client.fetch_instruments_metadata()
            if not metadata_list:
                return 0

            schemas: List[InstrumentCreate] = []
            for item in metadata_list:
                schemas.append(
                    InstrumentCreate(
                        exchange_id=resolved_ex_id,
                        symbol=item["symbol"].replace("/", "").replace(":USDT", ""),
                        base_asset=item.get("base_asset", item["symbol"].replace("USDT", "")),
                        quote_asset=item.get("quote_asset", "USDT"),
                        tick_size=Decimal(str(item.get("tick_size", "0.1"))),
                        step_size=Decimal(str(item.get("step_size", "0.001"))),
                        min_qty=Decimal(str(item.get("min_qty", "0.001"))),
                        min_notional=Decimal(str(item.get("min_notional", "5.0"))),
                        price_precision=int(item.get("price_precision", 2)),
                        qty_precision=int(item.get("qty_precision", 3)),
                        is_active=True,
                    )
                )

            count = await self.instrument_repo.bulk_upsert_instruments(schemas)
            logger.info(f"Bulk-synced {count} instrument records from Binance.")

            if self.watchlist_repo:
                all_active = await self.instrument_repo.get_all_active(resolved_ex_id)
                for active_inst in all_active:
                    await self.watchlist_repo.set_symbol_enabled(active_inst.id, True)

            # Bulk sync leverage brackets for all active instruments
            if self.bracket_repo:
                try:
                    all_brackets = await self.binance_client.fetch_leverage_brackets()
                    all_active = await self.instrument_repo.get_all_active(resolved_ex_id)
                    inst_map = {item.symbol.upper(): item for item in all_active}
                    synced_brackets = 0
                    for b_item in all_brackets:
                        sym = b_item.get("symbol", "").upper()
                        if sym in inst_map:
                            await self.bracket_repo.bulk_upsert_brackets(inst_map[sym].id, b_item.get("brackets", []))
                            synced_brackets += 1
                    logger.info(f"Bulk-synced leverage brackets for {synced_brackets} active instruments.")
                except Exception as e:
                    logger.error(f"Failed to bulk-sync leverage brackets from Binance: {e}")

            return count
        except Exception as e:
            logger.error(f"Failed to bulk-sync instruments from Binance: {e}")
            return 0

    async def sync_exchange_instruments(self, exchange_id: Optional[int] = None) -> SyncInstrumentsResponseDTO:
        """Execute on-demand sync of exchange info and leverage brackets.

        Returns:
            SyncInstrumentsResponseDTO containing counts and timestamp.
        """
        synced_count = await self.sync_all_instruments(exchange_id)
        
        # Count synced brackets
        synced_brackets = 0
        if self.bracket_repo:
            resolved_ex_id = await self._ensure_exchange_id(exchange_id)
            all_active = await self.instrument_repo.get_all_active(resolved_ex_id)
            for item in all_active:
                brackets = await self.bracket_repo.get_brackets_by_instrument(item.id)
                if brackets:
                    synced_brackets += 1

        now_utc = datetime.now(timezone.utc)
        return SyncInstrumentsResponseDTO(
            synced_instruments=synced_count,
            synced_brackets=synced_brackets or synced_count,
            timestamp=now_utc,
        )

