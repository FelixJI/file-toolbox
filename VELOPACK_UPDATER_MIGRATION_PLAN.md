# File Toolbox：Velopack 更新器迁移实施方案

## 1. 结论

File Toolbox 已采用 Velopack 1.2.0 Python SDK、同版本 `vpk` CLI 和现有 PyInstaller
`onedir` 产物。新安装路径用 `UpdateCoordinator` 隐藏 Velopack，GUI 不再调用自研
`versions/downloader/replacer`；旧实现和 legacy ZIP 在桥接窗口内保留，不叠加到已安装更新链。

真实 SDK/CONNECT Spike 已证明 built-in `HttpSource` 会使用 standard forward proxy，因此无需
materialize fallback。URL-prefix 与 direct 也都直接交给 Velopack；Python 层不实现 nupkg 的版本
选择、包校验、目录替换或回退。

启动健康失败自动回退不设为 required。下载、校验或 apply 失败时保住当前版本仍是 required。

## 2. 固定决策

| 项目 | 决策 |
|---|---|
| Pack ID | `FileToolbox` |
| 安装根 | `%LocalAppData%\FileToolbox`（Velopack 默认） |
| GUI 数据根 | 保持官方快捷方式现有语义：`%USERPROFILE%\.file_toolbox` |
| CLI 数据根 | 保持 cwd-scoped `.file_toolbox/`，不被桌面安装器改写 |
| Channel | 默认 `win`，feed 为 `releases.win.json` |
| Feed | `https://github.com/FelixJI/file-toolbox/releases/latest/download/` |
| Package | 首版 full nupkg，不生成 delta |
| 新用户入口 | `FileToolbox-Setup.exe` |
| 旧用户入口 | 桥接窗口继续发布 `FileToolbox-{version}-win64.zip` |
| 代理 | 用户已有 prefix 列表继续有效；另验证 standard forward proxy |
| 健康回退 | 非强制；保留真实启动与数据路径 smoke |

