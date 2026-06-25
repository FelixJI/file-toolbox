# File Toolbox

批量文件工具箱,提供 4 个常用文件批处理功能,带命令行(CLI)和图形界面(GUI)。

| 功能 | 说明 | 平台要求 |
|---|---|---|
| **批量重命名** | 前缀/后缀/替换/正则/序号/删除/日期,可组合 | 全平台 |
| **批量建文件夹** | 从粘贴的 Excel 表格或层级列表批量创建目录结构 | 全平台 |
| **批量生成 PDF** | Word/Excel/PPT/图片 → PDF,可合并、可转图片型 | Word/Excel/PPT 需 Windows + Office |
| **批量替换** | Word/Excel/txt 文档内容批量替换(简单+正则),自动备份 | Word/Excel 需 Windows + Office |

## 安装

```bash
git clone <repo-url> file-toolbox
cd file-toolbox
pip install -e .
# 带 GUI:
pip install -e ".[gui]"
```

> 需要 Python ≥ 3.11。

## 命令行

```bash
# 批量重命名(支持多个 --op 组合,默认预览,--yes 执行)
file-toolbox rename *.docx \
    --op add_prefix:text="项目_" \
    --op add_number:start=1,digits=3 \
    --op replace_text:find="草稿",replace="" \
    --dir ./docs --recursive --yes

# 批量建文件夹
file-toolbox mkdir --root ./output \
    --levels "部门A/项目1" "部门A/项目2" "部门B/项目1"
# 或从 Tab 分隔的文本文件读结构:
file-toolbox mkdir --root ./output --from-table structure.txt --on-conflict merge

# 批量生成 PDF(合并模式 + 图片型)
file-toolbox pdf *.docx *.xlsx *.png \
    --output-mode merge --merge-name 汇总.pdf \
    --pdf-type image --dpi 300 --paper A4

# 批量内容替换
file-toolbox replace *.docx \
    --op simple_replace:find="旧公司",replace="新公司",case_sensitive=false \
    --op regex_replace:pattern="20\d{2}",replace="2026" --yes

# 启动图形界面
file-toolbox gui
```

### `--op` 语法

```
--op type:key=value,key=value
```

- 一个 `--op` 描述一个操作,可重复多次,**顺序即应用顺序**。
- `type` 为操作类型,各工具支持的操作见下表。
- 值会自动识别类型:`true`/`false` → 布尔,数字 → 整数,其余为字符串。
- 含逗号或等号的值用双引号包裹:`find="a,b"`。

| 工具 | 操作类型 | 关键参数 |
|---|---|---|
| rename | `add_prefix` / `add_suffix` | `text` |
| rename | `replace_text` | `find`, `replace`, `case_sensitive` |
| rename | `regex_replace` | `pattern`, `replace`, `ignore_case` |
| rename | `add_number` | `start`, `digits` |
| rename | `delete_chars` | `delete_type`(prefix/suffix/text), `value` |
| rename | `add_date` | `format`(如 `%Y%m%d`) |
| replace | `simple_replace` | `find`, `replace`, `case_sensitive` |
| replace | `regex_replace` | `pattern`, `replace`, `ignore_case` |

所有命令**默认预览(dry-run)**,加 `--yes` 才真正执行。

## 图形界面

```bash
file-toolbox gui
```

一个主窗口,4 个 Tab(重命名 / 建文件夹 / 生成PDF / 内容替换),顶部有「历史」按钮查看操作记录。

## 数据位置

工具箱数据(备份、历史)放在**运行目录**下的 `.file_toolbox/`,跟程序走:

```
.file_toolbox/
├── backups/      # 内容替换执行前自动备份(带时间戳)
└── history/      # 各工具操作历史(.jsonl,支持撤销标记)
    ├── rename.jsonl
    ├── replace.jsonl
    ├── pdf.jsonl
    └── mkdir.jsonl
```

## 平台说明

- 重命名、建文件夹、图片转 PDF、文本替换:**全平台**(Windows / macOS / Linux)。
- Word/Excel/PPT 转 PDF、Word/Excel 内容替换:**仅 Windows**,需已安装 Microsoft Office 或 WPS Office(通过 COM 自动化调用)。

## 许可证

MIT
