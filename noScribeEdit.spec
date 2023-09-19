# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['noScribeEdit.py'],
    pathex=[],
    binaries=[('C:/Users/kai/Documents/Programmierung/2023_WhisperTranscribe/noScribeEditor/ffmpeg_win/ffmpeg.exe','ffmpeg_win'),
        ('C:/Users/kai/Documents/Programmierung/2023_WhisperTranscribe/noScribeEditor/ffmpeg_win/ffplay.exe','ffmpeg_win')],
    datas=[('C:/Users/kai/Documents/Programmierung/2023_WhisperTranscribe/noScribeEditor/noScribeEditLogo.png', '.')],
    hiddenimports=[],
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
    name='noScribeEdit',
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
    icon='noScribeEditLogo.ico'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='noScribeEdit',
)
