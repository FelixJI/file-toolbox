"""batch_generate 取消逻辑测试。

mock generate_pdf 避免真实转换,只验证 cancel_check 中断行为。
"""

from pathlib import Path

import pytest

from file_toolbox.core.batch_pdf.service import PDFGeneratorService


@pytest.fixture
def svc(monkeypatch):
    """构造 service,mock 掉所有转换器,generate_pdf 直接成功。"""
    s = PDFGeneratorService()
    monkeypatch.setattr(s, "generate_pdf", lambda src, out, cfg: (True, ""))
    monkeypatch.setattr(s, "merge_pdfs", lambda pdfs, out, mode: (True, ""))
    return s


def test_cancel_check_stops_after_first_file(svc):
    """cancel_check 在第二个文件前返回 True → 只处理第一个。"""
    files = [Path(f"a{i}.docx") for i in range(3)]
    config = {"output_mode": "separate", "same_as_source": True}

    call_count = {"n": 0}

    def cancel_check():
        call_count["n"] += 1
        return call_count["n"] > 1  # 第二次检查时取消

    results = svc.batch_generate(files, config, cancel_check=cancel_check)
    # 第一个文件处理完后,循环头检查取消 → break,只产出 1 个结果
    assert len(results) == 1
    assert results[0]["success"] is True


def test_no_cancel_check_processes_all(svc):
    """不传 cancel_check → 全部处理(向后兼容)。"""
    files = [Path(f"a{i}.docx") for i in range(3)]
    config = {"output_mode": "separate", "same_as_source": True}

    results = svc.batch_generate(files, config)
    assert len(results) == 3
    assert all(r["success"] for r in results)


def test_cancel_check_false_processes_all(svc):
    """cancel_check 恒返回 False → 全部处理。"""
    files = [Path(f"a{i}.docx") for i in range(3)]
    config = {"output_mode": "separate", "same_as_source": True}

    results = svc.batch_generate(files, config, cancel_check=lambda: False)
    assert len(results) == 3
