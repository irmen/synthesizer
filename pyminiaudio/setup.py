import os
import sys
from setuptools import setup

if sys.version_info < (3, 5):
    raise SystemExit("Miniaudio requires Python 3.5 or newer")


miniaudio_path = os.path.abspath(".")  # to make sure the compiler can find the required include files

setup(
      cffi_modules=["./build_ffi_module.py:ffibuilder"],
      include_dirs=[miniaudio_path]
      )
