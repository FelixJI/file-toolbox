"""PDF 排序核心:按文字层提取每页排序键,重排页面写出新 PDF。

纯 pypdf 实现,跨平台、不依赖 Office/WPS COM。输入必须含文字层
(电子版或已 OCR 的扫描件);纯图像扫描页提取不到文字,会按未匹配策略处理。
输出只按新页序复制页面,不保留原文件的书签/目录;源文件永不修改,
输出已存在时自动加序号,绝不覆盖。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from file_toolbox.common.history import JsonHistoryStore
from file_toolbox.common.loggable import LoggableMixin
from file_toolbox.core.pdf_sort.constants import (
    SORTED_MARKER,
    SUPPORTED_SUFFIXES,
)
from file_toolbox.core.pdf_sort.keys import compile_pattern, compute_order, extract_key
from file_toolbox.core.pdf_sort.types import (
    FailedFile,
    FilePlan,
    PagePlan,
    SortedFile,
    SortOptions,
    SortResult,
)

ProgressCallback = Callable[[int, int, str], None]
CancelCheck = Callable[[], bool]


class PdfSortService(LoggableMixin):
    """PDF 排序服务:plan_pages 预览、sort 执行。"""

    def __init__(self, history_store: JsonHistoryStore | None = None) -> None:
        """初始化服务。

        Args:
            history_store: 历史存储;传入则 sort 成功写出至少一个输出后记录一条
                pdf_sort 历史。None 表示不记录(默认)。
        """
        self._history_store = history_store

    # ==================== 预览 ====================

    def plan_pages(
        self,
        files: list[Path],
        options: SortOptions,
        progress_callback: ProgressCallback | None = None,
    ) -> tuple[list[FilePlan], list[FailedFile]]:
        """读取每个 PDF 的文字层,给出每页排序键与新页序(不写任何文件)。

        Args:
            files: 源 PDF 文件列表。
            options: 排序选项(pattern 非法时抛 ValueError)。
            progress_callback: (current, total, message) 进度回调。

        Returns:
            (计划列表, 读取失败列表)。order 为 None 的计划不会进入输出。
        """
        regex = compile_pattern(options.pattern)
        plans: list[FilePlan] = []
        failed: list[FailedFile] = []
        total = len(files)
        for idx, path in enumerate(files, start=1):
            if progress_callback is not None:
                progress_callback(idx, total, f"分析 {path.name}")
            try:
                pages, order, note = self._plan_one(path, regex, options)
            except ValueError as e:
                failed.append(FailedFile(path.name, str(e)))
                continue
            except Exception as e:
                failed.append(FailedFile(path.name, f"无法读取: {e}"))
                continue
            plans.append(FilePlan(file=path.name, pages=pages, order=order, note=note))
        return plans, failed

    # ==================== 执行 ====================

    def sort(
        self,
        files: list[Path],
        options: SortOptions,
        output: Path | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> SortResult:
        """按排序键重排每个 PDF 的页面并写出新文件。

        Args:
            files: 源 PDF 文件列表。
            options: 排序选项(pattern 非法时抛 ValueError)。
            output: 单文件时为输出文件路径(后缀强制 .pdf);
                多文件时为输出目录(在各自名称后加"排序"标记);None 写在源文件同目录。
            progress_callback: (current, total, message) 进度回调(按文件粒度)。
            cancel_check: 返回 True 时在下一个文件前取消(不写输出)。

        Returns:
            SortResult:success = 至少一个文件被处理(允许部分文件失败)。
        """
        regex = compile_pattern(options.pattern)
        if output is not None and len(files) > 1 and output.suffix.lower() == ".pdf":
            raise ValueError("多个文件时不支持指定单一输出文件,请指定输出目录或不使用 --output")
        sorted_files: list[SortedFile] = []
        failed: list[FailedFile] = []
        cancelled = False
        total = len(files)

        for idx, path in enumerate(files, start=1):
            if cancel_check is not None and cancel_check():
                cancelled = True
                self.logger.info("PDF 排序被取消,已处理 %d/%d 个文件", idx - 1, total)
                break
            if progress_callback is not None:
                progress_callback(idx, total, f"排序 {path.name}")
            try:
                pages, order, note = self._plan_one(path, regex, options)
            except ValueError as e:
                failed.append(FailedFile(path.name, str(e)))
                self.logger.warning("源文件读取失败,跳过: %s (%s)", path, e)
                continue
            except Exception as e:
                failed.append(FailedFile(path.name, f"无法读取: {e}"))
                self.logger.warning("源文件读取失败,跳过: %s (%s)", path, e)
                continue
            if order is None:
                failed.append(FailedFile(path.name, note))
                continue
            if order == list(range(len(order))):
                sorted_files.append(SortedFile(path.name, None, pages, "顺序未变,未写出输出"))
                continue
            out_path = self._resolve_output_path(self._target_output(path, output, len(files)))
            try:
                self._write_sorted(path, order, out_path)
            except Exception as e:
                self.logger.error("输出 PDF 写出失败: %s (%s)", out_path, e)
                failed.append(FailedFile(path.name, f"写出失败: {e}"))
                continue
            sorted_files.append(SortedFile(path.name, out_path, pages))

        if cancelled:
            return SortResult(cancelled=True, failed=failed)
        if not sorted_files:
            reason = "全部源文件失败" if failed else "没有可排序的 PDF"
            return SortResult(failed=failed, error_message=reason)

        self.logger.info(
            "PDF 排序完成: %d 个文件, 写出 %d 个输出",
            total,
            sum(1 for f in sorted_files if f.output is not None),
        )
        result = SortResult(sorted_files=sorted_files, failed=failed)
        self._record_history(result, total, options)
        return result

    # ==================== 内部实现 ====================

    def _plan_one(
        self, path: Path, regex: re.Pattern[str], options: SortOptions
    ) -> tuple[list[PagePlan], list[int] | None, str]:
        """读取一个 PDF,返回 (每页计划, 新页序或 None, 原因说明)。"""
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(
                f"不支持的格式 {path.suffix or '(无后缀)'},仅支持 {'/'.join(SUPPORTED_SUFFIXES)}"
            )
        with path.open("rb") as stream:
            reader = PdfReader(stream)
            if reader.is_encrypted:
                raise ValueError("加密 PDF 暂不支持,请先解除密码后重试")
            keys: list[str | None] = []
            for page in reader.pages:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""  # 单页提取失败按未匹配处理,不拖垮整个文件
                keys.append(extract_key(text, regex))

        if not any(key is not None for key in keys):
            note = "没有任何页面匹配到排序文字(可能无文字层或格式不符)"
            pages = [PagePlan(p, "", False) for p, key in enumerate(keys)]
            return pages, None, note

        order = compute_order(keys, options.order, options.unmatched)
        if order is None:
            n = sum(1 for key in keys if key is None)
            note = f"{n} 页未匹配到排序文字(--unmatched fail,未排序)"
            pages = [PagePlan(p, key or "", key is not None) for p, key in enumerate(keys)]
            return pages, None, note

        position = {orig: pos for pos, orig in enumerate(order)}
        pages = [PagePlan(p, key or "", key is not None, position[p]) for p, key in enumerate(keys)]
        return pages, order, ""

    def _target_output(self, path: Path, output: Path | None, file_count: int) -> Path:
        """单文件:output 为输出文件(缺省 主名_排序.pdf);
        多文件:output 为输出目录(缺省源文件目录)。后缀统一 .pdf。"""
        if file_count == 1:
            target = (
                output if output is not None else path.parent / f"{path.stem}{SORTED_MARKER}.pdf"
            )
            if target.suffix.lower() != ".pdf":
                return target.with_suffix(".pdf")
            return target
        out_dir = output if output is not None else path.parent
        return out_dir / f"{path.stem}{SORTED_MARKER}.pdf"

    def _resolve_output_path(self, output: Path) -> Path:
        """输出已存在时自动加序号,绝不覆盖已有文件(与 pdf/excel-merge 输出策略一致)。"""
        if not output.exists():
            return output
        counter = 1
        while True:
            candidate = output.with_name(f"{output.stem}_{counter}{output.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _write_sorted(self, path: Path, order: list[int], output: Path) -> None:
        """按新页序把源 PDF 的页面复制进新文件(不保留原书签/目录)。"""
        writer = PdfWriter()
        try:
            with path.open("rb") as stream:
                reader = PdfReader(stream)
                if reader.is_encrypted:
                    raise ValueError("加密 PDF 暂不支持,请先解除密码后重试")
                writer.append(reader, pages=list(order), import_outline=False)
            output.parent.mkdir(parents=True, exist_ok=True)
            writer.write(output)
        finally:
            writer.close()

    def _record_history(self, result: SortResult, file_count: int, options: SortOptions) -> None:
        """记录 pdf_sort 历史(若注入了 history_store 且至少写出一个输出)。"""
        if self._history_store is None or result.written_count == 0:
            return
        self._history_store.add_record(
            "pdf_sort",
            {
                "file_count": file_count,
                "page_count": sum(len(f.pages) for f in result.sorted_files),
                "unmatched_count": sum(
                    1 for f in result.sorted_files for p in f.pages if not p.matched
                ),
                "order": options.order,
                "pattern": options.pattern,
                "outputs": [str(f.output) for f in result.sorted_files if f.output],
                "success": True,
            },
        )
