"""Use case for synchronizing instruments and leverage brackets from Exchange."""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List

from src.domain.ports.repositories import (
    IInstrumentRepository,
    IExchangeRepository,
    IWatchlistRepository,
    IInstrumentLeverageBracketRepository,
    ITradingCredentialRepository,
    ITradingAccountRepository,
)
from src.infrastructure.persistence.models.instruments import Instrument

from src.domain.ports.gateways import IExchangeGateway
from src.presentation.api.schemas.master import (
    InstrumentCreate,
    ExchangeCreate,
    SyncInstrumentsResponseDTO,
)
from src.utils.security import decrypt_secret


logger = logging.getLogger(__name__)


class SyncInstrumentsUseCase:
    """Use case to fetch all active USDT-M contracts from Exchange and bulk upsert them into database & watchlist."""

    def __init__(
        self,
        instrument_repo: IInstrumentRepository,
        exchange_gateway: Optional[IExchangeGateway] = None,
        exchange_repo: Optional[IExchangeRepository] = None,
        watchlist_repo: Optional[IWatchlistRepository] = None,
        bracket_repo: Optional[IInstrumentLeverageBracketRepository] = None,
        credential_repo: Optional[ITradingCredentialRepository] = None,
        account_repo: Optional[ITradingAccountRepository] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.exchange_gateway = exchange_gateway
        self.exchange_repo = exchange_repo
        self.watchlist_repo = watchlist_repo
        self.bracket_repo = bracket_repo
        self.credential_repo = credential_repo
        self.account_repo = account_repo

    async def _ensure_authenticated_client(self) -> None:
        if not self.exchange_gateway:
            raise ValueError("Exchange gateway is required for syncing instruments from exchange.")

        if self.credential_repo:
            try:
                active_cred = await self.credential_repo.get_active_credential(account_id=1)
                if active_cred and active_cred.encrypted_api_key:
                    is_testnet = True
                    if self.account_repo:
                        acc = await self.account_repo.get(active_cred.account_id)
                        if acc and acc.environment:
                            is_testnet = acc.environment.upper() == "TESTNET"
                    if hasattr(self.exchange_gateway, "reconfigure"):
                        raw_api = decrypt_secret(active_cred.encrypted_api_key) or ""
                        raw_sec = decrypt_secret(active_cred.encrypted_secret_key) or ""
                        self.exchange_gateway.reconfigure(
                            api_key=raw_api,
                            secret_key=raw_sec,
                            testnet=is_testnet,
                        )
            except Exception as e:
                logger.warning(f"Could not auto-configure credentials for exchange gateway: {e}")


    async def _ensure_exchange_id(self, exchange_id: Optional[int] = None) -> int:
        if exchange_id is not None:
            return exchange_id
        if self.exchange_repo:
            exchange = await self.exchange_repo.get_by_code("BINANCE")
            if not exchange:
                exchange = await self.exchange_repo.create(
                    ExchangeCreate(code="BINANCE", name="Binance Futures", status=True)
                )
            if exchange:
                return exchange.id
        return 1

    async def get_or_sync_instrument(
        self, symbol: str, exchange_id: Optional[int] = None
    ) -> Optional[Instrument]:
        """Fetch instrument from DB, or dynamically fetch authentic specifications from Binance if not yet stored."""
        clean_sym = symbol.strip().upper().replace("/", "").replace(":USDT", "")
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)

        inst = await self.instrument_repo.get_by_symbol(clean_sym, exchange_id=resolved_ex_id)
        if inst:
            if self.watchlist_repo:
                await self.watchlist_repo.set_symbol_enabled(inst.id, True)

            if self.bracket_repo and self.exchange_gateway:
                existing_brackets = await self.bracket_repo.get_brackets_by_instrument(inst.id)
                if not existing_brackets:
                    try:
                        await self._ensure_authenticated_client()
                        b_data = await self.exchange_gateway.fetch_leverage_brackets(clean_sym)
                        if b_data:
                            await self.bracket_repo.bulk_upsert_brackets(inst.id, b_data[0].get("brackets", []))
                    except Exception as e:
                        logger.warning(f"Could not fetch leverage brackets for {clean_sym}: {e}")

            return inst

        # Dynamic on-demand resolution from Binance gateway
        if self.exchange_gateway is None:
            logger.warning("No exchange gateway configured for sync_instruments.")
            return None

        logger.info(f"Symbol {clean_sym} not in database. Fetching live specifications from Binance...")
        try:
            metadata_list = await self.exchange_gateway.fetch_instruments_metadata()
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

                if self.bracket_repo and self.exchange_gateway is not None:
                    try:
                        await self._ensure_authenticated_client()
                        b_data = await self.exchange_gateway.fetch_leverage_brackets(clean_sym)
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

    async def execute(self, exchange_id: Optional[int] = None, symbol_filter: Optional[List[str]] = None) -> SyncInstrumentsResponseDTO:
        """Fetch all active USDT-M contracts from Binance and bulk upsert them into database & watchlist."""
        now_utc = datetime.now(timezone.utc)
        resolved_ex_id = await self._ensure_exchange_id(exchange_id)
        await self._ensure_authenticated_client()
        if self.exchange_gateway is None:
            logger.warning("No exchange gateway configured for sync_instruments.")
            return SyncInstrumentsResponseDTO(
                synced_instruments=0,
                synced_brackets=0,
                timestamp=now_utc,
            )
        try:
            metadata_list = await self.exchange_gateway.fetch_instruments_metadata()
            if not metadata_list:
                return SyncInstrumentsResponseDTO(
                    synced_instruments=0,
                    synced_brackets=0,
                    timestamp=now_utc,
                )

            create_dtos: List[InstrumentCreate] = []
            for item in metadata_list:
                raw_sym = item.get("symbol", "").strip().upper()
                clean_sym = raw_sym.replace("/", "").replace(":USDT", "")
                base_asset = item.get("base_asset") or clean_sym.replace("USDT", "")
                quote_asset = item.get("quote_asset") or "USDT"

                create_dtos.append(
                    InstrumentCreate(
                        exchange_id=resolved_ex_id,
                        symbol=clean_sym,
                        base_asset=base_asset,
                        quote_asset=quote_asset,
                        tick_size=Decimal(str(item.get("tick_size", "0.01"))),
                        step_size=Decimal(str(item.get("step_size", "0.001"))),
                        min_qty=Decimal(str(item.get("min_qty", "0.001"))),
                        min_notional=Decimal(str(item.get("min_notional", "5.0"))),
                        price_precision=int(item.get("price_precision", 2)),
                        qty_precision=int(item.get("qty_precision", 3)),
                        is_active=True,
                    )
                )

            synced_count = await self.instrument_repo.bulk_upsert_instruments(create_dtos)
            all_active = await self.instrument_repo.get_all_active(resolved_ex_id)

            if self.watchlist_repo:
                for inst in all_active:
                    await self.watchlist_repo.set_symbol_enabled(inst.id, True)


            synced_brackets = 0
            if self.bracket_repo and (
                hasattr(self.exchange_gateway, "fetch_all_leverage_brackets")
                or hasattr(self.exchange_gateway, "fetch_leverage_brackets")
            ):
                try:
                    fetch_brackets = getattr(self.exchange_gateway, "fetch_all_leverage_brackets", None) or getattr(
                        self.exchange_gateway, "fetch_leverage_brackets"
                    )
                    all_brackets_data = await fetch_brackets()


                    if all_brackets_data:
                        inst_map = {inst.symbol: inst.id for inst in all_active}
                        for b_entry in all_brackets_data:
                            b_sym = b_entry.get("symbol", "").strip().upper().replace("/", "").replace(":USDT", "")
                            inst_id = inst_map.get(b_sym)
                            if inst_id:
                                await self.bracket_repo.bulk_upsert_brackets(
                                    inst_id, b_entry.get("brackets", [])
                                )
                                synced_brackets += 1
                except Exception as e:
                    logger.warning(f"Could not bulk sync leverage brackets: {e}")

            logger.info(f"Synchronized {synced_count} instruments for exchange {resolved_ex_id}")
            return SyncInstrumentsResponseDTO(
                synced_instruments=synced_count,
                synced_brackets=synced_brackets or synced_count,
                timestamp=now_utc,
            )
        except Exception as e:
            logger.error(f"Failed to sync instruments from Binance: {e}")
            return SyncInstrumentsResponseDTO(
                synced_instruments=0,
                synced_brackets=0,
                timestamp=datetime.now(timezone.utc),
            )

    async def sync_all_instruments(self, exchange_id: Optional[int] = None) -> int:
        """Alias method to sync all instruments and return the integer count."""
        res = await self.execute(exchange_id=exchange_id)
        return res.synced_instruments

    async def sync_all_active_instruments(
        self, exchange_id: Optional[int] = None, symbol_filter: Optional[List[str]] = None
    ) -> int:
        """Alias method to sync active instruments with optional symbol filter."""
        res = await self.execute(exchange_id=exchange_id, symbol_filter=symbol_filter)
        return res.synced_instruments


