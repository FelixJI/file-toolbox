"""共享 pytest fixtures:程序化生成虚构 OFD/PDF/ZIP fixture(避免提交二进制与隐私内容)。"""

import io
import os
import zipfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _disable_live_com_detect():
    """全局禁用 PDF Tab 构造时的实时 Office COM 检测。

    GUI 单元测试只校验控件状态与配置逻辑(各 test_*_gui.py 的 docstring 均声明
    "不触发真实 COM")。但 PDFGeneratorDialog.__init__ 会异步 Dispatch Word/WPS COM
    服务器,在无桌面/未装 Office 的测试环境触发 RPC 致命异常(0x800706ba/be),
    污染进程退出。置此环境变量让对话框跳过 Dispatch,仅用缓存/占位信息。
    """
    old = os.environ.get("FILE_TOOLBOX_NO_COM_DETECT")
    os.environ["FILE_TOOLBOX_NO_COM_DETECT"] = "1"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("FILE_TOOLBOX_NO_COM_DETECT", None)
        else:
            os.environ["FILE_TOOLBOX_NO_COM_DETECT"] = old

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


def _write_ofd(tmp_path: Path, name: str, ofd_xml: str, doc_xml: str, contents: dict) -> Path:
    """通用 OFD 打包器。contents: {zip内路径: xml 文本}。"""
    p = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("OFD.xml", ofd_xml)
        zf.writestr("Doc_0/Document.xml", doc_xml)
        for path, text in contents.items():
            zf.writestr(path, text)
    p.write_bytes(buf.getvalue())
    return p


@pytest.fixture
def ofd_sample(tmp_path) -> Path:
    """生成虚构 OFD(打包 XML),返回路径。"""
    return _write_ofd(
        tmp_path, "sample.ofd", OFD_XML, DOCUMENT_XML,
        {"Doc_0/Pages/Page_0/Content.xml": CONTENT_XML},
    )


# --- OFD 含明细行(Content.xml 带 Boundary/X/Y 坐标的 TextObject) ---
CONTENT_XML_WITH_ITEMS = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject Boundary="200 30 100 12"><ofd:TextCode X="200" Y="40">电子发票（增值税专用发票）</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 90 140 12"><ofd:TextCode X="50" Y="100">名称:测试销售方有限公司</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="300 90 140 12"><ofd:TextCode X="300" Y="100">名称:测试购买方有限公司</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 190 40 12"><ofd:TextCode X="50" Y="200">项目名称</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="190 190 60 12"><ofd:TextCode X="190" Y="200">规格型号</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="250 190 40 12"><ofd:TextCode X="250" Y="200">单位</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="290 190 40 12"><ofd:TextCode X="290" Y="200">数量</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="330 190 40 12"><ofd:TextCode X="330" Y="200">单价</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="380 190 40 12"><ofd:TextCode X="380" Y="200">金额</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="430 190 40 12"><ofd:TextCode X="430" Y="200">税率</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="470 190 40 12"><ofd:TextCode X="470" Y="200">税额</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 210 140 12"><ofd:TextCode X="50" Y="220">*交通运输设备*测试品甲</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="190 210 60 12"><ofd:TextCode X="190" Y="220">TEST-001</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="250 210 40 12"><ofd:TextCode X="250" Y="220">根</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="290 210 40 12"><ofd:TextCode X="290" Y="220">2</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="330 210 40 12"><ofd:TextCode X="330" Y="220">500</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="380 210 60 12"><ofd:TextCode X="380" Y="220">1000.00</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="430 210 40 12"><ofd:TextCode X="430" Y="220">13%</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="470 210 60 12"><ofd:TextCode X="470" Y="220">130.00</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 230 140 12"><ofd:TextCode X="50" Y="240">*交通运输设备*丙品</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="190 230 60 12"><ofd:TextCode X="190" Y="240">C-3</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="250 230 40 12"><ofd:TextCode X="250" Y="240">件</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="290 230 40 12"><ofd:TextCode X="290" Y="240">5</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="330 230 40 12"><ofd:TextCode X="330" Y="240">10</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="380 230 60 12"><ofd:TextCode X="380" Y="240">50.00</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="430 230 40 12"><ofd:TextCode X="430" Y="240">13%</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="470 230 60 12"><ofd:TextCode X="470" Y="240">6.50</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 250 40 12"><ofd:TextCode X="50" Y="260">合计</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="380 250 60 12"><ofd:TextCode X="380" Y="260">1050.00</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="470 250 60 12"><ofd:TextCode X="470" Y="260">136.50</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 270 40 12"><ofd:TextCode X="50" Y="280">价税合计(大写)</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="200 270 160 12"><ofd:TextCode X="200" Y="280">壹仟壹佰捌拾陆圆伍角整</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="50 290 40 12"><ofd:TextCode X="50" Y="300">备注:壹元优惠</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""


