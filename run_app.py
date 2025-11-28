# #nuitka-project: --onefile
# nuitka-project: --standalone
# nuitka-project: --output-filename=fictionpub.exe
# nuitka-project: --output-dir=./dist/

# nuitka-project: --windows-console-mode=force
# (disable/force/attach/hide)

# nuitka-project: --lto=yes
# nuitka-project: --assume-yes-for-downloads

# nuitka-project: --enable-plugin=tk-inter

# include resource folder
# nuitka-project: --include-package-data=fictionpub.resources
# nuitka-project: --include-data-dir=fictionpub/resources=fictionpub/resources

# nuitka-project: --static-libpython=auto
# nuitka-project: --follow-imports

# nuitka-project: --mingw64

"""
Entry point for Pyinstaller.
"""

from fictionpub.main import main

if __name__ == "__main__":
    main()
