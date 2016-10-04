"""
Some audiostream related tools

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import subprocess
import shutil
import json
import wave
import os
import io
from functools import namedtuple
from .sample import Sample


__all__ = ["AudiofileToWavStream", "EndlessStream", "EndlessWavReader", "StreamMixer"]


AudioFormatProbe = namedtuple("AudioFormatProbe", ["rate", "channels", "sampformat", "fileformat"])


class AudiofileToWavStream(io.RawIOBase):
    """
    Streams WAV PCM audio data from the given sound source file.
    If the file is not already a .wav, and/or you want to resample it,
    ffmpeg/ffprobe are used to convert it in the background.
    For HQ resampling, ffmpeg has to be built with libsoxr support.

    Input: audio file of any supported format
    Output: stream of audio data in WAV PCM format
    """
    ffmpeg_executable = "ffmpeg"
    ffprobe_executable = "ffprobe"

    def __init__(self, filename, outputfilename=None, samplerate=Sample.norm_samplerate,
                 channels=Sample.norm_nchannels, sampleformat=str(8*Sample.norm_samplewidth), hqresample=True):
        self.filename = filename
        if not os.path.isfile(filename):
            raise FileNotFoundError(filename)
        self.outputfilename = outputfilename
        self.stream = None
        self.resample_options = []
        self.downmix_options = []
        self.sampleformat_options = []
        self.conversion_required = True
        if self.ffprobe_executable:
            try:
                # probe the existing file format, to see if we can avoid needless conversion
                probe = self.probe_format()
                self.conversion_required = probe.rate!=samplerate or probe.channels!=channels \
                                           or probe.sampformat!=sampleformat or probe.fileformat!="wav"
            except (subprocess.CalledProcessError, IOError, OSError):
                pass
        if self.conversion_required:
            if samplerate:
                samplerate = int(samplerate)
                assert 2000 <= samplerate <= 200000
                if hqresample:
                    buildconf = subprocess.check_output([self.ffmpeg_executable, "-v", "error", "-buildconf"]).decode()
                    if "--enable-libsoxr" not in buildconf:
                        raise RuntimeError("ffmpeg isn't compiled with libsoxr, so hq resampling is not supported")
                    self.resample_options = ["-af", "aresample=resampler=soxr", "-ar", str(samplerate)]
                else:
                    self.resample_options = ["-ar", str(samplerate)]
            if channels:
                channels = int(channels)
                assert 1 <= channels <= 9
                self.downmix_options = ["-ac", str(channels)]
            if sampleformat:
                codec = {
                        "8": "pcm_u8",
                        "16": "pcm_s16le",
                        "24": "pcm_s24le",
                        "32": "pcm_s32le",
                        "float": "pcm_f32le",
                        "alaw": "pcm_alaw",
                        "ulaw": "pcm_mulaw"
                    }[sampleformat]
                self.sampleformat_options = ["-acodec", codec]
        self.start_stream()

    def probe_format(self):
        command = [self.ffprobe_executable, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-i", self.filename]
        probe = subprocess.check_output(command)
        probe = json.loads(probe.decode())
        if len(probe["streams"]) > 1:
            raise IOError("audio file contains more than one stream, not supported")
        stream = probe["streams"][0]
        samplerate = int(stream["sample_rate"])
        nchannels = int(stream["channels"])
        sampleformat = {
            "u8": "8",
            "s16": "16",
            "s32": "32",
            "fltp": "float",
            }.get(stream["sample_fmt"], "<unknown>")
        fileformat = probe["format"]["format_name"]
        return AudioFormatProbe(samplerate, nchannels, sampleformat, fileformat)

    def start_stream(self):
        if not self.conversion_required:
            if self.outputfilename:
                with open(self.filename, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return
            self.stream = open(self.filename, "rb")
        else:
            command = [self.ffmpeg_executable, "-v", "error", "-hide_banner", "-loglevel", "error", "-i", self.filename, "-f", "wav"]
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

    def read(self, bytes):
        return self.stream.read(bytes)

    def close(self):
        self.stream.close()


class EndlessStream(io.RawIOBase):
    """
    Turns source stream into an endles stream by adding zero bytes at the end util closed.
    """
    def __init__(self, source):
        self.source = source

    def read(self, size):
        data = self.source.read(size)
        if data:
            return data
        return b"\0" * size

    def close(self):
        self.source.close()


class EndlessWavReader(wave.Wave_read):
    """
    Turns wav reader into endless wav reader by adding silence frames at the end until closed.
    """
    def __init__(self, wav_read):
        self.source = wav_read
        self._nchannels = wav_read._nchannels
        self._nframes = wav_read._nframes
        self._sampwidth = wav_read._sampwidth
        self._framerate = wav_read._framerate
        self._comptype = wav_read._comptype
        self._compname = wav_read._compname
        self.source_exhausted = False

    def readframes(self, nframes):
        if not self.source_exhausted:
            frames = self.source.readframes(nframes)
            if frames:
                return frames
            self.source_exhausted = True
        return b"\0"*self._nchannels*self._sampwidth*nframes  # silence frames

    def rewind(self):
        raise IOError("cannot rewind an infinite wav")

    def getnframes(self):
        raise IOError("cannot get file size of infinite wav")

    def setpos(self, pos):
        raise IOError("cannot seek in infinite wav")

    def close(self):
        self.source.close()


class StreamMixer:
    """
    Mixes one or more wav audio streams into one output.
    Takes ownership of the source streams that are being mixed, and will close them for you as needed.
    """
    buffer_size = 4096   # number of frames in a buffer
    def __init__(self, streams, endless=False, samplewidth=Sample.norm_samplewidth, samplerate=Sample.norm_samplerate, nchannels=Sample.norm_nchannels):
        self.wave_streams = []
        for stream in streams:
            self.add_stream(stream, endless)
        if len(self.wave_streams) < 1:
            raise ValueError("must have at least one stream")
        # assume all wave streams are the same parameters
        self.samplewidth = samplewidth
        self.samplerate = samplerate
        self.nchannels = nchannels
        self.timestamp = 0.0

    def add_stream(self, stream, endless=False):
        ws = wave.open(stream, 'r')
        if endless:
            ws = EndlessWavReader(ws)
        self.wave_streams.append(ws)

    def remove_stream(self, stream):
        stream.close()
        self.wave_streams.remove(stream)

    def add_sample(self, sample):
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        stream = io.BytesIO()
        sample.write_wav(stream)
        stream.seek(0, io.SEEK_SET)
        self.add_stream(stream)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        for stream in self.wave_streams:
            stream.close()
        del self.wave_streams

    def __iter__(self):
        """
        Yields tuple(timestamp, Sample) that represent the mixed audio streams.
        """
        while True:
            stream_frames = {ws: ws.readframes(self.buffer_size) for ws in self.wave_streams}
            mixed_sample = None
            for ws, frames in stream_frames.items():
                if len(frames)==0:
                    self.remove_stream(ws)
                else:
                    sample = Sample.from_raw_frames(frames, self.samplewidth, self.samplerate, self.nchannels)
                    if mixed_sample:
                        mixed_sample.mix(sample)
                    else:
                        mixed_sample = sample
            if not mixed_sample:
                break
            self.timestamp += mixed_sample.duration
            yield self.timestamp, mixed_sample
