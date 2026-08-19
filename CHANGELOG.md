# Changelog

## 0.2.9

### Bug Fixes

- **gui:** 内容替换预览与执行移入后台线程修复主界面冻结 (#53) (2d6fc88)
- **gui:** 修复入口以 __main__ 执行时启动留痕日志丢失 (#50) (bc4676b)

### Performance

- **gui:** 功能 Tab 懒构造，首帧只构造当前页 (#51) (a8752e6)

## 0.2.8

### Bug Fixes

- **gui:** 修复启动自动检查更新在主线程执行导致 GUI 冻结 (#48) (eb68218)

## 0.2.7

### Bug Fixes

- **gui:** 修复关闭 Tab 报错、配置落位程序目录并增加冻结诊断留痕 (#46) (2688877)

## 0.2.6

### Breaking Changes

- 升级到 Python 3.13、升级全部依赖并修复 Dependabot 安全提醒 (#42) (8523354)

### Features

- **release:** 移除 Setup 安装器仅保留便携版自更新 (#43) (6cfd69a)

### Bug Fixes

- **pdf:** 加快引擎检测并修正生成态引擎显示 (#39) (84fa474)

## 0.2.5

### Features

- **updater:** 迁移 Velopack 更新链 (#35) (b02c96d)

### Dependencies

- **deps:** 使用成熟依赖收敛基础能力 (#37) (1f0224e)

## 0.2.4

### Features

- **attendance:** 识别加班并清理末尾空行 (#33) (5b89847)

## 0.2.3

### Bug Fixes

- **attendance:** 支持基础模板生成名单分组工作表 (#31) (4d14684)
- **updater:** 修复便携版更新识别 (#30) (2873d0e)

## 0.2.2

### Bug Fixes

- **attendance:** 修复考勤报错并完善产品日志 (#28) (7ccb81d)

## 0.2.1

### Features

- **attendance:** 增加人员名单导入与分组输出 (#26) (9783867)

### Bug Fixes

- **updater:** 修复检查更新无反应并扩充主流代理镜像 (#25) (cf7ae52)

## 0.2.0

### Features

- **attendance:** 新增可配置考勤汇总与分组导出 (#23) (41b7dbe)
- **gui:** 历史按钮跟随标签页并整合更新与代理回退 (#19) (d577523)
- **ci:** 统一自动化发布流程 (#9) (c99a9c4)

### Bug Fixes

- **ci:** 修复镜像标签同步并完善六仓治理 (#18) (0b18aaa)
- **release:** 统一候选派生资产归属 (#14) (9648251)
- **test:** 修复 CodeQL URL 子串校验告警 (#13) (94c72b9)
- **ci:** 修复发布 tag 推送认证 (#12) (35eb484)
- **rename-template:** 校验导入模板 operations 键 + 补强覆盖率与边缘测试至 100% (#7) (6fcac0a)
- **release:** 收敛发布与 Changelog 工作流 (#6) (39c813d)

### Performance

- **ci:** 支持统一分片门禁与取消过时 PR 运行 (#15) (4ffa958)

### Dependencies

- **deps:** bump pypdf from 6.14.2 to 6.15.0 (#20) (da9f50e)
- **deps:** bump cryptography from 49.0.0 to 50.0.0 (#16) (c312e39)

## [0.1.15](https://github.com/FelixJI/file-toolbox/compare/v0.1.14...v0.1.15) (2026-08-02)


### Fixed

* **release:** 收敛发布与 Changelog 工作流 ([#6](https://github.com/FelixJI/file-toolbox/issues/6)) ([39c813d](https://github.com/FelixJI/file-toolbox/commit/39c813db435881a75e76c9aca55575d3e2723c6e))
* **rename-template:** 校验导入模板 operations 键 + 补强覆盖率与边缘测试至 100% ([#7](https://github.com/FelixJI/file-toolbox/issues/7)) ([6fcac0a](https://github.com/FelixJI/file-toolbox/commit/6fcac0a4257c6b306763f29411156545446fa4f8))

## 0.1.14 - 2026-07-30

### Fixed
- `JsonHistoryStore.get_records(limit<0)` 反向切片丢首条:`limit=-1` 误返回 N-1 条
  (docstring 承诺 ≤0 表示全部)。统一用 `limit>0` 判定。
- 批量重命名 `_delete_chars` 前缀删除 value 为负数时语义反转:`name[count:]` 对负数
  取到尾部(`"ABCDE"` 删 -2 误返回 `"DE"`)。负数视为无效返回原名。
- 内容替换 simple_replace 不区分大小写时,replace 文本含反斜杠(`\d`/`\1`)抛
  `re.error('bad escape')` 或误当反向引用;区分大小写分支(`str.replace`)正常。
  改用 lambda 使 replacement 作为字面文本,两分支行为一致(`batch_rename` 与
  `text_handler` 两处同款写法一并修复;regex_replace 仍保留反向引用语义)。
- 内容替换 `_create_backup` 同名 stem + 同一秒备份静默覆盖导致备份数据丢失:时间戳
  精度仅到秒,两个不同目录的同名文件同秒备份生成相同文件名。冲突时追加 `_1`/`_2` 后缀。
- 内容替换 `read_content` 读 UTF-8 BOM 文件时 `\ufeff` 残留内容,破坏后续 simple_replace
  匹配。编码列表首选改 `utf-8-sig`(自动剥离 BOM,对无 BOM 文件与 utf-8 一致)。
- GUI `PDFController.summarize_results` 对缺 `success` 键的结果 dict(worker 异常返回
  `{'error': ...}`)抛 `KeyError`,一条异常结果中断整个汇总让 UI 崩溃。改用 `.get('success')`。
- GUI `InvoiceController.dedupe_strategy` 负索引静默返回错误策略:`(-1)` 返回 `'mark'`、
  `(-2)` 返回 `'dedupe'`(Python 负索引),与 docstring「越界抛 IndexError」相悖。显式拒绝。
- GUI `InvoiceTab` 无 `closeEvent`,解析中关闭窗口泄漏 `_parse_worker`(无事件循环 QThread,
  `quit` 无效),进程退出可能崩溃。补 `closeEvent` 协作式 `cancel`+`wait`。
- GUI `RenameController.format_history_line` 对 `data: None`(worker 写入 null)抛
  `AttributeError` 让历史列表整体崩溃。改 `record.get('data') or {}` 兜底。

### Changed
- 测试加固(GUI/CLI 层):补 22 个边界行为断言(用例 1441→1463)。op_parser._coerce
  类型强转边界(前导零/float/bool 大小写/负数/空串/重复键);qt_prompter 参数透传
  (minValue/maxValue/current/editable 实际转发给 QInputDialog,旧测试丢弃参数);
  pdf_cmd 全失败 exit 0(锁定已知风险);replace 预览=执行计数一致;CLI 非法 regex 前置
  拦截;history_dialog 部分撤销仍标记已撤销(锁定已知风险)。
- 测试加固(core/common 层):行覆盖率已达 100% 但不证明边界行为被正确断言。补 48 个「写错断言就变红」
  的强边界断言(format_file_size 精确边界与浮点累积、format_datetime tz 后缀、
  expand_files 顺序/去重、op_schema string_keys 零值/identity、batch_rename 批内冲突/
  digits 溢出、mkdir 校验、invoice 税率/去重/多 DocBody 等)。用例数 1393→1441。
- CI 门禁加强:启用分支覆盖率(`--cov-branch`,core 阈值 88→90);新增严格告警
  (`-W error::ResourceWarning`/`DeprecationWarning`);新增用例数不回退门禁
  (`scripts/check_test_count.py`,基线 1441)。

## 0.1.13 - 2026-07-30

## 0.1.12 - 2026-07-30

### Added
- 关于页新增「检查更新」按钮:所有运行形态(便携 exe / pip / dev)均可手动核实更新可用性。
  便携版发现新版可下载应用;pip/dev 版提示升级命令。
- 关于页新增「GitHub 代理」设置:填入代理基址(如 `https://ghproxy.com`)加速版本检查与下载,
  或用环境变量 `FILE_TOOLBOX_GH_PROXY` 覆盖。
- 新增轻量设置存储(`.file_toolbox/settings.json`)。

### Changed
- 右上角「历史」按钮改为下拉菜单,各项直达对应模块历史(重命名/建文件夹/生成PDF/内容替换/
  发票识别),不再二次选择工具。
- UpdateWorker 新增 `checked` 信号,反馈检查结果(最新/可用/失败),供手动检查 UI 使用。

### Fixed
- 修复 Release 流水线手动触发必然失败:补发逻辑默认开启且按 creatordate 倒序找未发布 tag,
  总是命中 Nuitka 时代的 v0.1.2(代码无法用当前 PyInstaller 工具链构建 → `No module named nuitka`)。
  现补发默认关闭(手动触发即发最新版),且即便开启也只在最近 3 个 tag 范围内查找,
  不再回头处理远古不可构建的历史 tag。
- CI/Release actions 升级到 Node 24 runtime(消除 Node 20 弃用警告):
  checkout v4→v5、setup-uv v3→v7、upload-artifact v4→v6、download-artifact v4→v7、
  action-gh-release v2→v3。Node 20 将于 2026-09-16 从 runner 移除。
  (注:artifact 系列需分别到 upload v6 / download v7 才默认 Node 24,v5 仍是 Node 20。)
- 修复 Release 在 CI 内 bump 版本时 `git commit` 报 exit 128:GitHub runner 默认无全局
  git 提交身份,release.yml build job 现配置 `github-actions[bot]` 身份。
- `bump_version.py` 的 git commit 失败现透出 git 真实 stderr(原先被 `capture_output` 吞掉,
  日志只剩 `exit status 128` 无法诊断根因)。

## 0.1.11 - 2026-07-24

### Fixed
- 修复 CI(Linux runner)上 `test_batch_replace.py` 2 个测试失败:它们 monkeypatch
  `sys.platform="win32"` 后引用 `subprocess.CREATE_NO_WINDOW`,但该常量仅 Windows 存在
  (Linux 上 `subprocess` 模块无此属性 → AttributeError)。改用 monkeypatch 注入该常量,
  使测试在 Linux CI 也能跑(不丢覆盖),验证 `_no_window_flags` 逻辑不变。

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

- 内部修复 / CI 调整,无面向用户变更。

## 0.1.7 - 2026-07-22

- 内部修复 / CI 调整,无面向用户变更。

## 0.1.6 - 2026-07-06

### Changed
- PDF 生成 Tab:文件选择与预览合并为一张表(源/输出/大小/状态),布局更紧凑。
- "刷新预览"按钮真正刷新预览表(选文件后展示待转换清单 + 预期输出名)。
- 引擎检测改注册表探测(毫秒级),首次生成时用一次真 Dispatch 兑现验证。
- PDF 生成过程搬到后台线程(QThread),转换期间 UI 不卡顿,进度条实时推进。
- 新增生成取消功能(生成中显示"取消"按钮)。

## 0.1.5 - 2026-07-05

- 内部修复 / CI 调整,无面向用户变更。

## 0.1.4 - 2026-07-01

- 内部修复 / CI 调整,无面向用户变更。

## 0.1.3 - 2026-06-30

- 内部修复 / CI 调整,无面向用户变更。

## 0.1.2 - 2026-06-30

- 内部修复 / CI 调整,无面向用户变更。

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
