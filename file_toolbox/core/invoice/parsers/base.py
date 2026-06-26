"""解析器路由与异常。"""

from pathlib import Path


class UnsupportedFormatError(Exception):
    """文件格式不支持或解析失败。"""


def parse_invoice(path: Path, source_file: str = "") -> object:
    """按扩展名路由到具体解析器,返回 Invoice。"""
    path = Path(path)
    suffix = path.suffix.lower()
    if not source_file:
        source_file = path.name

    if suffix == ".zip":
        from file_toolbox.core.invoice.parsers.zip_parser import parse_zip

        return parse_zip(path, source_file)
    if suffix == ".xml":
        from file_toolbox.core.invoice.parsers.xml_parser import parse_xml

        return parse_xml(path, source_file)
    if suffix == ".ofd":
        from file_toolbox.core.invoice.parsers.ofd_parser import parse_ofd

        return parse_ofd(path, source_file)
    if suffix == ".pdf":
        from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf

        return parse_pdf(path, source_file)
    raise UnsupportedFormatError(f"不支持的格式: {suffix}")
