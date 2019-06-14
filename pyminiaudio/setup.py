import os
import re
from setuptools import setup

miniaudio_path = os.path.abspath(".")           # to make sure the compiler can find the required include files

PKG_VERSION = re.search(r'^__version__\s*=\s*"(.+)"', open("miniaudio.py", "rt").read(), re.MULTILINE).groups()[0]

setup(name="miniaudio",
      version=PKG_VERSION,
      description="miniaudio audio library and decoders (mp3, flac, ogg vorbis, wav) python bindings",
      author="Irmen de Jong",
      author_email="irmen@razorvine.net",
      license="MIT",
      py_modules=["miniaudio"],
      setup_requires=["cffi>=1.3.0"],
      install_requires=["cffi>=1.3.0"],
      include_package_data=False,
      cffi_modules=["./build_ffi_module.py:ffibuilder"],
      include_dirs=[miniaudio_path]
      )
