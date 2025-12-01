# nuitka-project: --product-name=FictionPub
# nuitka-project: --company-name=TinyRaindrop
# nuitka-project: --file-description="FB2 to EPUB converter"
# nuitka-project: --file-version=1.0.0
# nuitka-project: --product-version=1.0.0

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
# nuitka-project: --include-package-data=fictionpub.terms
# nuitka-project: --include-data-dir=fictionpub/resources=fictionpub/resources
# nuitka-project: --include-data-dir=fictionpub/terms=fictionpub/terms

# nuitka-project: --windows-icon-from-ico=fictionpub/resources/app.ico

# nuitka-project: --static-libpython=auto
# nuitka-project: --follow-imports

"""
Entry point for .exe compilers.
"""

from fictionpub.main import main

if __name__ == "__main__":
    main()
