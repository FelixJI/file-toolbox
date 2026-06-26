"""共享 pytest fixtures:程序化生成虚构 OFD/PDF/ZIP fixture(避免提交二进制与隐私内容)。"""

import io
import zipfile
from pathlib import Path

import pytest

# --- 虚构 OFD 内容(XML 明文,均为占位数据) ---
OFD_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016" Version="1.2" DocType="OFD">
<ofd:DocBody><ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot>
<ofd:DocInfo><ofd:DocID>testdocid</ofd:DocID>
<ofd:CreationDate>2026-05-19</ofd:CreationDate>
<ofd:CustomDatas>
<ofd:CustomData Name="发票号码">99990000000000000002</ofd:CustomData>
<ofd:CustomData Name="销售方纳税人识别号">91SELLERTAXID00000X</ofd:CustomData>
<ofd:CustomData Name="购买方纳税人识别号">91BUYERTAXID00000Y</ofd:CustomData>
<ofd:CustomData Name="合计金额">2000.00</ofd:CustomData>
<ofd:CustomData Name="合计税额">260.00</ofd:CustomData>
<ofd:CustomData Name="开票日期">2026-05-19 10:00:00</ofd:CustomData>
</ofd:CustomDatas></ofd:DocInfo></ofd:DocBody></ofd:OFD>
"""

DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">
<ofd:CommonData><ofd:PageArea><ofd:PhysicalBox>0 0 210 297</ofd:PhysicalBox></ofd:PageArea></ofd:CommonData>
<ofd:Pages><ofd:Page ID="1" BaseLoc="Pages/Page_0/Content.xml"/></ofd:Pages></ofd:Document>
"""

CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject><ofd:TextCode>电子发票（增值税专用发票）</ofd:TextCode></ofd:TextObject>
<ofd:TextObject><ofd:TextCode>名称:测试销售方有限公司</ofd:TextCode></ofd:TextObject>
<ofd:TextObject><ofd:TextCode>名称:测试购买方有限公司</ofd:TextCode></ofd:TextObject>
<ofd:TextObject><ofd:TextCode>贰仟贰佰陆拾圆整</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""


@pytest.fixture
def ofd_sample(tmp_path) -> Path:
    """生成虚构 OFD(打包 XML),返回路径。"""
    ofd_path = tmp_path / "sample.ofd"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("OFD.xml", OFD_XML)
        zf.writestr("Doc_0/Document.xml", DOCUMENT_XML)
        zf.writestr("Doc_0/Pages/Page_0/Content.xml", CONTENT_XML)
    ofd_path.write_bytes(buf.getvalue())
    return ofd_path
