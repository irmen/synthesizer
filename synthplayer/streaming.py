"""
Some audio stream related tools, such as decoding any audio file to a stream, and some
simple stream manipulations such as volume (amplitude) control.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import subprocess
import shutil
import json
import wave
import os
import io
import logging
from collections import namedtuple
from typing import Callable, Generator
from .sample import Sample
from . import params


__all__ = ["AudiofileToWavStream", "StreamMixer", "StreamingSample", "SampleStream",
           "VolumeFilter", "EndlessFramesFilter"]

log = logging.getLogger("synthplayer.streaming")

AudioFormatProbe = namedtuple("AudioFormatProbe", ["rate", "channels", "sampformat", "bitspersample", "fileformat", "duration"])


class AudiofileToWavStream(io.RawIOBase):
    """
    Streams WAV PCM audio data from the given sound source file.
    If the file is not already a .wav, and/or you want to resample it,
    ffmpeg/ffprobe are used to convert it in the background.
    For HQ resampling, ffmpeg has to be built with libsoxr support.
    If ffmpeg is not available, it can use oggdec (from the vorbis-tools package)
    instead to decode .ogg files, if needed. Resampling cannot be performed in this case.

    Input: audio file of any supported format
    Output: stream of audio data in WAV PCM format
    """
    ffmpeg_executable = "ffmpeg"
    ffprobe_executable = "ffprobe"
    oggdec_executable = "oggdec"

    def __init__(self, filename, outputfilename=None, samplerate=0,
                 channels=0, sampleformat="", bitspersample=0, hqresample=True, startfrom=0, duration=0):
        samplerate = samplerate or params.norm_samplerate
        channels = channels or params.norm_nchannels
        sampleformat = sampleformat or str(8*params.norm_samplewidth)
        if bitspersample == 0:
            try:
                bitspersample = int(sampleformat)
            except ValueError:
                pass
        self.name = filename
        if not os.path.isfile(filename):
            raise FileNotFoundError(filename)
        self.outputfilename = outputfilename
        self.stream = None
        self.resample_options = []
        self.downmix_options = []
        self.sampleformat_options = []
        self.conversion_required = True
        self.format_probe = None
        self._startfrom = startfrom
        self._duration = duration
        if self.ffprobe_executable:
            try:
                # probe the existing file format, to see if we can avoid needless conversion
                probe = self.probe_format(self.name)
                self.conversion_required = probe.rate != samplerate or probe.channels != channels \
                    or probe.sampformat != sampleformat or probe.fileformat != "wav" \
                    or self._startfrom > 0 or self._duration > 0 \
                    or (bitspersample != 0 and probe.bitspersample != 0 and probe.bitspersample != bitspersample)
                self.format_probe = probe
            except (subprocess.CalledProcessError, IOError, OSError):
                pass
        if self.conversion_required:
            if samplerate:
                samplerate = int(samplerate)
                assert 2000 <= samplerate <= 200000
                if hqresample:
                    if self.ffmpeg_executable and not self.supports_hq_resample():
                        raise RuntimeError("ffmpeg not found or it isn't compiled with libsoxr, so hq resampling is not supported")
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

    @classmethod
    def supports_hq_resample(cls):
        if cls.ffmpeg_executable:
            try:
                buildconf = subprocess.check_output([cls.ffmpeg_executable, "-v", "error", "-buildconf"]).decode()
                return "--enable-libsoxr" in buildconf
            except FileNotFoundError:
                return False
        return False

    @classmethod
    def probe_format(cls, filename):
        command = [cls.ffprobe_executable, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-i", filename]
        probe = subprocess.check_output(command)
        probe = json.loads(probe.decode())
        stream = [stream for stream in probe["streams"] if stream["codec_type"] == "audio"][0]
        if not stream:
            raise IOError("file contains no audio stream, not supported")
        samplerate = int(stream["sample_rate"])
        nchannels = int(stream["channels"])
        sampleformat = {
            "u8": "8",
            "u8p": "8",
            "s16": "16",
            "s16p": "16",
            "s32": "32",
            "s32p": "32",
            "fltp": "float",
            "flt": "float",
            }.get(stream["sample_fmt"], "<unknown>")
        bitspersample = stream["bits_per_sample"]
        if bitspersample == 0:
            try:
                bitspersample = int(sampleformat)
            except ValueError:
                pass
        fileformat = probe["format"]["format_name"]
        duration = probe["format"].get("duration") or stream.get("duration")
        duration = float(duration) if duration else None
        result = AudioFormatProbe(samplerate, nchannels, sampleformat, bitspersample, fileformat, duration)
        log.debug("format probe of %s: %s", filename, result)
        return result

    def start_stream(self):
        if not self.conversion_required:
            if self.outputfilename:
                log.debug("direct copy from %s to %s", self.name, self.outputfilename)
                with open(self.name, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return
            log.debug("direct stream input from %s", self.name)
            self.stream = open(self.name, "rb")
        else:
            if self.ffmpeg_executable:
                command = [self.ffmpeg_executable, "-v", "fatal", "-hide_banner", "-nostdin"]
                if self._startfrom > 0:
                    command.extend(["-ss", str(self._startfrom)])    # seek start time in seconds
                command.extend(["-i", self.name])
                if self._duration > 0:
                    command.extend(["-to", str(self._duration)])    # clip duration in seconds
                command.extend(self.resample_options)
                command.extend(self.downmix_options)
                command.extend(self.sampleformat_options)
                if self.outputfilename:
                    command.extend(["-y", self.outputfilename])
                    log.debug("ffmpeg file conversion: %s", " ".join(command))
                    subprocess.check_call(command)
                    return
                command.extend(["-f", "wav", "-"])
                log.debug("ffmpeg streaming: %s", " ".join(command))
                try:
                    converter = subprocess.Popen(command, stdin=None, stdout=subprocess.PIPE)
                    self.stream = converter.stdout
                    return
                except FileNotFoundError:
                    # somehow the ffmpeg decoder executable couldn't be launched
                    pass
            if self.oggdec_executable:
                # ffmpeg not available, try oggdec instead (only works on ogg files, but hey we can try)
                try:
                    if self.outputfilename:
                        command = [self.oggdec_executable, "--quiet", "--output", self.outputfilename, self.name]
                        log.debug("oggdec file conversion: %s", " ".join(command))
                        subprocess.check_call(command)
                    else:
                        command = [self.oggdec_executable, "--quiet", "--output", "-", self.name]
                        converter = subprocess.Popen(command, stdin=None, stdout=subprocess.PIPE)
                        self.stream = converter.stdout
                        log.debug("oggdec streaming: %s", " ".join(command))
                    return
                except FileNotFoundError:
                    # somehow the oggdec decoder executable couldn't be launched
                    pass
            raise RuntimeError("ffmpeg or oggdec (vorbis-tools) required for sound file decoding")
        return self.stream

    def read(self, bytes):
        return self.stream.read(bytes)

    def close(self):
        log.debug("closing stream %s", self.name)
        if self.stream:
            self.stream.close()

    @property
    def closed(self):
        if self.stream:
            return self.stream.closed
        else:
            return True


class StreamingSample(Sample):
    """
    A sound Sample that does NOT load the full source file/stream into memory,
    but loads and produces chunks of it as they are needed.
    Can be used for the realtime mixing output mode to allow
    on demand decoding and streaming of large sound files.
    """
    def __init__(self, wave_file=None, name=""):
        self.wave_stream = None
        super().__init__(wave_file, name)

    def load_wav(self, file_or_stream):
        self.wave_stream = wave.open(file_or_stream, "rb")
        if not 2 <= self.wave_stream.getsampwidth() <= 4:
            raise IOError("only supports sample sizes of 2, 3 or 4 bytes")
        if not 1 <= self.wave_stream.getnchannels() <= 2:
            raise IOError("only supports mono or stereo channels")
        filename = file_or_stream if isinstance(file_or_stream, str) else file_or_stream.name
        samp = Sample.from_raw_frames(b"", self.wave_stream.getsampwidth(), self.wave_stream.getframerate(),
                                      self.wave_stream.getnchannels(), filename)
        self.copy_from(samp)
        self.wave_stream.readframes(1)   # warm up the stream

    def chunked_frame_data(self, chunksize: int, repeat: bool=False,
                           stopcondition: Callable[[], bool]=lambda: False) -> Generator[memoryview, None, None]:
        silence = b"\0" * chunksize
        while True:
            audiodata = self.wave_stream.readframes(chunksize // self.samplewidth // self.nchannels)
            if not audiodata:
                break   # source stream exhausted
            if len(audiodata) < chunksize:
                audiodata += silence[len(audiodata):]
            yield memoryview(audiodata)


class SampleStream:
    """
    Turns a wav reader that produces frames, or a wav file stream,
    into a stream of Sample objects.
    You can add filters to the stream that process the Sample objects coming trough.
    """
    def __init__(self, wav_reader_or_stream, buffer_size):
        if isinstance(wav_reader_or_stream, io.RawIOBase):
            self.source = wave.open(wav_reader_or_stream, "r")
        else:
            self.source = wav_reader_or_stream
        self.samplewidth = self.source.getsampwidth()
        self.samplerate = self.source.getframerate()
        self.nchannels = self.source.getnchannels()
        self.buffer_size = buffer_size
        self.filters = []
        self.frames_filters = []
        self.source.readframes(1)  # warm up the stream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

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
            raise StopIteration
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

    def __init__(self, streams, endless=False, samplewidth=0, samplerate=0, nchannels=0):
        # assume all wave streams are the same parameters
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.samplerate = samplerate or params.norm_samplerate
        self.nchannels = nchannels or params.norm_nchannels
        self.timestamp = 0.0
        self.endless = endless
        self.sample_streams = []
        self.wrapped_streams = {}   # samplestream->(wrappedstream, end_callback) (to close stuff properly)
        for stream in streams:
            self.add_stream(stream, None, endless)

    def add_stream(self, stream, filters=None, endless=False, end_callback=None):
        ws = wave.open(stream, 'r')
        ss = SampleStream(ws, self.buffer_size)
        if endless:
            ss.add_frames_filter(EndlessFramesFilter())
        for f in (filters or []):
            ss.add_filter(f)
        self.sample_streams.append(ss)
        self.wrapped_streams[ss] = (stream, end_callback)

    def remove_stream(self, stream):
        stream.close()
        self.sample_streams.remove(stream)
        if stream in self.wrapped_streams:
            wrapped_stream, end_callback = self.wrapped_streams.pop(stream)
            wrapped_stream.close()
            if end_callback is not None:
                end_callback()

    def add_sample(self, sample, end_callback=None):
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        stream = io.BytesIO()
        sample.write_wav(stream)
        stream.seek(0, io.SEEK_SET)
        self.add_stream(stream, end_callback=end_callback)

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
        while self.endless or self.sample_streams:
            mixed_sample = Sample.from_raw_frames(b"", self.samplewidth, self.samplerate, self.nchannels)
            for sample_stream in self.sample_streams:
                try:
                    sample = next(sample_stream)
                except (os.error, ValueError):
                    # Problem reading from stream. Assume stream closed.
                    sample = None
                if sample:
                    mixed_sample.mix(sample)
                else:
                    self.remove_stream(sample_stream)
            yield self.timestamp, mixed_sample
            self.timestamp += mixed_sample.duration
