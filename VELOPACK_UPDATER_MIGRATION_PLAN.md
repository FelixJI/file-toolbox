# File Toolbox：Velopack 更新器方案

## 结论

File Toolbox 只保留 Velopack 1.2.0 更新链。发行形态只有 Portable 包，通过 `UpdateCoordinator`
检查、下载并应用 Velopack 包（便携原地自更新）。项目不再发布 Setup 安装器，也不再发布 legacy ZIP。

启动健康失败自动回退不设为 required；下载、校验或 apply 失败时保持当前版本可用仍是 required。

## 固定契约

| 项目 | 决策 |
|---|---|
| Pack ID | `FileToolbox` |
| 安装根 | 解压 Portable 的可写目录（Velopack 便携模式） |
| Channel | `win`，feed 为 `releases.win.json` |
| 新用户入口 | `FileToolbox-Portable.zip` |
| 便携自更新 | Velopack 原生支持（要求解压目录可写） |
| 代理 | GitHub URL-prefix 与 standard forward proxy |
| Package | full nupkg，不生成 delta；`--noInst` 不生成安装器 |

正式 Release 精确包含六项资产：

- `FileToolbox-{version}-full.nupkg`；
- `FileToolbox-Portable.zip`；
- `releases.win.json`；
- `checksums.txt`；
- `SBOM.spdx.json`；
- `build-identity.json`。

`checksums.txt`、identity、SBOM 与候选 manifest 必须绑定同一精确资产集合。CD 只发布 main CI
候选，不重新构建或替换资产。

## 运行时边界

`file_toolbox.updater` 只公开面向 UI 的 Coordinator Interface：

```python
class UpdateCoordinator(Protocol):
    def check(self) -> UpdateCheckResult: ...
    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
    ) -> UpdateApplyResult: ...
```

Qt worker 只认识结果对象，不认识 nupkg、安装器 URL、SHA 文件或 Velopack `UpdateInfo`。生产 Adapter
为 `VelopackUpdateCoordinator`，测试使用 fake。Python 层不实现版本选择、包校验、目录替换或回退。

网络候选支持：

- direct：GitHub Release feed；
- URL-prefix：用户配置的 GitHub 加速前缀；
- standard forward proxy：在 SDK 调用作用域内设置并完整恢复 `HTTP(S)_PROXY`/`NO_PROXY`。

从某个候选取得 feed 后，package 必须继续从同一 source 下载。代理配置的数据迁移继续保留，但不再有
旧 updater 执行路径。

## 数据与启动

`gui_entry.py` 在 frozen 应用初始化前运行 `velopack.App().run()`。GUI 数据根保持
`%USERPROFILE%\.file_toolbox`，CLI 仍使用调用方 cwd 下的 `.file_toolbox/`；更新器不得搬迁、删除或
重新解释 settings、backups、history、logs。

## 验收

- Portable 版可通过 direct、URL-prefix、forward proxy 完成 feed 与 full nupkg 更新并原地应用；
- 取消下载不退出，损坏 package 失败且当前版本仍可启动；
- Portable 能真实启动 `FileToolbox.exe`；
- Release 只包含六项声明资产，extra fail closed；
- GUI/CLI 数据根语义保持不变。

精确本地验证命令：

```powershell
uv sync --frozen --all-extras
uv run --all-extras python scripts/check_release_contract.py
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run --all-extras python scripts/regen_ui.py --check
uv run pytest --cov=file_toolbox --cov-branch --cov-fail-under=90 -q
uv run --all-extras python scripts/build_exe.py --ci
uv run python scripts/release_smoke.py
```

不做启动健康失败自动回退、首版 delta、静默强更或跨产品共享 updater；不修改公共
`scripts/automation_core.py`。
