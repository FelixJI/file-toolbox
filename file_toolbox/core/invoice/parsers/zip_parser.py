"""ZIP 发票解析:解压后优先级 xml > ofd > pdf,递归处理嵌套 zip。

临时文件用 TemporaryDirectory,解析完自动清理,不残留隐私内容。
解压用逐条校验路径的 _safe_extract,防 Zip Slip 路径穿越攻击。
"""

import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from file_toolbox.core.invoice.parsers.base import UnsupportedFormatError

if TYPE_CHECKING:
    from file_toolbox.core.invoice.types import Invoice


def _find_files_by_ext(root: Path, ext: str) -> list[Path]:
    """在 root 下递归找指定扩展名文件(包括已解嵌套的子目录)。"""
    return sorted(root.rglob(f"*{ext}"))


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """逐条解压 zip,跳过会逃逸出 dest 的条目(Zip Slip 防护)。

    不用 extractall(它不校验成员路径)。每个成员的解析后路径必须落在 dest 内。
    """
    dest = dest.resolve()
    for info in zf.infolist():
        if info.is_dir():
            continue
        # 拼接并规范化,校验是否仍在 dest 内
        target = (dest / info.filename).resolve()
        try:
            target.relative_to(dest)
        except ValueError:
            # 路径逃逸,跳过该条目
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(zf.read(info.filename))


def parse_zip(path: Path, source_file: str = "") -> "Invoice":
    """解析 ZIP 发票。优先级:xml > ofd > pdf,含嵌套 zip 递归解压。

    返回解析得到的 Invoice。
    """
    from file_toolbox.core.invoice.parsers.ofd_parser import parse_ofd
    from file_toolbox.core.invoice.parsers.pdf_parser import parse_pdf
    from file_toolbox.core.invoice.parsers.xml_parser import parse_xml

    path = Path(path)
    if not path.exists():
        raise UnsupportedFormatError(f"文件不存在: {path}")

    # 解压到临时目录,自动清理
    with tempfile.TemporaryDirectory(prefix="invoice_") as tmp:
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(path, "r") as zf:
                _safe_extract(zf, tmp_path)
        except zipfile.BadZipFile as e:
            raise UnsupportedFormatError(f"ZIP 解压失败: {e}") from e

        # 解嵌套 zip:把内层 zip 也解压到同级 _extracted 目录(最多处理一层)
        # (税务局标准下载最多两层;更深层忽略)
        for inner_zip in _find_files_by_ext(tmp_path, ".zip"):
            try:
                with zipfile.ZipFile(inner_zip, "r") as izf:
                    _safe_extract(izf, inner_zip.parent / (inner_zip.stem + "_extracted"))
            except (zipfile.BadZipFile, OSError):
                continue

        src_name = source_file or path.name

        # 优先级 xml > ofd > pdf;逐个尝试,失败(UnsupportedFormatError)则下一个
        for xml in _find_files_by_ext(tmp_path, ".xml"):
            try:
                return parse_xml(xml, source_file=src_name)
            except UnsupportedFormatError:
                continue

        for ofd in _find_files_by_ext(tmp_path, ".ofd"):
            try:
                return parse_ofd(ofd, source_file=src_name)
            except UnsupportedFormatError:
                continue

        for pdf in _find_files_by_ext(tmp_path, ".pdf"):
            try:
                return parse_pdf(pdf, source_file=src_name)
            except UnsupportedFormatError:
                continue

    raise UnsupportedFormatError(f"ZIP 内未找到可识别的发票文件: {path.name}")
