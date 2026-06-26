# 关于界面与快捷方式管理设计 (About Tab & Shortcuts)

- 日期:2026-06-26
- 状态:已批准(待实现)
- 范围:为 file-toolbox GUI 新增第 6 个 Tab「关于」,展示软件名称/版本号/开源地址/技术路线/更新日志,并提供一键创建/删除桌面与开始菜单快捷方式的能力。
- 不在范围内:任务栏直接 pin(Win10/11 已禁止程序化)、检查更新(联网)、软件图标资源。

## 1. 背景与目标

当前 GUI 是「顶部历史按钮 + 5 Tab」结构,缺少「关于」入口,用户无法查看版本、开源地址与技术栈。同时用户希望像常规桌面应用一样,能一键创建桌面/开始菜单快捷方式。

目标:新增第 6 个 Tab「关于」,集中展示应用元信息与更新日志,并提供快捷方式创建/删除功能,模块遵循项目现有「common=纯逻辑可测 / gui=界面」分层。

## 2. 关键决策(用户确认)

| 决策点 | 选择 | 说明 |
|---|---|---|
| 入口形式 | 第 6 个 Tab(嵌入主窗口) | 非弹窗,与现有 5 Tab 一致 |
| 开源地址 | 占位常量 `REPO_URL` | 当前 `https://github.com/felji/file-toolbox`,后续替换 |
| 快捷方式范围 | 桌面 + 开始菜单 | 任务栏 pin 走开始菜单右键固定(Win10/11 禁止程序化) |
| 快捷方式创建/删除 | 均支持 | 幂等,可重复操作 |
| CHANGELOG 来源 | 运行时读取 `CHANGELOG.md`(方案 B) | 单一数据源;3 级回退链兜底 |
| 打包配置 | 第一版不改 | 依赖回退链;真实分发需求出现时再处理 |
| 跨平台 | Windows 全功能 / Linux `.desktop` / macOS 提示手动 | 平台差异内化在 shortcuts 模块 |

## 3. 架构与模块布局

遵循现有分层(`common/<模块>` 纯逻辑、`gui/dialogs/<tab>` 界面),新增 2 个 common 模块 + 1 个 GUI Tab:

```
file_toolbox/
├── __init__.py              # 已有:__version__、APP_NAME
├── common/
│   ├── metadata.py          # 新增:应用元信息 + CHANGELOG 读取(单一数据源)
│   └── shortcuts.py         # 新增:跨平台快捷方式创建/删除
├── gui/
│   ├── main_window.py       # 改:注册第 6 个 Tab
│   └── dialogs/
│       ├── about_tab.py     # 新增:第 6 个 Tab(QWidget)
│       └── __init__.py      # 改:导出 AboutTab
```

**关键约束**:
- 快捷方式逻辑(`shortcuts.py`)与操作系统交互,UI 只调用它返回的 `ShortcutResult`,便于纯单元测试。
- `metadata.py` 提供 `get_changelog()` 给 UI 用,UI 不直接读文件。
- 元信息单一数据源 → 以后改版本号、仓库地址只动一处。

## 4. 数据层:`common/metadata.py`

集中存放应用元信息。CLI 的 `--version` 与 About Tab 都从这里读,不各自硬编码。

### 4.1 常量

```python
from file_toolbox import __version__

APP_NAME = "File Toolbox"
APP_DESCRIPTION = "批量文件工具箱:重命名、建文件夹、生成 PDF、内容替换、发票识别"
VERSION = __version__
REPO_URL = "https://github.com/felji/file-toolbox"   # ← 占位常量,后续替换
LICENSE = "MIT"
PYTHON_REQUIREMENT = ">=3.11"

TECH_STACK = [
    ("Python", ">=3.11"),
    ("PySide6", ">=6.5 (GUI)"),
    ("typer", ">=0.9 (CLI)"),
    ("pypdf / PyMuPDF", "(PDF 处理)"),
    ("pdfplumber + openpyxl", "(发票识别,可选)"),
    ("pywin32", ">=306 (Windows COM 自动化,仅 Windows)"),
]
```

