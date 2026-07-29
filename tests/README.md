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
uv run pytest -q                # 全量(基线 1393)
uv run pytest tests/test_X.py   # 单文件
uv run pytest --co -q           # 仅收集,核对用例数
```