Velopack Python 要求 PyInstaller `--onedir`，且启动 hook 必须在应用初始化前运行，见
[Python Getting Started](https://docs.velopack.io/getting-started/python)。Python 1.2.0 公开
`GithubSource` 与 `HttpSource`，但没有公开 custom source，见
[Python Sources](https://docs.velopack.io/reference/py/Sources)。

## 3. 目标 Module 与 Interface

`file_toolbox.updater` 继续作为一个 Module，但只公开一个面向 UI 的 Interface：

```python
class UpdateCoordinator(Protocol):
    def check(self) -> UpdateCheckResult: ...
    def download_and_apply(
        self,
        progress: Callable[[int], None] | None = None,
    ) -> UpdateApplyResult: ...
```

Qt worker 只认识结果对象，不认识 `RemoteRelease`、ZIP URL、SHA 文件、`.bat` helper 或
Velopack `UpdateInfo`。生产 Adapter 为 `VelopackUpdateCoordinator`，测试 Adapter 为 fake；
真实本地 feed 是网络 Seam 的测试 Adapter。

网络候选：

- direct：`HttpSource("https://github.com/.../releases/latest/download/")`；
- URL-prefix：`HttpSource("<prefix>/https://github.com/.../releases/latest/download/")`；
- standard forward proxy：在 SDK 调用作用域内注入 upper/lower-case `HTTP(S)_PROXY`，清空
  upper/lower-case `NO_PROXY` 并完整恢复；真实 CONNECT 测试证明 SDK 实际使用该代理；
- 不启用远程 materialize fallback：真实 1.2.0 binding 已覆盖所需能力。

候选不能混用：从某个 base 得到 feed 后，同一检查结果必须从同一 base 下载 package。

## 4. 数据边界先行

当前 `file_toolbox/common/paths.py` 以 `Path.cwd()` 解析 `.file_toolbox/`；项目自己创建的 Windows
快捷方式把 WorkingDirectory 固定为 `Path.home()`。迁移必须保留这两个真实产品语义：

1. `gui_entry.py` 在导入 Qt 前运行 frozen 的 `velopack.App().run()`，并以显式 policy 固定 GUI
   数据根；frozen GUI 同时把 cwd 固定为 `Path.home()`，开发态不改 cwd。
2. `common.paths` 增加显式 `DataRootPolicy` Adapter：GUI 使用 home，CLI 使用调用方 cwd；业务服务
   仍通过既有 `get_*_dir()` Interface 访问。
3. 对现有 `%USERPROFILE%\.file_toolbox` 不移动、不重命名；settings、backups、history、logs 全部原位。
4. 对“直接双击旧 exe 且数据恰好写在程序目录”的非官方路径，只做检测和迁移提示。当前旧 updater
   会整目录删除，无法由新版本事后承诺无损；发布说明必须要求这类用户先备份。

这一步须先于 Velopack apply，否则 `current/` 整体替换会让 cwd 漂移或清掉误放的数据。

## 5. 实施状态与桥接阶段

以下原分片已在当前迁移分支按纵向 TDD 实现；发布后的 bridge 清理仍是后续工作。

### 切片 1：代理与 Python SDK 阻断式 Spike（已完成）

1. 用两个最小 PyInstaller onedir 版本执行 `velopack.App().run()`、check、download、apply、restart。
2. 用 loopback static feed 验证 direct；用路径记录代理验证完整 URL-prefix。
3. 用 loopback CONNECT proxy 验证 upper/lower-case `HTTP(S)_PROXY` 和 `NO_PROXY`。
4. forward proxy 已生效，未实现不需要的“远程 materialize→本地 source”fallback。
5. 验证 Setup、Portable、损坏 full nupkg、取消下载、重复更新锁。

退出条件：三种 transport 均可被自动化证明，fallback 不解析或修改 nupkg，不实现目录替换。

### 切片 2：稳定数据根与新 Interface（已完成）

文件级变更：

- 修改 `file_toolbox/gui_entry.py`，最早执行 Velopack hook，再固定 frozen GUI cwd；
- 重构 `file_toolbox/common/paths.py` 为显式 GUI/CLI data-root policy；
- 新增 `file_toolbox/updater/coordinator.py`、`velopack_adapter.py`、`transport.py`、`models.py`；
- 修改 `gui/updater_widget.py` 依赖 `UpdateCoordinator`；
- `gui/dialogs/about_tab.py` 保留 prefix 列表 UI，并清楚区分“URL 加速前缀”和“系统 forward proxy”；
- 在 `pyproject.toml`/`uv.lock` 锁定 `velopack==1.2.0`，通过 `uv` 更新；
- 在 `scripts/FileToolbox.spec` 明确收集 Velopack native library 与 metadata。

Qt worker 仅依赖新 Coordinator。`UpdateManager.get_is_portable()` 与 legacy 布局 probe 决定是否
进入 Setup bridge，不以 binding 的英文异常文本作为控制流。

### 切片 3：双格式构建与桥接运行态（已完成）

修改 `scripts/build_exe.py`：

1. PyInstaller onedir 仍是唯一产品 build input；
2. 对该目录运行固定版本 `vpk pack --packId FileToolbox --mainExe FileToolbox.exe`；
3. `vpk` 输出进入 `build/` 临时目录，再复制声明的正式资产到 artifacts；
4. 继续生成旧 ZIP，使旧 updater 能把客户端升级到同版本 bridge binary；
5. `checksums.txt` 覆盖 legacy ZIP、Setup、Portable、full nupkg 和 feed；
6. `build-identity.json`、SPDX SBOM 绑定所有发布字节，而不是只绑定 legacy ZIP。

桥接期精确 Release 资产：

- `FileToolbox-{version}-win64.zip`；
- `checksums.txt`、`SBOM.spdx.json`、`build-identity.json`；
- `FileToolbox-{version}-full.nupkg`；
- `FileToolbox-Setup.exe`、`FileToolbox-Portable.zip`；
- `releases.win.json`。

同步修改 `.ci/project.json`、`scripts/release_smoke.py`、`scripts/check_release_contract.py` 及其测试。
CD 只发布 main CI 候选，不运行 `vpk`。

legacy 布局中，Coordinator 检测到 `not-installed` 后下载并校验同版本 Setup，用户确认后退出并安装。
正常 GUI 数据仍在 home 下，不随安装路径变化。迁移成功前保留旧目录。

bridge 先从 feed 取得唯一 `PackageId=FileToolbox` 的 Full asset，并校验/规范化 SemVer；随后把
`latest` 固定为 `/releases/download/v{version}/`，确保 checksums 与 Setup 属于同一版本。

实际 Velopack CLI 1.2.0 在当前 Windows 环境生成 `FileToolbox-win-Setup.exe` 与
`FileToolbox-win-Portable.zip`；构建脚本兼容官方文档所示无 `-win` 名称，并统一输出固定对外名
`FileToolbox-Setup.exe`、`FileToolbox-Portable.zip`。`global.json` 锁定 SDK，构建通过
`dotnet dnx vpk@1.2.0`，不依赖全局 `vpk`。

### 后续：桥接发布与清理（未开始）

1. 发布两个连续双格式版本，验证任一桥接期旧客户端可先吃 legacy ZIP，再装同版本 Setup。
2. 桥接窗口至少两个正式版本或 90 天，以较长者为准。
3. 窗口结束后删除 `versions.py`、`downloader.py`、`replacer.py`、旧 `errors.py`、旧 facade 与对应测试。
4. 删除 `.bat`/`mshta`/目录 rename 逻辑和旧 ZIP 下载 UI 状态；保留 proxy settings 的数据迁移。
5. 后续可停止 legacy ZIP；极老版本改为手动 Setup，不让兼容层永久存在。

## 6. 必须通过的验收

- GUI 从官方快捷方式、桌面双击、Setup stub 启动时都使用同一 home `.file_toolbox/`。
- CLI 在两个不同 cwd 执行时仍各自使用自己的 `.file_toolbox/`。
- settings、backups、history、logs 在 legacy→Setup→N+1 后内容和路径不变。
- direct、prefix、forward proxy 均覆盖 feed 与 full nupkg；错误页不能当 feed/package 成功。
- 取消下载不退出；损坏 package 失败且旧版本可启动；并发更新只允许一个持锁。
- Setup、Portable、legacy ZIP 都能真实启动 `FileToolbox.exe`；新版本启动失败不要求自动回退。
- 发布资产集合、checksums、identity、SBOM 与候选 manifest 完全一致。

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
uv run python scripts/automation.py ci --event pull_request --source-sha <HEAD_SHA>
```

release build/smoke 由 canonical CI 注入 `AUTOMATION_*` 环境；手工本地复现时使用同一 automation 入口，
不伪造通过结果。

## 7. 明确不做

- 不做启动健康失败自动回退、首版 delta、静默强更或跨产品共享 updater。
- 不改变 CLI 的 cwd-scoped 工作区语义。
- 不在 Python fallback 中重新实现版本比较、包 hash、文件替换或 rollback。
- 不修改公共 `scripts/automation_core.py`。
