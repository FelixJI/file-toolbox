"""PDF 排序常量:排序方向、未匹配策略、后缀与默认输出名。"""

# 排序方向
ORDER_ASC = "asc"  # 升序(默认)
ORDER_DESC = "desc"  # 降序

SUPPORTED_ORDERS = (ORDER_ASC, ORDER_DESC)

# 未匹配页策略(某页提取不到排序文字时)
UNMATCHED_LAST = "last"  # 保持原相对顺序排在末尾(默认)
UNMATCHED_FIRST = "first"  # 保持原相对顺序排在最前
UNMATCHED_FAIL = "fail"  # 该 PDF 不排序,报错提示修正格式

SUPPORTED_UNMATCHED = (UNMATCHED_LAST, UNMATCHED_FIRST, UNMATCHED_FAIL)

# 源文件后缀
SUPPORTED_SUFFIXES = (".pdf",)

# 未显式指定输出时,输出名 = 源主名 + 该标记 + .pdf(写在源文件同目录)
SORTED_MARKER = "_排序"