@pytest.fixture
def ofd_sample_with_items(tmp_path) -> Path:
    """OFD 含 3 行明细(第 3 行为续行验证)+ 大写金额 + 备注干扰项。"""
    return _write_ofd(
        tmp_path, "with_items.ofd", OFD_XML, DOCUMENT_XML,
        {"Doc_0/Pages/Page_0/Content.xml": CONTENT_XML_WITH_ITEMS},
    )


# --- OFD 键名变体 + 全角冒号(#2 #3 回归) ---
OFD_XML_VARIANT_KEYS = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:OFD xmlns:ofd="http://www.ofdspec.org/2016" Version="1.2" DocType="OFD">
<ofd:DocBody><ofd:DocRoot>Doc_0/Document.xml</ofd:DocRoot>
<ofd:DocInfo><ofd:CustomDatas>
<ofd:CustomData Name="发票号码">99990000000000000010</ofd:CustomData>
<ofd:CustomData Name="合计(元)">3000.00</ofd:CustomData>
<ofd:CustomData Name="税额合计">390.00</ofd:CustomData>
<ofd:CustomData Name="价税合计(大写)">3390.00</ofd:CustomData>
<ofd:CustomData Name="开票时间">2026-07-01 09:00:00</ofd:CustomData>
</ofd:CustomDatas></ofd:DocInfo></ofd:DocBody></ofd:OFD>
"""

CONTENT_XML_FULLWIDTH_COLON = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject Boundary="50 90 200 12"><ofd:TextCode X="50" Y="100">名称：全角销售方</ofd:TextCode></ofd:TextObject>
<ofd:TextObject Boundary="300 90 200 12"><ofd:TextCode X="300" Y="100">名称：全角购买方</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""


@pytest.fixture
def ofd_sample_variant_keys(tmp_path) -> Path:
    """OFD 用键名变体(合计(元)/税额合计/价税合计(大写)/开票时间)+ 全角冒号。"""
    return _write_ofd(
        tmp_path, "variant.ofd", OFD_XML_VARIANT_KEYS, DOCUMENT_XML,
        {"Doc_0/Pages/Page_0/Content.xml": CONTENT_XML_FULLWIDTH_COLON},
    )


# --- OFD 多页(#7):Document.xml 声明两页,Content 分两个文件 ---
DOCUMENT_XML_MULTIPAGE = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Document xmlns:ofd="http://www.ofdspec.org/2016">
<ofd:CommonData><ofd:PageArea><ofd:PhysicalBox>0 0 210 297</ofd:PhysicalBox></ofd:PageArea></ofd:CommonData>
<ofd:Pages>
<ofd:Page ID="1" BaseLoc="Pages/Page_0/Content.xml"/>
<ofd:Page ID="2" BaseLoc="Pages/Page_1/Content.xml"/>
</ofd:Pages></ofd:Document>
"""

