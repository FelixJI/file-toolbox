"""发票解析器:XML/OFD/PDF/ZIP。"""

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError, parse_invoice

__all__ = ["parse_invoice", "UnsupportedFormatError"]
