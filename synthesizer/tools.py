"""
Some audio related tools

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import subprocess


__all__ = ["WavFileStream"]


class WavFileStream:
    """
    Streams WAV PCM audio data from the given sound source file.
    If the file is not already a .wav, ffmpeg is used to convert it in the background.
    """
    def __init__(self, filename, ffmpeg_executable=None):
        self.ffmpeg_exe = ffmpeg_executable or "ffmpeg"
        self.filename = filename
        self.stream = None
    def get_stream(self):
        if self.filename.endswith(".wav"):
            self.stream = open(self.filename, "rb")
        else:
            command = [self.ffmpeg_exe, "-hide_banner", "-loglevel", "panic", "-i", self.filename, "-f", "wav", "-"]
            converter = subprocess.Popen(command, stdout=subprocess.PIPE)
            self.stream = converter.stdout
        return self.stream
    def __enter__(self):
        return self.get_stream()
    def __exit__(self, *args):
        self.stream.close()
