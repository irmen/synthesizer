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
from synthesizer.sample import Sample


__all__ = ["AudiofileToWavStream", "EndlessWavReader", "StreamMixer", "VolumeFilter", "SampleStream"]


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


class SampleStream:
    """
    Turns a wav reader that produces frames, into a stream of Sample objects.
    You can add filters to the stream that process the Sample objects coming trough.
    """
    def __init__(self, wav_reader, buffer_size):
        self.source = wav_reader
        self.samplewidth = wav_reader.getsampwidth()
        self.samplerate = wav_reader.getframerate()
        self.nchannels = wav_reader.getnchannels()
        self.buffer_size = buffer_size
        self.filters = []
        self.frames_filters = []

    def add_frames_filter(self, filter):
        filter.set_params(self.buffer_size, self.samplerate, self.samplewidth, self.nchannels)
        self.frames_filters.append(filter)

    def add_filter(self, filter):
        filter.set_params(self.buffer_size, self.samplerate, self.samplewidth, self.nchannels)
        self.filters.append(filter)

    def __iter__(self):
        return self

    def __next__(self):
        frames = self.source.readframes(self.buffer_size)
        for filter in self.frames_filters:
            frames = filter(frames)
        if not frames:
            return None
        sample = Sample.from_raw_frames(frames, self.samplewidth, self.samplerate, self.nchannels)
        for filter in self.filters:
            sample = filter(sample)
        return sample

    def close(self):
        self.source.close()


class EndlessFramesFilter:
    """
    Turns a frame stream into an endless frame stream by adding silence frames at the end until closed.
    """
    def set_params(self, buffer_size, samplerate, samplewidth, nchannels):
        self.silence_frame = b"\0" * nchannels * samplewidth * buffer_size

    def __call__(self, frames):
        return frames if frames else self.silence_frame


class VolumeFilter:
    def __init__(self, volume=1.0):
        self.volume = volume

    def set_params(self, buffer_size, samplerate, samplewidth, nchannels):
        pass

    def __call__(self, sample):
        if sample:
            sample.amplify(self.volume)
        return sample


class StreamMixer:
    """
    Mixes one or more wav audio streams into one output.
    Takes ownership of the source streams that are being mixed, and will close them for you as needed.
    """
    buffer_size = 4096   # number of frames in a buffer
    def __init__(self, streams, endless=False, samplewidth=Sample.norm_samplewidth, samplerate=Sample.norm_samplerate, nchannels=Sample.norm_nchannels):
        # assume all wave streams are the same parameters
        self.samplewidth = samplewidth
        self.samplerate = samplerate
        self.nchannels = nchannels
        self.timestamp = 0.0
        self.sample_streams = []
        for stream in streams:
            self.add_stream(stream, endless)
        if len(self.sample_streams) < 1:
            raise ValueError("must have at least one stream")

    def add_stream(self, stream, endless=False):
        ws = wave.open(stream, 'r')
        ss = SampleStream(ws, self.buffer_size)
        if endless:
            ss.add_frames_filter(EndlessFramesFilter())
        # ss.add_filter(VolumeFilter(0.1))
        self.sample_streams.append(ss)

    def remove_stream(self, stream):
        stream.close()
        self.sample_streams.remove(stream)

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
        for stream in self.sample_streams:
            stream.close()
        del self.sample_streams

    def __iter__(self):
        """
        Yields tuple(timestamp, Sample) that represent the mixed audio streams.
        """
        while True:
            mixed_sample = Sample.from_raw_frames(b"", self.samplewidth, self.samplerate, self.nchannels)
            for sample_stream in self.sample_streams:
                sample = next(sample_stream)
                if sample:
                    mixed_sample.mix(sample)
                else:
                    self.remove_stream(sample_stream)
            yield self.timestamp, mixed_sample
            self.timestamp += mixed_sample.duration
