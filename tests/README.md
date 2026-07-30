# tests/ — 测试组织约定

## 文件组织

- **一个被测模块对应一个 `test_<module>.py`**:测试文件与被测源码模块一一对应,
  不按"覆盖率工具关注点"拆分文件。历史遗留的 `test_<module>_coverage.py`
  分裂已于 Phase 7(M5)合并消除。
- **分组用 `pytest` class 或注释分段**(`# --- 区段名 ---` / `# ===== 标题 =====`),
  不用文件后缀。
- **fixture 放 `conftest.py`**:跨文件共享的 fixture(如 `ofd_sample`、`pdf_sample`)
  定义在 `tests/conftest.py`,而非每个测试文件重复。
- 模块级私有 helper(如 `_svc()`、`_make_pdf()`、`_xml()`)放在所属 `test_<module>.py`
  顶部,函数名以 `_` 前缀表明仅模块内使用。

## 运行

```bash
uv run pytest -q                # 全量(基线 1441)
uv run pytest tests/test_X.py   # 单文件
uv run pytest --co -q           # 仅收集,核对用例数
```

## 边界用例约定(Phase A-C 加固)

- **不只是行覆盖**:100% 行覆盖只证明某行被执行过,不证明其边界行为被正确断言。
  新增用例须是「写错断言就变红」的强断言(精确边界值、精确输出文本、行为一致性)。
- **锁定当前行为**:对「代码当前行为正确但语义有争议」的点(如 `validate_folder_name`
  允许 `.`/`..`、invoice 全角 `％` 未归一),用测试**锁定当前行为**并在注释标注「未来
  若收紧策略/改语义,该测试应变红提醒有意更新」,而非擅自改语义。
- **真实缺陷先复现再修**:发现的真实 bug 须先写红测试复现、再改代码转绿(见 git log
  中 `fix(...)` 系列:history 负数 limit、delete_chars 负数、case-insensitive 反斜杠、
  backup 同秒覆盖、BOM 残留)。
