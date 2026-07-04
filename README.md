# File Toolbox

批量文件工具箱,提供 5 个常用文件批处理功能,带命令行(CLI)和图形界面(GUI)。

| 功能 | 说明 | 平台要求 |
|---|---|---|
| **批量重命名** | 前缀/后缀/替换/正则/序号/删除/日期,可组合 | 全平台 |
| **批量建文件夹** | 从粘贴的 Excel 表格或层级列表批量创建目录结构 | 全平台 |
| **批量生成 PDF** | Word/Excel/PPT/图片 → PDF,可合并、可转图片型 | Word/Excel/PPT 需 Windows + Office |
| **批量替换** | Word/Excel/txt 文档内容批量替换(简单+正则),自动备份 | Word/Excel 需 Windows + Office |
| **发票识别** | 电子发票(PDF/OFD/XML)→ Excel(双 Sheet)/JSON,按发票号码去重 | 需 `pip install 'file-toolbox[invoice]'` |

## 安装

```bash
git clone <repo-url> file-toolbox
cd file-toolbox
pip install -e .
# 带 GUI:
pip install -e ".[gui]"
# 带发票识别:
pip install -e ".[invoice]"
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

# 发票识别(默认预览,--yes 导出;支持 zip/xml/ofd/pdf)
file-toolbox invoice *.zip *.xml *.ofd *.pdf \
    --format excel --output 发票汇总.xlsx \
    --dedupe mark --yes

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

一个主窗口,5 个 Tab(重命名 / 建文件夹 / 生成PDF / 内容替换 / 发票识别),顶部有「历史」按钮查看操作记录。

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
- 发票识别(PDF/OFD/XML 解析 + Excel/JSON 导出):**全平台**,需额外安装 `pip install 'file-toolbox[invoice]'`(pdfplumber + openpyxl)。扫描版发票(图片型)暂不支持。

## 打包与发版

本项目用 **PyInstaller**(onedir 模式)打包为 Windows 可执行程序,产出免安装便携 zip。

### 本地打包

```bash
uv run --extra gui --extra invoice --extra dev python scripts/build_exe.py
# 产物:dist/FileToolbox-{version}-win64.zip
```

### 版本号管理

版本号唯一真相源:`pyproject.toml`。`__init__.py` 运行时经 `importlib.metadata` 读取。

```bash
# 查看当前版本
uv run --extra dev python scripts/bump_version.py current

# bump 版本(自动改 pyproject + 迁移 CHANGELOG + git commit + tag)
uv run --extra dev python scripts/bump_version.py bump patch
uv run --extra dev python scripts/bump_version.py bump minor
uv run --extra dev python scripts/bump_version.py bump --set 1.0.0

# 推送 tag 触发 GitHub Actions 发版
git push --tags
```

### 更新依赖

```bash
uv run --extra dev python scripts/update_deps.py check    # 检查可升级
uv run --extra dev python scripts/update_deps.py update   # 全量升级 uv.lock
uv run --extra dev python scripts/update_deps.py update PySide6  # 单包升级
```

### 一键发版

```bash
uv run --extra dev python scripts/release.py patch   # bump → build,提示推送
```

### GitHub Actions

推送 `v*` tag 后,`.github/workflows/release.yml` 自动执行两个 job:

1. **build**(Windows):PyInstaller 打包,输出便携 zip + 校验和。
2. **release**(Ubuntu):创建 GitHub Release 并附带 zip + 校验和。

## 自动更新

便携 exe 版本内置**自动更新**:程序启动时后台静默检查新版本,有更新时状态栏显示
「🆕 发现新版本 vX.Y.Z · 点击更新」提示。点击后下载(带进度条)、自动校验 SHA256,
确认后**整目录替换并重启**到新版本。

- **更新源**:GitHub Release。
- **仅提示正式版**:预发布版本(a/b/rc/dev)不会通知用户。
- **强制校验**:下载的 zip 经 SHA256 校验,不匹配则丢弃、不应用。
- **数据安全**:替换的是程序目录 `FileToolbox/`,用户数据 `.file_toolbox/`(备份/历史)
  与程序同级、不受影响,更新不丢失。
- **失败可回退**:替换采用 `.old` 回滚式策略,失败时自动还原旧目录并弹窗提示。
- pip 安装的源码版**不启用**自动更新(用 `pip install -U file-toolbox` 升级)。

## 许可证

MIT
