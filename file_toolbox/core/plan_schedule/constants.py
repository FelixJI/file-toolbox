"""计划排布常量:输入表头别名、输出命名与样式颜色。"""

# 支持的输入格式(纯 openpyxl 读取,与 excel_merge 一致)
SUPPORTED_SUFFIXES = (".xlsx", ".xlsm")

# 输出文件默认名(CLI/GUI 未指定输出位置时使用;已存在时自动加序号)
DEFAULT_OUTPUT_NAME = "计划排布.xlsx"

# 输出工作簿中的工作表名
SHEET_NAME = "计划排布"

# GUI 导出输入清单模板的默认文件名
TEMPLATE_NAME = "计划排布清单模板.xlsx"

# 输入表头别名(去空白后精确匹配;顺序即优先级)
NAME_HEADERS = ("项点名称", "项点", "名称", "任务名称", "任务")
START_HEADERS = ("起始日期", "开始日期", "起始时间", "起始", "开始")
END_HEADERS = ("终止日期", "结束日期", "终止时间", "终止", "结束")

# 在前 N 行内搜索表头行
MAX_HEADER_SCAN_ROWS = 5

# 含年份的日期串格式
DATE_FORMATS_FULL = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日", "%Y%m%d")
# 缺年份的日期串:(格式, 与年份拼接的分隔符)。解析时把默认年份拼在前面按含年格式读,
# 避免 Python 3.13 对"无年份日月"strptime 的 DeprecationWarning。
DATE_FORMATS_NO_YEAR = (("%m-%d", "-"), ("%m/%d", "/"), ("%m.%d", "."), ("%m月%d日", "年"))

# ---- 输出样式 ----

# 项点名称列 / 日期列宽
NAME_COLUMN_WIDTH = 14.0
DAY_COLUMN_WIDTH = 4.5

# 周末整列浅灰底(DATE 表头 + 项点行 + 并行数行)
WEEKEND_FILL = "FFF2F2F2"
# 周末 DATE 表头红字(与浅灰底叠加,更醒目)
WEEKEND_HEADER_FONT = "FFC00000"

# 项点活动格循环配色(浅色系,黑字可读;按项点在清单中的顺序循环取色,
# 同一天并行的相邻项点颜色不同,便于区分)
ITEM_FILLS = (
    "FFBDD7EE",  # 浅蓝
    "FFF8CBAD",  # 浅橙
    "FFC6E0B4",  # 浅绿
    "FFFFE699",  # 浅金
    "FFD9C3E6",  # 浅紫
    "FFB7DEE8",  # 浅青
)
