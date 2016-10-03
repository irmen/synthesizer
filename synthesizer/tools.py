"""
Some audio related tools

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import subprocess
import shutil


__all__ = ["AudiofileToWavStream"]


class AudiofileToWavStream:
    """
    Streams WAV PCM audio data from the given sound source file.
    If the file is not already a .wav, and/or you want to resample it,
    ffmpeg is used to convert it in the background.
    """
    ffmpeg_executable = "ffmpeg"
    ffprobe_executable = "ffprobe"

    def __init__(self, filename, outputfilename=None, samplerate=None, channels=None, sampleformat=None, hqresample=True):
        self.filename = filename
        self.outputfilename = outputfilename
        probe_samplerate, probe_channels, probe_sampleformat = self.probe_format()
        self.stream = None
        self.resample_options = []
        self.downmix_options = []
        self.sampleformat_options = []
        if samplerate:
            samplerate = int(samplerate)
            assert 2000 <= samplerate <= 200000
            if hqresample:
                self.resample_options = ["-af", "aresample=resampler=soxr", "-ar", str(samplerate)]
            else:
                self.resample_options = ["-ar", str(samplerate)]
        if channels:
            channels = int(channels)
            assert 1 <= channels <= 9
            self.downmix_options = ["-ac", str(channels)]
        if sampleformat:
            sampleformat = {
                    "8": "pcm_u8",
                    "16": "pcm_s16le",
                    "24": "pcm_s24le",
                    "32": "pcm_s32le",
                    "float": "pcm_f32le",
                    "alaw": "pcm_alaw",
                    "ulaw": "pcm_mulaw"
                }[sampleformat]
            self.sampleformat_options = ["-acodec", sampleformat]

    def probe_format(self):
        return None, None, None

    def convert(self):
        if self.filename.endswith(".wav") and not self.resample_options and not self.downmix_options:
            if self.outputfilename:
                with open(self.filename, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return
            print("direct open")  # XXX
            self.stream = open(self.filename, "rb")
        else:
            command = [self.ffmpeg_executable, "-v", "error", "-hide_banner", "-loglevel", "panic", "-i", self.filename, "-f", "wav"]
            command.extend(self.resample_options)
            command.extend(self.downmix_options)
            command.extend(self.sampleformat_options)
            if self.outputfilename:
                command.extend(["-y", self.outputfilename])
                subprocess.check_call(command)
                return
            command.append("-")
            converter = subprocess.Popen(command, stdout=subprocess.PIPE)
            self.stream = converter.stdout
        return self.stream

    def __enter__(self):
        if self.outputfilename:
            raise RuntimeError("convert to file cannot be used as a contextmanager")
        return self.convert()

    def __exit__(self, *args):
        self.stream.close()
