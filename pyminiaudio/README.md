# Python miniaudio

This module provides:

- the [miniaudio](https://github.com/dr-soft/miniaudio/) cross platform sound playback and conversion library
- its decoders for wav, flac, vorbis and mp3
- python bindings via cffi for much of the functions offered in those libraries


Currently, it is only distributed in source form so you need a C compiler to build and install this.
For Linux and Mac this shouldn't be a problem. For Windows users it may be though.
If you're a windows user you should make sure you installed the required tools (Visual Studio or 
the C++ build tools) to be able to compile Python extension modules.
 

Software license for these Python bindings, miniaudio and the decoders: MIT



## todo

- Windows: Currently there is a problem compiling in the std_vorbis decoder with Msvc on Windows. The compiler stops with a handful of errors in winnt.h
- the various format conversion functions aren't available yet
