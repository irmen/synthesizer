import os
import glob
from setuptools import setup, find_packages

miniaudio_path = os.path.abspath(".")           # to make sure the compiler can find the required include files


PKG_NAME = "miniaudio"
PKG_VERSION = "0.1"

setup(name=PKG_NAME,
      version=PKG_VERSION,
      description="miniaudio audio library and decoders (mp3, flac, ogg vorbis, wav) python bindings",
      author="Irmen de Jong",
      py_modules=["miniaudio"],
      setup_requires=["cffi>=1.8.0"],
      install_requires=["cffi>=1.8.0"],
      include_package_data=False,
      cffi_modules=["./build_ffi_module.py:ffibuilder"],
      include_dirs=[miniaudio_path]
      )
