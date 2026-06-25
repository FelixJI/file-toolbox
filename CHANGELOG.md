# Changelog

## 0.1.0 - 2026-06-25

### Added
- 批量重命名(7 种操作:前缀/后缀/替换/正则/序号/删除/日期,可组合)
- 批量建文件夹(层级列表或 Excel 表格粘贴,冲突合并/跳过)
- 批量生成 PDF(Word/Excel/PPT/图片,合并/分别输出,可编辑型/图片型,纸张方向控制)
- 批量内容替换(Word/Excel/txt,简单替换+正则,执行前自动备份)
- typer 命令行(4 个子命令 + gui),紧凑可重复的 `--op type:key=value` 语法
- PySide6 图形界面(主窗口 + 4 Tab)
- JSON 历史存储(`.file_toolbox/history/*.jsonl`,支持撤销标记)
