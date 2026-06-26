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


# --- 虚构版式发票 PDF(reportlab 生成,模拟真实发票的绝对坐标文本排布) ---
@pytest.fixture
def pdf_sample(tmp_path) -> Path:
    """生成虚构版式发票 PDF,返回路径。注册 CJK 字体确保中文为真实文本(非 .notdef)。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    pdf_path = tmp_path / "sample_invoice.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont("STSong-Light", 10)
    _, h = A4
    y = h - 50
    c.drawString(200, y, "电子发票（增值税专用发票）")
    y -= 20
    c.drawString(300, y, "发票号码：")
    c.drawString(370, y, "99990000000000000003")
    c.drawString(300, y - 15, "开票日期：")
    c.drawString(370, y - 15, "2026年05月19日")
    y -= 50
    # 买卖方区
    c.drawString(50, y, "名称:测试销售方有限公司")
    c.drawString(300, y, "名称:测试购买方有限公司")
    y -= 15
    c.drawString(50, y, "统一社会信息代码/纳税人识别号:91SELLERTAXID00000X")
    c.drawString(300, y, "统一社会信息代码/纳税人识别号:91BUYERTAXID00000Y")
    y -= 40
    # 表头(8 列)
    c.drawString(50, y, "项目名称")
    c.drawString(200, y, "规格型号")
    c.drawString(260, y, "单位")
    c.drawString(300, y, "数量")
    c.drawString(340, y, "单价")
    c.drawString(390, y, "金额")
    c.drawString(440, y, "税率")
    c.drawString(480, y, "税额")
    y -= 20
    # 明细行 1(有规格)
    c.drawString(50, y, "*交通运输设备*测试品甲")
    c.drawString(200, y, "TEST-001")
    c.drawString(260, y, "根")
    c.drawString(300, y, "2")
    c.drawString(340, y, "500")
    c.drawString(390, y, "1000.00")
    c.drawString(440, y, "13%")
    c.drawString(480, y, "130.00")
    y -= 20
    # 明细行 2(规格为空 —— 验证空单元格不错位)
    c.drawString(50, y, "*交通运输设备*无规格品")
    c.drawString(260, y, "个")
    c.drawString(300, y, "3")
    c.drawString(340, y, "100")
    c.drawString(390, y, "300.00")
    c.drawString(440, y, "13%")
    c.drawString(480, y, "39.00")
    y -= 20
    # 明细行 3(凑够 3 行以触发列对齐 min_words_vertical=3)
    c.drawString(50, y, "*交通运输设备*丙品")
    c.drawString(200, y, "C-3")
    c.drawString(260, y, "件")
    c.drawString(300, y, "5")
    c.drawString(340, y, "10")
    c.drawString(390, y, "50.00")
    c.drawString(440, y, "13%")
    c.drawString(480, y, "6.50")
    y -= 20
    # 合计行(1000+300+50=1350 ; 130+39+6.5=175.5)
    c.drawString(50, y, "合计")
    c.drawString(390, y, "1350.00")
    c.drawString(480, y, "175.50")
    y -= 20
    c.drawString(50, y, "价税合计(大写)")
    c.drawString(200, y, "壹仟伍佰贰拾伍圆伍角整")
    c.drawString(390, y, "1525.50")
    c.save()
    return pdf_path