### 4.2 `get_changelog()`

方案 B 核心,按 **3 级回退链**找 `CHANGELOG.md`(已确认 pip 安装的包不含该文件):

```python
def get_changelog() -> str:
    """读取 CHANGELOG.md,失败返回兜底文本。

    查找顺序:
    1. 仓库根(开发环境):  <包目录>/../../CHANGELOG.md
    2. 当前工作目录:      ./CHANGELOG.md
    3. 都找不到 → 返回内置兜底字符串(显示版本号,提示完整日志见仓库)
    """
```

兜底文本示例:
```
当前版本 0.1.0。
完整更新日志请见开源仓库的 CHANGELOG.md。
(未在当前运行环境找到 CHANGELOG.md 文件)
```

**设计理由**:单一数据源 + 3 级回退 → 开发环境显示完整日志,打包/异地运行优雅降级不报错;`TECH_STACK` 用元组列表 → UI 控制格式化,数据不绑死呈现方式。

## 5. 快捷方式层:`common/shortcuts.py`

跨平台快捷方式创建/删除,**纯逻辑、可单测、UI 只看返回值**。

### 5.1 返回结构

```python
from dataclasses import dataclass

@dataclass
class ShortcutResult:
    success: bool
    path: str          # 实际创建/删除的快捷方式路径(失败时为空)
    location: str      # "desktop" / "start_menu"
    message: str       # 给用户看的中文提示(成功/失败原因)
```

### 5.2 公共 API

```python
def create_desktop_shortcut() -> ShortcutResult: ...
def create_start_menu_shortcut() -> ShortcutResult: ...
def remove_desktop_shortcut() -> ShortcutResult: ...
def remove_start_menu_shortcut() -> ShortcutResult: ...
```

### 5.3 快捷方式目标(Target)

统一指向启动 GUI 的命令:
- **Windows**: `sys.executable`(当前 Python 解释器)+ 参数 `-m file_toolbox gui`(已验证 `python -m file_toolbox gui` 可用)。暂无图标资源,用默认。
- **Linux**: 创建 `.desktop` 文件,`Exec` 同上。
- **macOS**: 返回 `success=False, message="macOS 暂不支持自动创建,请手动添加"`。

### 5.4 Windows 桌面路径(关键技术点)

直接用 `Path.home() / "Desktop"` 会因 **OneDrive 重定向**失败。用注册表取真实路径:

```python
def _windows_desktop() -> Path:
    try:
        import winreg
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders",
        ) as key:
            desktop, _ = winreg.QueryValueEx(key, "Desktop")
            return Path(desktop)
    except OSError:
        return Path.home() / "Desktop"   # 回退
```

开始菜单路径:`Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs"`,目录不存在则创建。

### 5.5 Windows 创建(`.lnk`)

用 `WScript.Shell`(COM,`win32com.client`)。`pywin32` 已是 Windows 依赖,无需新增。

### 5.6 操作语义

| 操作 | 情况 | 行为 |
|---|---|---|
| 创建 | 快捷方式不存在 | 创建,`success=True` |
| 创建 | 已存在同名 | **覆盖**(幂等,可重复点击) |
| 创建 | 失败(COM/权限) | `success=False` + 异常信息,不抛异常 |
| 删除 | 快捷方式存在 | 删除,`success=True` |
| 删除 | 不存在 | `success=False, message="未找到桌面快捷方式(可能尚未创建)"`,**不报错** |
| 删除 | 失败(权限/占用) | `success=False` + 异常信息,不抛异常 |

**路径一致性**:删除函数复用创建时同一套路径解析,保证创建到哪就能从哪删。

**设计理由**:统一 `ShortcutResult` 让 UI 无需关心平台差异;所有失败内化,UI 永远拿到结果能弹框;Windows 复用已有 `pywin32` 依赖,零新增依赖。

