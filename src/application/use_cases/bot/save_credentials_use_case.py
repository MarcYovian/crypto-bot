from typing import Optional, Any
from src.domain.ports.gateways import IExchangeGateway
from src.domain.exceptions.exchange import ExchangeAuthError
from src.domain.ports.repositories import (
    ITradingCredentialRepository,
    ITradingAccountRepository,
    IExchangeRepository,
)
from src.infrastructure.persistence.models.exchange import Exchange
from src.infrastructure.persistence.models.trading_accounts import TradingAccount

from src.presentation.api.schemas.system import (
    TradingCredentialCreateRequest,
    CredentialSaveResponseDTO,
)
from src.utils.cache import in_memory_cache


class SaveCredentialsUseCase:
    """Use case to validate Exchange credentials via handshake and persist them securely."""

    def __init__(
        self,
        credential_repo: Optional[ITradingCredentialRepository] = None,
        account_repo: Optional[ITradingAccountRepository] = None,
        exchange_repo: Optional[IExchangeRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        cache: Optional[Any] = None,
    ) -> None:
        self.credential_repo = credential_repo
        self.account_repo = account_repo
        self.exchange_repo = exchange_repo
        self.exchange_gateway = exchange_gateway
        self.cache = cache or in_memory_cache

    async def execute(self, payload: TradingCredentialCreateRequest) -> CredentialSaveResponseDTO:
        """Perform live exchange handshake and register/rotate account API credentials."""
        is_testnet = payload.environment.upper() == "TESTNET"

        # 1. Live handshake test
        if not self.exchange_gateway:
            raise ExchangeAuthError("Exchange gateway is required for credential handshake verification.")

        try:
            if hasattr(self.exchange_gateway, "reconfigure"):
                self.exchange_gateway.reconfigure(
                    api_key=payload.api_key,
                    secret_key=payload.secret_key,
                    testnet=is_testnet,
                )
            balance_func = getattr(self.exchange_gateway, "get_balance", None) or getattr(
                self.exchange_gateway, "fetch_balance", None
            )
            balance_data = await balance_func() if balance_func else {}
        except Exception as e:
            raise ExchangeAuthError(f"Exchange handshake authentication failed: {e}")


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
                if hasattr(self.exchange_repo, "session") and self.exchange_repo.session:
                    self.exchange_repo.session.add(ex)
                    await self.exchange_repo.session.commit()
                    await self.exchange_repo.session.refresh(ex)
            if ex:
                exchange_id = ex.id

        account_id = payload.account_id or 1
        if self.account_repo:
            if payload.account_id:
                acc = await self.account_repo.get(payload.account_id)
            else:
                acc = await self.account_repo.get_active_account(exchange_id)
            if not acc:
                acc = TradingAccount(
                    exchange_id=exchange_id,
                    name=f"Binance {payload.environment.upper()}",
                    account_type="FUTURES",
                    environment=payload.environment.upper(),
                    is_active=True,
                )
                if hasattr(self.account_repo, "session") and self.account_repo.session:
                    self.account_repo.session.add(acc)
                    await self.account_repo.session.commit()
                    await self.account_repo.session.refresh(acc)
            else:
                acc.environment = payload.environment.upper()
                acc.is_active = True
                if hasattr(self.account_repo, "session") and self.account_repo.session:
                    self.account_repo.session.add(acc)
                    await self.account_repo.session.commit()
            if acc:
                account_id = acc.id

        # 3. Store credentials (upsert)
        credential_id = 1
        if self.credential_repo:
            existing_cred = await self.credential_repo.get_active_credential(account_id)
            if not existing_cred:
                existing_cred = await self.credential_repo.get_by_account_id(account_id)

            if existing_cred:
                updated = await self.credential_repo.update(
                    existing_cred,
                    {
                        "api_key": payload.api_key,
                        "secret_key": payload.secret_key,
                        "is_active": True,
                    },
                )
                credential_id = updated.id
            else:
                cred = await self.credential_repo.create({
                    "account_id": account_id,
                    "key_name": f"Key_{payload.environment.upper()}",
                    "api_key": payload.api_key,
                    "secret_key": payload.secret_key,
                    "key_version": 1,
                    "is_active": True,
                })
                credential_id = cred.id


        if self.cache:
            await self.cache.invalidate("settings")
            await self.cache.invalidate("accounts")

        return CredentialSaveResponseDTO(
            success=True,
            account_id=account_id,
            credential_id=credential_id,
            wallet_balance_usdt=wallet_balance,
            environment=payload.environment.upper(),
        )
