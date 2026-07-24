# Changelog

## [Unreleased]

## 0.1.10 - 2026-07-24

### Fixed
- 修复 CI(Linux runner)上 pytest 收集 GUI 测试失败:`PySide6.QtWidgets` 在 import 时
  加载 `libEGL.so.1`/`libGL` 原生库,ubuntu runner 默认未装。
  - CI 安装 Qt 运行期系统库(libegl1/libgl1/libxkbcommon 等),GUI 测试在 Linux 真正运行。
  - 6 个 GUI 测试的 `importorskip` 由顶层 `PySide6` 改为 `PySide6.QtWidgets` 子模块,
    缺原生库时干净跳过而非收集报错(防御性,缺库也能跑其余测试)。

## 0.1.9 - 2026-07-24

### Fixed
- 修复 CI(Linux runner)上 mypy 误报 Windows-only API(`os.startfile` / `winreg`)的 7 个错误:
  mypy 固定 `platform=win32`,与目标平台(Windows 桌面工具)及开发机一致。
- 修复潜在运行时崩溃:`updater/replacer.py` 模块级取 `os.startfile` 改为 `getattr` 回退,
  非 Windows 不再 import 即报错;`common/shortcuts.py` 注册表探测补 `ImportError` 捕获。
- 修复测试在 Linux 上的收集崩溃:`test_engine_manager.py` 改用 `pytest.importorskip("winreg")`,
  非 Windows 干净跳过。

## 0.1.8 - 2026-07-23

## 0.1.7 - 2026-07-22

## 0.1.6 - 2026-07-06

### Changed
- PDF 生成 Tab:文件选择与预览合并为一张表(源/输出/大小/状态),布局更紧凑。
- "刷新预览"按钮真正刷新预览表(选文件后展示待转换清单 + 预期输出名)。
- 引擎检测改注册表探测(毫秒级),首次生成时用一次真 Dispatch 兑现验证。
- PDF 生成过程搬到后台线程(QThread),转换期间 UI 不卡顿,进度条实时推进。
- 新增生成取消功能(生成中显示"取消"按钮)。

## 0.1.5 - 2026-07-05

## 0.1.4 - 2026-07-01

## 0.1.3 - 2026-06-30

## 0.1.2 - 2026-06-30

## 0.1.1 - 2026-06-30

### Added
- 打包与发版工具链:
  - Nuitka `--standalone` 打包脚本(`scripts/build_exe.py`),产出 Windows 便携 exe + zip + 校验和。
  - 版本号管理 `scripts/bump_version.py`(bump/current/validate,自动 git commit + tag),pyproject.toml 单一真相源。
  - 依赖更新 `scripts/update_deps.py`(uv lock 封装 + 升级摘要)。
  - 一键发版 `scripts/release.py`。
  - GitHub Actions `release.yml`:tag 触发自动打包 + 发版。
- 发票识别工具 `invoice`:识别电子发票(PDF/OFD/XML),导出 Excel(双 Sheet:汇总+明细)/JSON。
  - 解析优先级:ZIP 内 XML > OFD > PDF(XML/OFD 为结构化数据,PDF 为尽力而为)。
  - 按发票号码去重,支持 keep_all/dedupe/mark(标色)三策略;同号不同来源保留更高优先级。
  - GUI 表格预览,重复行标黄、PDF 弱解析行标灰。
  - 新增可选依赖组 `invoice`(pdfplumber + openpyxl)。
- 关于界面(`gui` 第 6 个 Tab):展示软件名称/版本号/开源地址(可点击+复制)/技术路线/更新日志。
  - 一键创建/删除桌面与开始菜单快捷方式(Windows `.lnk` via COM,Linux `.desktop`)。
  - Windows 用注册表读取真实桌面路径(规避 OneDrive 重定向);macOS 提示手动添加。
  - 新增 `common/metadata.py`(应用元信息单一数据源,`get_changelog()` 3 级回退链读 `CHANGELOG.md`)。

## 0.1.0 - 2026-06-25

### Added
- 批量重命名(7 种操作:前缀/后缀/替换/正则/序号/删除/日期,可组合)
- 批量建文件夹(层级列表或 Excel 表格粘贴,冲突合并/跳过)
- 批量生成 PDF(Word/Excel/PPT/图片,合并/分别输出,可编辑型/图片型,纸张方向控制)
- 批量内容替换(Word/Excel/txt,简单替换+正则,执行前自动备份)
- typer 命令行(4 个子命令 + gui),紧凑可重复的 `--op type:key=value` 语法
- PySide6 图形界面(主窗口 + 4 Tab)
- JSON 历史存储(`.file_toolbox/history/*.jsonl`,支持撤销标记)