CONTENT_XML_PAGE0 = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject Boundary="50 90 200 12"><ofd:TextCode X="50" Y="100">名称:多页销售方</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""

CONTENT_XML_PAGE1 = """<?xml version="1.0" encoding="UTF-8"?>
<ofd:Page xmlns:ofd="http://www.ofdspec.org/2016"><ofd:Content><ofd:Layer Type="Body">
<ofd:TextObject Boundary="50 90 200 12"><ofd:TextCode X="50" Y="100">名称:多页购买方</ofd:TextCode></ofd:TextObject>
</ofd:Layer></ofd:Content></ofd:Page>
"""


@pytest.fixture
def ofd_sample_multipage(tmp_path) -> Path:
    """OFD 两页:Document.xml 声明 Page_0/Page_1,买卖方名称分在不同页。"""
    return _write_ofd(
        tmp_path, "multipage.ofd", OFD_XML, DOCUMENT_XML_MULTIPAGE,
        {
            "Doc_0/Pages/Page_0/Content.xml": CONTENT_XML_PAGE0,
            "Doc_0/Pages/Page_1/Content.xml": CONTENT_XML_PAGE1,
        },
    )


# --- OFD 错误路径:缺 OFD.xml / 非 ZIP ---
@pytest.fixture
def ofd_sample_missing_ofdxml(tmp_path) -> Path:
    """OFD 缺 OFD.xml(只有 Content),应报 UnsupportedFormatError。"""
    p = tmp_path / "no_ofdxml.ofd"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Doc_0/Pages/Page_0/Content.xml", CONTENT_XML)
    p.write_bytes(buf.getvalue())
    return p


@pytest.fixture
def ofd_sample_badzip(tmp_path) -> Path:
    """非 ZIP 的伪 OFD,应报 UnsupportedFormatError。"""
    p = tmp_path / "bad.ofd"
    p.write_bytes(b"not a zip file content")
    return p


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


# --- 虚构 ZIP fixtures(模拟税务局完整下载:含 pdf+ofd+嵌套 zip) ---
_XML_FIXTURE = (
    Path(__file__).parent / "fixtures" / "invoice" / "sample_einvoice.xml"
)


@pytest.fixture
def zip_with_xml(tmp_path) -> Path:
    """完整 ZIP:含 pdf+ofd 占位 + 嵌套 zip(内含 xml),模拟完整下载。应优先采信 xml。"""
    xml_src = _XML_FIXTURE.read_bytes()
    inner_buf = io.BytesIO()
    with zipfile.ZipFile(inner_buf, "w") as zf:
        zf.writestr("dzfp_99990000000000000001.xml", xml_src)
    inner_bytes = inner_buf.getvalue()

    outer_path = tmp_path / "full_invoice.zip"
    with zipfile.ZipFile(outer_path, "w") as zf:
        zf.writestr("some.pdf", b"%PDF-1.4 fake")
        zf.writestr("some.ofd", b"PK fake")
        zf.writestr("99990000000000000001.zip", inner_bytes)
    return outer_path


@pytest.fixture
def zip_xml_only(tmp_path) -> Path:
    """ZIP 内直接含 XML(无嵌套)。"""
    xml_src = _XML_FIXTURE.read_bytes()
    p = tmp_path / "xml_only.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("dzfp_99990000000000000001.xml", xml_src)
    return p


@pytest.fixture
def zip_ofd_only(tmp_path, ofd_sample) -> Path:
    """ZIP 内只含 OFD(无 xml),应回退到 OFD。"""
    ofd_bytes = ofd_sample.read_bytes()
    p = tmp_path / "ofd_only.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("some.ofd", ofd_bytes)
    return p


