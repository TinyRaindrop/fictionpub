# -*- mode: python ; coding: utf-8 -*-

import os
from glob import glob

project_root = os.path.abspath('.')

# Paths inside your project
resources_dir = os.path.join(project_root, 'fictionpub', 'resources')
terms_json_dir = os.path.join(project_root, 'fictionpub', 'terms')

# Collect all resource files recursively
resource_files = []
for root, dirs, files in os.walk(resources_dir):
    for file in files:
        src = os.path.join(root, file)
        # Target path inside the executable (relative to dist/)
        rel = os.path.relpath(root, project_root)
        resource_files.append((src, rel))

# Collect all json files in terms/
terms_files = []
for file in glob(os.path.join(terms_json_dir, '*.json')):
    # Put them under fictionpub/terms/ inside the bundled app
    terms_files.append((file, 'fictionpub/terms'))

a = Analysis(
    ['run_app.py'],         # Entry point
    pathex=[project_root],
    binaries=[],
    datas=resource_files + terms_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'email',
        'asyncio',
        'unittest',
        'html',
        'http',
        'pydoc', 
        'setuptools',
        'setuptools._distutils',
        'distutils',
        'pkg_resources',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='fictionpub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # change to False for a GUI app
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='fictionpub'
)
