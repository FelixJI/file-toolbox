from file_toolbox.core.invoice.parsers.zip_parser import _safe_extract, parse_zip


def test_zip_prefers_xml_when_nested(zip_with_xml):
    """完整 ZIP:含 pdf+ofd+嵌套 zip(内 xml),应优先采信 xml。"""
    inv = parse_zip(zip_with_xml, source_file="full.zip")
    assert inv.invoice_number == "99990000000000000001"
    assert inv.parse_method == "xml"  # 优先级 xml > ofd > pdf
    assert inv.seller_name == "测试销售方有限公司"


def test_zip_xml_direct(zip_xml_only):
    """ZIP 直接含 XML。"""
    inv = parse_zip(zip_xml_only, source_file="xml_only.zip")
    assert inv.invoice_number == "99990000000000000001"
    assert inv.parse_method == "xml"


def test_zip_fallback_to_ofd(zip_ofd_only):
    """ZIP 只含 OFD,回退到 OFD。"""
    inv = parse_zip(zip_ofd_only, source_file="ofd_only.zip")
    assert inv.invoice_number == "99990000000000000002"
    assert inv.parse_method == "ofd"


def test_safe_extract_blocks_path_traversal(tmp_path):
    """Zip Slip 防护:含 ../../ 路径的恶意条目不得写到目标目录之外。"""
    import zipfile

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        # 正常条目 + 一个试图逃逸的条目
        zf.writestr("ok.xml", b"<x/>")
        zf.writestr("../escape.txt", b"PWNED")
        zf.writestr("sub/../../escape2.txt", b"PWNED2")

    dest = tmp_path / "dest"
    dest.mkdir()
    with zipfile.ZipFile(evil, "r") as zf:
        _safe_extract(zf, dest)

    # 正常条目解压成功
    assert (dest / "ok.xml").exists()
    # 逃逸条目未写到 dest 之外(被跳过或安全重定位),且未写到父目录
    assert not (tmp_path / "escape.txt").exists()
    assert not (tmp_path / "escape2.txt").exists()
