"""
Some audio stream related tools, such as decoding any audio file to a stream, and some
simple stream manipulations such as volume (amplitude) control.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import subprocess
import shutil
import json
import wave
import os
import io
import time
import logging
from collections import namedtuple
from typing import Callable, Generator, BinaryIO, Optional, Union, Iterable, Tuple, List, Dict
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

    def __init__(self, filename: str, outputfilename: str="", samplerate: int=0,
                 channels: int=0, sampleformat: str="", bitspersample: int=0,
                 hqresample: bool=True, startfrom: float=0.0, duration: float=0.0) -> None:
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
        self.stream = None              # type: Optional[BinaryIO]
        self.resample_options = []      # type: List[str]
        self.downmix_options = []       # type: List[str]
        self.sampleformat_options = []  # type: List[str]
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
    def supports_hq_resample(cls) -> bool:
        if cls.ffmpeg_executable:
            try:
                buildconf = subprocess.check_output([cls.ffmpeg_executable, "-v", "error", "-buildconf"]).decode()
                return "--enable-libsoxr" in buildconf
            except FileNotFoundError:
                return False
        return False

    @classmethod
    def probe_format(cls, filename: str) -> AudioFormatProbe:
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

    def start_stream(self) -> Optional[BinaryIO]:
        if not self.conversion_required:
            if self.outputfilename:
                log.debug("direct copy from %s to %s", self.name, self.outputfilename)
                with open(self.name, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return None
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
                    return None
                command.extend(["-f", "wav", "-"])
                log.debug("ffmpeg streaming: %s", " ".join(command))
                try:
                    converter = subprocess.Popen(command, stdin=None, stdout=subprocess.PIPE)
                    self.stream = converter.stdout      # type: ignore
                    return None
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
                        self.stream = converter.stdout      # type: ignore
                        log.debug("oggdec streaming: %s", " ".join(command))
                    return None
                except FileNotFoundError:
                    # somehow the oggdec decoder executable couldn't be launched
                    pass
            raise RuntimeError("ffmpeg or oggdec (vorbis-tools) required for sound file decoding")
        return self.stream

    def read(self, size):
        return self.stream.read(size)

    def close(self) -> None:
        log.debug("closing stream %s", self.name)
        if self.stream:
            self.stream.read(100000)   # read possible surplus data to clean the pipe
            self.stream.close()
            if os.name == "nt":
                time.sleep(0.02)    # windows sometimes keeps the file locked for a bit

    @property
    def closed(self) -> bool:
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
    def __init__(self, wave_file: Union[str, BinaryIO]=None, name: str="") -> None:
        super().__init__(wave_file, name)

    def view_frame_data(self):
        raise NotImplementedError("a streaming sample doesn't have a frame data buffer to view")

    def load_wav(self, file_or_stream: Union[str, BinaryIO]) -> 'Sample':
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
        return self

    def chunked_frame_data(self, chunksize: int, repeat: bool=False,
                           stopcondition: Callable[[], bool]=lambda: False) -> Generator[memoryview, None, None]:
        silence = b"\0" * chunksize
        while True:
            audiodata = self.wave_stream.readframes(chunksize // self.samplewidth // self.nchannels)
            if not audiodata:
                if repeat:
                    self.wave_stream.rewind()
                else:
                    break   # non-repeating source stream exhausted
            if len(audiodata) < chunksize:
                audiodata += silence[len(audiodata):]
            yield memoryview(audiodata)


class FramesFilter:
    def set_params(self, buffer_size: int, samplerate: int, samplewidth: int, nchannels: int) -> None:
        raise NotImplementedError

    def __call__(self, frames: bytes) -> bytes:
        raise NotImplementedError


class SampleFilter:
    def __call__(self, sample: Sample) -> Sample:
        raise NotImplementedError


class EndlessFramesFilter(FramesFilter):
    """
    Turns a frame stream into an endless frame stream by adding silence frames at the end until closed.
    """
    def set_params(self, buffer_size: int, samplerate: int, samplewidth: int, nchannels: int) -> None:
        self.silence_frame = b"\0" * nchannels * samplewidth * buffer_size

    def __call__(self, frames: bytes) -> bytes:
        return frames if frames else self.silence_frame


class VolumeFilter(SampleFilter):
    def __init__(self, volume: float=1.0) -> None:
        self.volume = volume

    def __call__(self, sample: Sample) -> Sample:
        if sample:
            sample.amplify(self.volume)
        return sample


class SampleStream:
    """
    Turns a wav reader that produces frames, or a wav file stream,
    into an iterable producing a stream of Sample objects.
    You can add filters to the stream that process the Sample objects coming trough.
    The buffer size is the number of audio _frames_ (not bytes)
    """
    def __init__(self, wav_reader_or_stream: Union[wave.Wave_read, BinaryIO], frames_per_sample: int) -> None:
        if isinstance(wav_reader_or_stream, io.RawIOBase):
            self.source = wave.open(wav_reader_or_stream, "r")   # type: wave.Wave_read
        else:
            assert isinstance(wav_reader_or_stream, wave.Wave_read)
            self.source = wav_reader_or_stream
        self.samplewidth = self.source.getsampwidth()
        self.samplerate = self.source.getframerate()
        self.nchannels = self.source.getnchannels()
        self.frames_per_sample = frames_per_sample
        self.filters = []           # type: List[SampleFilter]
        self.frames_filters = []    # type: List[FramesFilter]
        self.source.readframes(1)  # warm up the stream

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def add_frames_filter(self, flter: FramesFilter) -> None:
        flter.set_params(self.frames_per_sample, self.samplerate, self.samplewidth, self.nchannels)
        self.frames_filters.append(flter)

    def add_filter(self, flter: SampleFilter) -> None:
        self.filters.append(flter)

    def __iter__(self):
        return self

    def __next__(self) -> Sample:
        frames = self.source.readframes(self.frames_per_sample)
        for ff in self.frames_filters:
            frames = ff(frames)
        if not frames:
            raise StopIteration
        sample = Sample.from_raw_frames(frames, self.samplewidth, self.samplerate, self.nchannels)
        for sf in self.filters:
            sample = sf(sample)
        return sample

    def close(self) -> None:
        self.source.close()


class StreamMixer:
    """
    Mixes one or more wav audio streams into one output.
    Takes ownership of the source streams that are being mixed, and will close them for you as needed.
    """
    buffer_size = 4096   # number of frames in a buffer

    def __init__(self, streams: Iterable[BinaryIO], endless: bool=False,
                 samplewidth: int=0, samplerate: int=0, nchannels: int=0) -> None:
        # assume all wave streams are the same parameters
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.samplerate = samplerate or params.norm_samplerate
        self.nchannels = nchannels or params.norm_nchannels
        self.timestamp = 0.0
        self.endless = endless
        self.sample_streams = []    # type: List[SampleStream]
        self.wrapped_streams = {}   # type: Dict[SampleStream, Tuple[BinaryIO, Optional[Callable[[], None]]]] # (to close stuff properly)
        for stream in streams:
            self.add_stream(stream, None, endless)

    def add_stream(self, stream: BinaryIO, filters: Iterable[SampleFilter]=None,
                   endless: bool=False, end_callback: Callable[[], None]=None) -> None:
        ws = wave.open(stream, 'r')
        ss = SampleStream(ws, self.buffer_size)
        if endless:
            ss.add_frames_filter(EndlessFramesFilter())
        for f in (filters or []):
            ss.add_filter(f)
        self.sample_streams.append(ss)
        self.wrapped_streams[ss] = (stream, end_callback)

    def remove_stream(self, stream: SampleStream) -> None:
        stream.close()
        self.sample_streams.remove(stream)
        if stream in self.wrapped_streams:
            wrapped_stream, end_callback = self.wrapped_streams.pop(stream)
            wrapped_stream.close()
            if end_callback is not None:
                end_callback()

    def add_sample(self, sample: Sample, end_callback: Callable[[], None]=None) -> None:
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

    def close(self) -> None:
        for stream in self.sample_streams:
            stream.close()
        del self.sample_streams

    def __iter__(self) -> Generator[Tuple[float, Sample], None, None]:
        """
        Yields tuple(timestamp, Sample) that represent the mixed audio streams.
        """
        while self.endless or self.sample_streams:
            mixed_sample = Sample.from_raw_frames(b"", self.samplewidth, self.samplerate, self.nchannels)
            for sample_stream in self.sample_streams:
                try:
                    sample = next(sample_stream)        # type: ignore
                except StopIteration:
                    if self.endless:
                        sample = None
                    else:
                        break
                except (os.error, ValueError):
                    # Problem reading from stream. Assume stream closed.
                    sample = None
                if sample:
                    mixed_sample.mix(sample)
                else:
                    self.remove_stream(sample_stream)
            yield self.timestamp, mixed_sample
            self.timestamp += mixed_sample.duration