# --- 虚构 PDF fixture:模拟真实发票形态(拆字表头+长单价+购/销标签) ---
@pytest.fixture
def pdf_sample_realistic(tmp_path) -> Path:
    """模拟真实发票版式的 PDF。

    关键特征(对应 pdf_parser 重构解决的根因):
    - 拆字表头:'单'+'位'/'数'+'量' 等独立 word(真实发票形态,非连写)
    - 长单价: 96.2001361061947(验证 word 中心判列,不误归数量)
    - 购/销竖排标签 + 名称分区(验证按标签 x 定位买卖方)
    - 跨行价税合计(大写标签行与金额行分离)
    - 商品名跨 2 行(名称主体 + 续行'块(L135)')
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    pdf_path = tmp_path / "realistic_invoice.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    c.setFont("STSong-Light", 10)
    _, h = A4

    # 标题 + 号码
    c.drawString(200, h - 40, "电子发票（增值税专用发票）")
    c.drawString(400, h - 40, "发票号码：")
    c.drawString(470, h - 40, "99990000000000000099")
    c.drawString(400, h - 55, "开票日期：")
    c.drawString(470, h - 55, "2026年07月09日")

    # 购/销竖排标签(真实发票左侧"购买方"、右侧"销售方")
    left_x, right_x = 16, 300
    for i, ch in enumerate("购买方信息"):
        c.drawString(left_x, h - 80 - i * 12, ch)
    for i, ch in enumerate("销售方信息"):
        c.drawString(right_x, h - 80 - i * 12, ch)
    # 名称(左=购买方,右=销售方)——与真实发票一致
    c.drawString(30, h - 84, "名称:徐州中车轨道装备有限公司")
    c.drawString(315, h - 84, "名称:中车南京浦镇车辆有限公司")
    # 税号(带"统一社会信用代码/"前缀,验证裁剪)
    c.drawString(30, h - 110, "统一社会信用代码/纳税人识别号:91BUYERTAXID00000Z")
    c.drawString(315, h - 110, "统一社会信用代码/纳税人识别号:91SELLERTAXID00000X")

    # 拆字表头(真实发票形态:单字独立 word)
    hy = h - 140
    c.drawString(47, hy, "项目名称")
    c.drawString(117, hy, "规格型号")
    c.drawString(189, hy, "单"); c.drawString(207, hy, "位")
    c.drawString(263, hy, "数"); c.drawString(281, hy, "量")
    c.drawString(334, hy, "单"); c.drawString(352, hy, "价")
    c.drawString(408, hy, "金"); c.drawString(426, hy, "额")
    c.drawString(445, hy, "税率/征收率")
    c.drawString(549, hy, "税"); c.drawString(567, hy, "额")

    # 明细行 1(跨 2 行:名称主体 + 续行)
    y1 = hy - 20
    c.drawString(12, y1, "*交通运输设备*补强")
    c.drawString(117, y1, "P000002356623")
    c.drawString(198, y1, "件")
    c.drawString(278, y1, "26")
    c.drawString(290, y1, "96.2001361061947")  # 长单价,x0 紧贴数量
    c.drawString(403, y1, "2501.20")
    c.drawString(463, y1, "13%")
    c.drawString(555, y1, "325.16")
    # 续行:仅名称列
    y2 = y1 - 12
    c.drawString(12, y2, "块（L")
    c.drawString(39, y2, "135）")

    # 合计行(两字分离 '合'+'计' + ¥ 符号)
    y3 = y2 - 16
    c.drawString(69, y3, "合")
    c.drawString(114, y3, "计")
    c.drawString(392, y3, "¥2501.20")
    c.drawString(543, y3, "¥325.16")

    # 价税合计行(大写标签行 与 金额行 跨行)
    y4 = y3 - 16
    c.drawString(55, y4, "价税合计(大写)")
    c.drawString(182, y4, "贰仟捌佰贰拾陆圆叁角陆分")
    c.drawString(407, y4, "(小写)")
    # 金额在相邻 y 行(真实发票如此)
    y5 = y4 - 3
    c.drawString(443, y5, "¥2826.36")

    c.save()
    return pdf_path
