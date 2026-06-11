# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for healthcheck-gui.exe."""

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# CRITICAL: Add spec directory to search path so PyInstaller finds healthcheck/
# SPECPATH is provided by PyInstaller — the directory containing this .spec file
_here = Path(SPECPATH).absolute()

# Collect healthcheck package data files
datas = [
    (str(_here / 'healthcheck' / 'config.yaml'), 'healthcheck'),
]

# Explicitly list ALL healthcheck submodules (collect_submodules fails for local packages)
hiddenimports = [
    'healthcheck',
    'healthcheck.__init__',
    'healthcheck.dataclasses',
    'healthcheck.config',
    'healthcheck.cpu',
    'healthcheck.memory',
    'healthcheck.disk',
    'healthcheck.smart',
    'healthcheck.network',
    'healthcheck.temperature',
    'healthcheck.report',
    'healthcheck.main',
    'healthcheck.gui',
    'healthcheck.i18n',
    # Dependencies
    'psutil',
    'rich',
    'yaml',
    # Rich submodules (may be needed)
    'rich.console',
    'rich.table',
    'rich.panel',
    'rich.text',
    'rich.layout',
    'rich.box',
    'rich.themes',
    'rich.style',
    'rich.color',
    'rich.measure',
    'rich.segment',
    'rich.protocol',
    'rich.emoji',
    'rich.errors',
    'rich.default_styles',
    'rich.json',
    'rich.pretty',
    'rich.markdown',
    'rich.padding',
    'rich.columns',
    'rich.containers',
    'rich.align',
    'pygments',
    'markdown_it',
]

a = Analysis(
    ['run_gui.py'],
    pathex=[str(_here)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='healthcheck-gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for GUI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