## 6. UI 层:`gui/dialogs/about_tab.py`

纯展示为主 + 4 个快捷方式按钮。继承 `QWidget`(同 `InvoiceTab` 模式),不混入业务逻辑。

### 6.1 布局(自上而下)

```
┌─────────────────────────────────────────────┐
│           File Toolbox                      │   ← 居中大字(无图标资源)
│           版本 0.1.0                        │
│           批量文件工具箱                     │
│                                             │
│   ─────────── 基本信息 ───────────          │   ← 分组标题
│   开源地址    https://github.com/...  [复制] │   ← QLabel(可点击外链) + 复制按钮
│   许可证      MIT                            │
│   Python 要求 >=3.11                        │
│   运行环境    win32                          │   ← 动态:platform.platform() 或 sys.platform
│                                             │
│   ─────────── 技术路线 ───────────          │
│   Python              >=3.11                │
│   PySide6             >=6.5 (GUI)           │   ← Form 布局,遍历 TECH_STACK
│   ...                                       │
│                                             │
│   ─────────── 更新日志 ───────────          │
│   ┌─────────────────────────────────────┐   │
│   │ # Changelog                         │   │   ← QPlainTextEdit
│   │ ## [Unreleased]                     │   │      (只读,等宽字体,
│   │ - 发票识别工具 invoice ...           │   │       显示 get_changelog())
│   └─────────────────────────────────────┘   │
│                                             │
│   桌面:    [添加到桌面]  [从桌面移除]       │   ← 操作区(每行一个目标位置)
│   开始菜单: [添加到开始菜单] [从开始菜单移除] │
│                                             │
│   [状态提示文本]                             │   ← 每次操作后更新
└─────────────────────────────────────────────┘
```

### 6.2 关键交互

| 元素 | 行为 |
|---|---|
| 软件名/版本 | 从 `metadata` 读,**不硬编码** |
| 运行环境 | 动态读 `platform.platform()`(如 `Windows-11-10.0.26220-SP0`),反映实际运行环境 |
| 开源地址 | `QLabel` 开 `OpenExternalLinks`,点击浏览器打开仓库 |
| 开源地址 `[复制]` | `QApplication.clipboard().setText(url)`,状态栏提示"已复制" |
| 技术路线 | 遍历 `TECH_STACK` 元组,Form 布局渲染 |
| 更新日志 | `QPlainTextEdit` 只读,等宽字体,`setPlainText(get_changelog())` |
| `[添加到桌面]` | 调 `create_desktop_shortcut()`,弹 `QMessageBox` 显示 `result.message` |
| `[从桌面移除]` | 调 `remove_desktop_shortcut()`,同上 |
| `[添加到开始菜单]` / `[从开始菜单移除]` | 同理,调对应函数 |
| 状态提示 | 操作后底部 QLabel 更新(如"✓ 已创建到桌面") |

按钮分两行(每行一个目标位置)而非 2×2 网格:操作语义清晰,用户一眼看出"我在操作哪个位置的快捷方式"。

### 6.3 不做的事(YAGNI)

- ❌ 检查更新(需联网,超出范围)
- ❌ 图标资源(项目无,用文字 LOGO;留接口以后加)
- ❌ 任务栏 pin(走开始菜单右键固定)
- ❌ 更新日志交互式展开折叠(只读文本框足够)

## 7. 主窗口改动

`gui/main_window.py` 加:

```python
self._about_tab = AboutTab()
tabs.addTab(self._about_tab, "关于")
```

`closeEvent` 遍历列表加上 `self._about_tab`。`AboutTab` 是纯展示 Widget,无 worker 需特殊清理,但保险起见仍加入遍历。

## 8. 测试策略

遵循现有模式(`tests/test_*.py`,GUI 测试用 `pytest.importorskip("PySide6")` + `QApplication` fixture)。三层各自可测。

