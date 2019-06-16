import os
import sys
import re
from setuptools import setup

if sys.version_info < (3, 5):
    raise SystemExit("Miniaudio requires Python 3.5 or newer")

miniaudio_path = os.path.abspath(".")  # to make sure the compiler can find the required include files
PKG_VERSION = re.search(r'^__version__\s*=\s*"(.+)"', open("miniaudio.py", "rt").read(), re.MULTILINE).groups()[0]

setup(
    name="miniaudio",
    version=PKG_VERSION,
    cffi_modules=["build_ffi_module.py:ffibuilder"],
    include_dirs=[miniaudio_path],
    zip_safe=False,
    include_package_data=False,
    py_modules=["miniaudio"],
    install_requires=["cffi>=1.3.0"],
    setup_requires=["cffi>=1.3.0"]
)
