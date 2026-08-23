"""Instrument service for managing trading pair metadata, precision sync, and watchlist orchestration."""

import logging
from decimal import Decimal
from typing import Optional, List, Dict, Any

from src.database.models import Instrument
from src.schemas.master import InstrumentCreate, ExchangeCreate
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.exchange_repository import ExchangeRepository
from src.repository.watchlist_repository import WatchlistRepository
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
        binance_client: Optional[BinanceRestClient] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.exchange_repo = exchange_repo
        self.watchlist_repo = watchlist_repo
        self.bracket_repo = bracket_repo
        self.binance_client = binance_client

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
            symbol: Trading pair symbol (e.g. "AAVEUSDT", "BTCUSDT").
            exchange_id: Optional exchange ID filter.
            
        Returns:
            The resolved Instrument instance with verified precision filters, or None if invalid on Binance.
        """
        clean_sym = symbol.strip().upper().replace("/", "").replace(":USDT", "")
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)

        # 1. Check local database
        inst = await self.instrument_repo.get_by_symbol(clean_sym, exchange_id=resolved_ex_id)
        if inst:
            if self.watchlist_repo:
                await self.watchlist_repo.set_symbol_enabled(inst.id, True)

            # Ensure leverage brackets are populated
            if self.bracket_repo and self.binance_client:
                existing_brackets = await self.bracket_repo.get_brackets_by_instrument(inst.id)
                if not existing_brackets:
                    try:
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
                            b_data = await self.binance_client.fetch_leverage_brackets(clean_sym)
                            if b_data:
                                await self.bracket_repo.bulk_upsert_brackets(inst.id, b_data[0].get("brackets", []))
                                logger.info(f"Synced leverage brackets for new Instrument {clean_sym}")
                        except Exception as e:
                            logger.warning(f"Could not fetch leverage brackets for new instrument {clean_sym}: {e}")

                    if self.watchlist_repo:
                        await self.watchlist_repo.set_symbol_enabled(inst.id, True)
                    return inst
                else:
                    logger.warning(f"Symbol {clean_sym} is not a valid active USDT contract on Binance Futures.")
            except Exception as e:
                logger.error(f"Failed to fetch live instrument specifications from Binance for {clean_sym}: {e}")

        return None

    async def sync_all_instruments(self, exchange_id: Optional[int] = None) -> int:
        """Fetch all active USDT-M contracts from Binance and bulk upsert them into database & watchlist.
        
        Returns:
            Number of synchronized instruments.
        """
        if not self.binance_client:
            return 0

        resolved_ex_id = await self._ensure_exchange_id(exchange_id)
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
                for item in all_active:
                    await self.watchlist_repo.set_symbol_enabled(item.id, True)

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
