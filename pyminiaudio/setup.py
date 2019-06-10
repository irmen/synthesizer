import os
from setuptools import setup, find_packages

miniaudio_path = os.path.abspath(".")           # to make sure the compiler can find the required include files


setup(name="pyminiaudio",
      version="0.1",
      description="miniaudio decoders (mp3, flac, ogg vorbis, wav) python bindings",
      author="Irmen de Jong",
      py_modules=["miniaudio_decoders"],
      setup_requires=["cffi>=1.8.0"],
      install_requires=["cffi>=1.8.0"],
      include_package_data=False,
      cffi_modules=["./build_decoders_module.py:ffibuilder"],
      include_dirs=[miniaudio_path]
      )
