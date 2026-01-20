# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for The-Uplink application.

Build command:
    pyinstaller The-Uplink.spec
"""

import os
import customtkinter

block_cipher = None

# Get customtkinter path for including its assets
ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Application assets
        ('gui/The_Uplink_App_Icon.ico', 'gui'),
        ('gui/The Uplink logo.png', 'gui'),
        ('gui/arc_raiders.mp3', 'gui'),
        ('gui/arc-raiders-loot.mp3', 'gui'),
        ('gui/arc-raiders-elevator.mp3', 'gui'),
        # CustomTkinter assets (required for themes to work)
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'bcrypt',
        'PIL',
        'PIL._tkinter_finder',
        'customtkinter',
        'sqlite3',
        'winsound',
    ],
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
    [],
    exclude_binaries=True,
    name='The-Uplink',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='gui/The_Uplink_App_Icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='The-Uplink',
)
