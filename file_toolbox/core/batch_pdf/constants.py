"""
PDF生成器常量定义

包含纸张尺寸、方向、PDF类型等常量
"""

# 支持的文件类型
SUPPORTED_FORMATS = {
    "word": [".doc", ".docx"],
    "excel": [".xls", ".xlsx"],
    "powerpoint": [".ppt", ".pptx"],
    "image": [".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".gif"],
    "pdf": [".pdf"],
}

# 所有支持的扩展名
ALL_SUPPORTED_EXTENSIONS = [ext for exts in SUPPORTED_FORMATS.values() for ext in exts]

# 纸张尺寸定义 (宽, 高) 单位: mm
PAPER_SIZES = {
    "A3": (297, 420),
    "A4": (210, 297),
    "A5": (148, 210),
    "Letter": (216, 279),
    "Legal": (216, 356),
}

# 纸张方向
ORIENTATION_PORTRAIT = "portrait"  # 纵向
ORIENTATION_LANDSCAPE = "landscape"  # 横向
ORIENTATION_AUTO = "auto"  # 按文档
ORIENTATION_AUTO_DETECT = "auto_detect"  # 自动横纵（根据页面尺寸判断）

# PDF类型
PDF_TYPE_IMAGE = "image"  # 图片型
PDF_TYPE_EDITABLE = "editable"  # 可编辑型

# 输出模式
OUTPUT_SEPARATE = "separate"  # 各自生成
OUTPUT_MERGE = "merge"  # 合并为一个

# 打印模式
PRINT_MODE_SINGLE = "single"  # 单面打印
PRINT_MODE_DUPLEX = "duplex"  # 双面打印

# Office引擎类型
ENGINE_AUTO = "auto"  # 自动检测
ENGINE_MS_OFFICE = "office"  # Microsoft Office
ENGINE_WPS = "wps"  # WPS Office

# 图片型PDF清晰度选项 (DPI)
DPI_OPTIONS = [150, 300, 600]
DPI_DEFAULT = 300  # 默认300dpi

# Word纸张尺寸常量 (WdPaperSize)
WORD_PAPER_MAP = {
    "A3": 8,  # wdPaperA3
    "A4": 7,  # wdPaperA4
    "A5": 11,  # wdPaperA5
    "Letter": 1,  # wdPaperLetter
    "Legal": 4,  # wdPaperLegal
}

# Excel纸张尺寸常量
EXCEL_PAPER_MAP = {
    "A3": 8,  # xlPaperA3
    "A4": 9,  # xlPaperA4
    "A5": 11,  # xlPaperA5
    "Letter": 1,  # xlPaperLetter
    "Legal": 5,  # xlPaperLegal
}

# 缩放选项
SCALE_FIT_MARGIN = "fit_margin"  # 适合打印边距（缩放到纸张内）
SCALE_ACTUAL_SIZE = "actual_size"  # 实际大小（不缩放）
SCALE_SHRINK_OVERSIZED = "shrink_oversized"  # 缩小过大页面（超出时才缩小）

# 默认缩放选项
SCALE_DEFAULT = SCALE_SHRINK_OVERSIZED
