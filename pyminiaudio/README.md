[![saythanks](https://img.shields.io/badge/say-thanks-ff69b4.svg)](https://saythanks.io/to/irmen)
[![Latest Version](https://img.shields.io/pypi/v/miniaudio.svg)](https://pypi.python.org/pypi/miniaudio/)


# Python miniaudio

This module provides:

- the [miniaudio](https://github.com/dr-soft/miniaudio/) cross platform sound playback and conversion library
- its decoders for wav, flac, vorbis and mp3
- python bindings via cffi for much of the functions offered in those libraries


*requires Python 3.5 or newer*. 

Currently, it is only distributed in source form so you need a C compiler to build and install this.
For Linux and Mac this shouldn't be a problem. For Windows users it may be though.
If you're a windows user you should make sure you installed the required tools (Visual Studio or 
the C++ build tools) to be able to compile Python extension modules.
 

Software license for these Python bindings, miniaudio and the decoders: MIT


## todo

- the various format conversion functions aren't properly exposed yet.
- documentation is severely lacking.
- only playback for now, the recording capabilities of miniaudio aren't exposed yet 
