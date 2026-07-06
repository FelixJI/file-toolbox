# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec:file-toolbox onedir 便携打包。

调用(由 scripts/build_exe.py 驱动):
    pyinstaller scripts/FileToolbox.spec --distpath dist --workpath build --noconfirm

打包策略(对比旧 Nuitka 方案,核心优势是 C 扩展/运行时 DLL 全自动收集):
  - PIL(Pillow):标准 C 扩展包,collect_all 自动收 _imaging.cp*.pyd。
  - pymupdf/fitz(PyMuPDF):原生绑定体量巨大,Nuitka 编译会 OOM(issue #3291);
    PyInstaller 无编译步骤,collect_all 直接收 .pyd/.dll/.py,无需手工干预。
  - win32com/win32comext/win32/pythoncom/pywintypes(pywin32):COM 自动化运行时。
    PyInstaller 内置 pywin32 hook 会把 pywin32_system32/ 下的 pythoncom3XX.dll、
    pywintypes3XX.dll 自动收进产物根目录(Nuitka 下需手工 copytree,是旧 bug 根源)。
  - PySide6:由 PyInstaller 官方 hook 处理 Qt 插件/资源。
  - pdfplumber/openpyxl/chardet:纯 Python,Analysis 自动追踪即可。

SPECPATH 是本 spec 文件所在目录(scripts/),故 project_root = SPECPATH.parent。
"""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

block_cipher = None

project_root = Path(SPECPATH).parent

# --- 第三方包的完整收集(C 扩展 + 数据文件 + 子模块)---
# PyInstaller 内置 hook 已覆盖大部分,这里对带原生扩展/运行时 DLL 的几个包显式
# collect_all 兜底,确保 .pyd/.dll/数据文件全进产物。
datas: list = []
binaries: list = []
hiddenimports: list = []
for pkg in ("pymupdf", "fitz", "win32com", "win32comext", "win32",
            "pythoncom", "pywintypes", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# CHANGELOG.md 随包:放到 exe 同级("."),供关于页 metadata.get_changelog()
# 回退链第 2 级(Path(sys.executable).parent / "CHANGELOG.md")命中。
datas += [(str(project_root / "CHANGELOG.md"), ".")]

a = Analysis(
    [str(project_root / "file_toolbox" / "gui_entry.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],  # 不排除任何东西,避免漏依赖(产物体积可后期再瘦身)
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FileToolbox",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX 压缩易触发杀软误报,禁用
    console=False,  # GUI 无黑框(等价 Nuitka --windows-console-mode=disable)
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="assets/app.ico",  # 暂无图标,用 PyInstaller 默认;后续补 ico 即可
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FileToolbox",  # 产物目录名 = dist/FileToolbox/
)