### 8.1 `shortcuts.py`(纯逻辑,重点测)

```python
# tests/test_shortcuts.py
def test_create_desktop_shortcut_returns_result(tmp_path, monkeypatch):
    # monkeypatch 桌面路径到 tmp_path,避免污染真实桌面
    # 断言返回 ShortcutResult,.lnk 文件确实生成
    # Windows 跑真实 COM,Linux 跑 .desktop 路径

def test_create_overwrites_existing(tmp_path, monkeypatch):
    # 已存在同名 → 覆盖,success=True

def test_remove_nonexistent_returns_false(tmp_path, monkeypatch):
    # 删不存在的 → success=False,不抛异常

def test_create_then_remove_is_idempotent(tmp_path, monkeypatch):
    # 创建 → 删除 → 再删除(应 success=False)
```

`monkeypatch` 把 `_windows_desktop()` / 开始菜单目录重定向到 `tmp_path`,**测试不碰用户真实桌面/开始菜单**。

### 8.2 `metadata.py`(纯逻辑)

```python
# tests/test_metadata.py
def test_version_matches_package():
    assert metadata.VERSION == file_toolbox.__version__

def test_get_changelog_finds_repo_root():  # 开发环境
    # CHANGELOG.md 在仓库根,应返回完整内容
    assert "Changelog" in metadata.get_changelog()

def test_get_changelog_fallback_when_missing(tmp_path, monkeypatch):
    # 把 CWD 切到 tmp_path,模拟找不到文件
    # 断言返回兜底字符串(含版本号),不抛异常
```

### 8.3 `about_tab.py`(GUI 冒烟测试)

```python
# tests/test_about_gui.py
pytest.importorskip("PySide6")

def test_about_tab_instantiates(app):
    tab = AboutTab()
    assert tab is not None

def test_about_tab_shows_version(app):
    tab = AboutTab()
    # 控件命名以实现为准(如 _lbl_version / _version_label),断言版本号出现在界面某处
    assert "0.1.0" in _collect_tab_text(tab)

def test_about_tab_has_changelog(app):
    tab = AboutTab()
    # 通过辅助函数读取 Tab 内所有文本,不依赖具体控件名
    assert "Changelog" in _collect_tab_text(tab)
```

GUI 测试**不实际点按钮**(难可靠),只验证控件存在 + 数据正确渲染。按钮逻辑由 `shortcuts` 单测覆盖。

> 注:测试通过辅助函数 `_collect_tab_text(tab)` 递归收集 Tab 内所有 QLabel/QPlainTextEdit 文本,避免依赖具体控件名(实现时控件命名可能调整)。

## 9. 打包配置(第一版不改)

方案 B 的潜在风险:`CHANGELOG.md` 在仓库根(包目录外),pip 安装的包不含该文件。

**第一版决策:不改打包配置**,依赖 `get_changelog()` 的 3 级回退链。开发环境显示完整日志,pip 安装环境显示兜底文本(也不报错)。等真实分发需求出现时再处理打包(`package-data` 配置对包外文件支持不一致,需实测)。

## 10. 影响范围汇总

| 文件 | 改动类型 | 说明 |
|---|---|---|
| `common/metadata.py` | 新增 | 元信息 + CHANGELOG 读取 |
| `common/shortcuts.py` | 新增 | 快捷方式创建/删除 |
| `gui/dialogs/about_tab.py` | 新增 | 第 6 个 Tab |
| `gui/dialogs/__init__.py` | 改 | 导出 `AboutTab` |
| `gui/main_window.py` | 改 | 注册第 6 个 Tab |
| `tests/test_metadata.py` | 新增 | 元信息测试 |
| `tests/test_shortcuts.py` | 新增 | 快捷方式测试 |
| `tests/test_about_gui.py` | 新增 | GUI 冒烟测试 |
| `CHANGELOG.md` | 改 | 加本次变更条目 |
