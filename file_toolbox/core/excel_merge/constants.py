"""Excel 合并常量:命名策略、内容模式、支持的后缀。"""

# 工作表命名策略
NAMING_PREFIX = "prefix"  # 文件主名-工作表名(默认;跨文件同名工作表天然可区分)
NAMING_KEEP = "keep"  # 保留原名,冲突时自动加序号

SUPPORTED_NAMING = (NAMING_PREFIX, NAMING_KEEP)

# 内容模式
MODE_VALUES = "values"  # 取公式的缓存计算结果(默认;从未被 Excel 计算过的公式为空)
MODE_FORMULAS = "formulas"  # 保留公式文本(引用的工作表改名后公式可能失效)

SUPPORTED_MODES = (MODE_VALUES, MODE_FORMULAS)

# 源文件后缀:openpyxl 可读的 xlsx 家族(.xls 二进制老格式不支持)
SUPPORTED_SUFFIXES = (".xlsx", ".xlsm")

# 输出文件默认名(CLI/GUI 未指定输出位置时使用)
DEFAULT_OUTPUT_NAME = "合并结果.xlsx"
