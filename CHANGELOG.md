# Changelog

## [Unreleased]

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
