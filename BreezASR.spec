# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all
import sys

# 跨平台圖示處理
if sys.platform == 'darwin':
    icon_file = 'icon.icns'
elif sys.platform == 'win32':
    icon_file = 'icon.ico'
else:
    icon_file = None

datas = [('transcribe.py', '.')]
binaries = []
hiddenimports = [
    'torch', 
    'torchaudio', 
    'transformers', 
    'customtkinter', 
    'huggingface_hub',
    'transcribe'  # 確保 transcribe.py 被當作模組打包
]
hiddenimports += collect_submodules('torch')
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BreezASR',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_file] if icon_file else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BreezASR',
)

# macOS 專用的 .app bundle
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='BreezASR.app',
        icon='icon.icns',
        bundle_identifier='com.github.xinhonglin.breezasr',
    )
