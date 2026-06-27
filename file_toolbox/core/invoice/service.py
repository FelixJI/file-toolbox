"""InvoiceService:编排 解析 -> 去重 -> 导出。"""

from pathlib import Path

from file_toolbox.core.invoice.dedupe import (
    DEDUPE,
    KEEP_ALL,
    MARK,
    dedupe_invoices,
)
from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError, parse_invoice
from file_toolbox.core.invoice.types import FailedFile, Invoice, ParseResult


class InvoiceService:
    """发票识别编排服务:解析文件 -> 去重 -> 导出。"""

    def __init__(self):
        pass

    def parse_files(
        self,
        files: list[Path],
        dedupe_strategy: str = KEEP_ALL,
    ) -> ParseResult:
        """解析文件列表,应用去重,返回 ParseResult。

        单个文件解析失败进 failed,不中断整体。
        """
        invoices: list[Invoice] = []
        failed: list[FailedFile] = []
        for fp in files:
            try:
                inv = parse_invoice(Path(fp), source_file=Path(fp).name)
                invoices.append(inv)
            except UnsupportedFormatError as e:
                failed.append(FailedFile(file=Path(fp).name, reason=str(e)))
            except Exception as e:  # noqa: BLE001 - 解析意外错误也记为失败
                failed.append(FailedFile(file=Path(fp).name, reason=f"{type(e).__name__}: {e}"))

        kept, dups = dedupe_invoices(invoices, dedupe_strategy)
        return ParseResult(invoices=kept, duplicates=dups, failed=failed)

    def export(
        self,
        result: ParseResult,
        output_path: Path,
        fmt: str = "excel",
        json_path: Path | None = None,
        dedupe_strategy: str = KEEP_ALL,
    ) -> list[Path]:
        """导出。fmt: excel | json | both。返回生成的文件列表。"""
        from file_toolbox.core.invoice.exporters.excel_exporter import export_excel
        from file_toolbox.core.invoice.exporters.json_exporter import export_json

        written: list[Path] = []
        if fmt in ("excel", "both"):
            written.append(export_excel(result.invoices, output_path))
        if fmt in ("json", "both"):
            jp = json_path or output_path.with_suffix(".json")
            written.append(
                export_json(result.invoices, jp, dedupe_strategy, result.failed)
            )
        return written

    @staticmethod
    def supported_dedupe_strategies() -> list[str]:
        return [KEEP_ALL, DEDUPE, MARK]

    @staticmethod
    def supported_formats() -> list[str]:
        """支持导出的格式。"""
        return ["excel", "json", "both"]
