"""Use case for exporting closed trade history as standardized CSV."""

import csv
import io
from datetime import date, datetime, time
from typing import Optional

from src.domain.exceptions.system import InvalidDateRangeError
from src.domain.ports.repositories import ITradeRepository


class ExportTradesCsvUseCase:
    """Use case to generate a standardized RFC 4180 CSV export of closed trade history."""

    def __init__(self, trade_repo: ITradeRepository) -> None:
        self.trade_repo = trade_repo

    async def execute(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> str:
        """Generate a standardized RFC 4180 CSV export of closed trade history."""
        if start_date and end_date and start_date > end_date:
            raise InvalidDateRangeError(
                f"Invalid date range: start_date ({start_date}) cannot be after end_date ({end_date})."
            )

        start_dt: Optional[datetime] = (
            datetime.combine(start_date, time.min) if start_date else None
        )
        end_dt: Optional[datetime] = (
            datetime.combine(end_date, time.max) if end_date else None
        )

        trades = await self.trade_repo.get_closed_trades_for_report(
            start_date=start_dt,
            end_date=end_dt,
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header Row
        writer.writerow([
            "Trade ID",
            "Symbol",
            "Side",
            "Entry Price",
            "Exit Price",
            "Position Size",
            "Leverage",
            "Gross PnL (USDT)",
            "Commission (USDT)",
            "Net PnL (USDT)",
            "ROI %",
            "Result",
            "Close Reason",
            "Opened At",
            "Closed At",
        ])

        for t in trades:
            sym_name = t.instrument.symbol if t.instrument else "UNKNOWN"
            entry_price_val = float(t.avg_entry_price or t.entry_price or 0.0)

            # Compute approximate exit price if summary exists
            exit_price_val = entry_price_val
            gross_pnl_val = 0.0
            comm_val = 0.0
            net_pnl_val = 0.0
            roi_val = 0.0
            result_str = "N/A"
            close_reason_str = "N/A"

            if t.summary:
                gross_pnl_val = float(t.summary.gross_pnl or 0.0)
                comm_val = float(t.summary.commission or 0.0)
                net_pnl_val = float(t.summary.net_pnl or 0.0)
                roi_val = float(t.summary.roi or 0.0)
                result_str = str(t.summary.result or "N/A")
                close_reason_str = str(t.summary.close_reason or "N/A")

                pos_size_val = float(t.position_size or 0.0)
                if pos_size_val > 0:
                    if t.side.upper() == "BUY":
                        exit_price_val = entry_price_val + (gross_pnl_val / pos_size_val)
                    else:
                        exit_price_val = entry_price_val - (gross_pnl_val / pos_size_val)

            opened_str = t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else "N/A"
            closed_str = (
                t.closed_at.strftime("%Y-%m-%d %H:%M:%S")
                if t.closed_at
                else (t.updated_at.strftime("%Y-%m-%d %H:%M:%S") if t.updated_at else "N/A")
            )

            writer.writerow([
                t.id,
                sym_name,
                t.side,
                f"{entry_price_val:.4f}",
                f"{exit_price_val:.4f}",
                f"{float(t.position_size or 0.0):.4f}",
                f"{t.leverage}x",
                f"{gross_pnl_val:.2f}",
                f"{comm_val:.2f}",
                f"{net_pnl_val:.2f}",
                f"{roi_val:.2f}%",
                result_str,
                close_reason_str,
                opened_str,
                closed_str,
            ])

        return output.getvalue()
