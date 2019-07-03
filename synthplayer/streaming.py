"""
Some audio stream related tools, such as decoding any audio file to a stream, and some
simple stream manipulations such as volume (amplitude) control.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import audioop
import subprocess
import shutil
import json
import wave
import os
import sys
import io
import time
import logging
import threading
from collections import namedtuple, defaultdict
from typing import Callable, Generator, BinaryIO, Optional, Union, Iterable, Tuple, List, Dict, Iterator, Any
from types import TracebackType
from .sample import Sample
from . import params
try:
    import miniaudio
except ImportError:
    miniaudio = None


__all__ = ["AudiofileToWavStream", "StreamMixer", "RealTimeMixer", "StreamingSample", "SampleStream",
           "VolumeFilter", "EndlessFramesFilter", "get_file_info"]

log = logging.getLogger("synthplayer.streaming")

AudioFormatInfo = namedtuple("AudioFormatInfo", ["rate", "channels", "sampformat", "bitspersample", "fileformat", "duration", "num_frames"])


antipop_fadein = 0.005
antipop_fadeout = 0.02


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

    def __init__(self, filename: str, outputfilename: str = "", samplerate: int = 0,
                 channels: int = 0, sampleformat: str = "", bitspersample: int = 0,
                 hqresample: bool = True, startfrom: float = 0.0, duration: float = 0.0) -> None:
        self.sample_rate = samplerate or params.norm_samplerate
        self.nchannels = channels or params.norm_nchannels
        self.sample_format = sampleformat or str(8 * params.norm_samplewidth)
        if bitspersample == 0:
            try:
                bitspersample = int(self.sample_format)
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
        probe = None
        try:
            # probe the existing file format, to see if we can avoid needless conversion
            probe = self.probe_format(self.name)
            self.conversion_required = probe.rate != self.sample_rate or probe.channels != self.nchannels \
                                       or probe.sampformat != self.sample_format or probe.fileformat != "wav" \
                                       or self._startfrom > 0 or self._duration > 0 \
                                       or (bitspersample != 0 and probe.bitspersample != 0 and probe.bitspersample != bitspersample)
            self.format_probe = probe
        except (subprocess.CalledProcessError, IOError, OSError):
            pass
        if self.conversion_required:
            if self.sample_rate:
                self.sample_rate = int(self.sample_rate)
                assert 2000 <= self.sample_rate <= 200000
                if hqresample:
                    if self.ffmpeg_executable and not self.supports_hq_resample():
                        raise RuntimeError("ffmpeg not found or it isn't compiled with libsoxr, so hq resampling is not supported")
                    self.resample_options = ["-af", "aresample=resampler=soxr", "-ar", str(self.sample_rate)]
                else:
                    self.resample_options = ["-ar", str(self.sample_rate)]
            if self.nchannels:
                self.nchannels = int(self.nchannels)
                assert 1 <= self.nchannels <= 9
                self.downmix_options = ["-ac", str(self.nchannels)]
            if self.sample_format:
                codec = {
                    "8": "pcm_u8",
                    "16": "pcm_s16le",
                    "24": "pcm_s24le",
                    "32": "pcm_s32le",
                    "float": "pcm_f32le",
                    "alaw": "pcm_alaw",
                    "ulaw": "pcm_mulaw"
                }[self.sample_format]
                self.sampleformat_options = ["-acodec", codec]
        self.start_stream(probe)

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
    def probe_format(cls, filename: str) -> AudioFormatInfo:
        # first try to use miniaudio if it's available
        if miniaudio:
            try:
                info = miniaudio.get_file_info(filename)
            except miniaudio.DecodeError:
                pass   # not a file recognised by miniaudio
            else:
                sample_format = {
                    miniaudio.SampleFormat.UNKNOWN: "?",
                    miniaudio.SampleFormat.UNSIGNED8: "8",
                    miniaudio.SampleFormat.SIGNED16: "16",
                    miniaudio.SampleFormat.SIGNED24: "24",
                    miniaudio.SampleFormat.SIGNED32: "32",
                    miniaudio.SampleFormat.FLOAT32: "float"
                }[info.sample_format]
                return AudioFormatInfo(info.sample_rate, info.nchannels, sample_format, info.sample_width*8,
                                       info.file_format, info.duration, info.num_frames)
        # if it's a .wav, we can open that ourselves
        try:
            with wave.open(filename, "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
                return AudioFormatInfo(wf.getframerate(), wf.getnchannels(),
                                       str(wf.getsampwidth()*8), wf.getsampwidth() * 8, "wav", duration, wf.getnframes())
        except wave.Error:
            pass
        # fall back to the probe tool
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
            if sampleformat == "float":
                bitspersample = 32
            else:
                try:
                    bitspersample = int(sampleformat)
                except ValueError:
                    pass
        fileformat = stream["codec_name"]
        duration = stream.get("duration") or probe["format"].get("duration")
        duration = float(duration) if duration else 0.0
        num_frames = 0
        if duration > 0:
            num_frames = samplerate / duration
        result = AudioFormatInfo(samplerate, nchannels, sampleformat, bitspersample, fileformat, duration, num_frames)
        log.debug("format probe of %s: %s", filename, result)
        return result

    def start_stream(self, info: Optional[AudioFormatInfo]) -> None:
        if not self.conversion_required:
            if self.outputfilename:
                log.debug("direct copy from %s to %s", self.name, self.outputfilename)
                with open(self.name, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return
            log.debug("direct stream input from %s", self.name)
            self.stream = open(self.name, "rb")
            return
        else:
            # first, attempt to stream via miniaudio
            if miniaudio:
                output_format = {
                    "8": miniaudio.SampleFormat.UNSIGNED8,
                    "16": miniaudio.SampleFormat.SIGNED16,
                    "24": miniaudio.SampleFormat.SIGNED24,
                    "32": miniaudio.SampleFormat.SIGNED32,
                    "float": miniaudio.SampleFormat.FLOAT32
                }[self.sample_format]
                try:
                    pcm_gen = miniaudio.stream_file(self.name, output_format, self.nchannels, self.sample_rate)
                    num_frames = 0
                    if info:
                        num_frames = int(info.num_frames * (self.sample_rate / info.rate))
                    self.stream = miniaudio.WavFileReadStream(pcm_gen, self.sample_rate, self.nchannels, output_format, num_frames)
                except miniaudio.DecodeError:
                    pass   # something that miniaudio can't decode, fall back to other methods
                else:
                    return
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
                    self.stream = converter.stdout      # type: ignore
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
                        self.stream = converter.stdout      # type: ignore
                        log.debug("oggdec streaming: %s", " ".join(command))
                    return
                except FileNotFoundError:
                    # somehow the oggdec decoder executable couldn't be launched
                    pass
            raise RuntimeError("ffmpeg or oggdec (vorbis-tools) required for sound file decoding/conversion")

    def read(self, size: int = sys.maxsize) -> Optional[bytes]:
        return self.stream.read(size)   # type: ignore

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


def get_file_info(filename: str) -> AudioFormatInfo:
    return AudiofileToWavStream.probe_format(filename)


class StreamingSample(Sample):
    """
    A sound Sample that does NOT load the full source file/stream into memory,
    but loads and produces chunks of it as they are needed.
    Can be used for the realtime mixing output mode to allow
    on demand decoding and streaming of large sound files.
    """
    def __init__(self, wave_file: Optional[Union[str, BinaryIO]] = None, name: str = "") -> None:
        super().__init__(wave_file, name)

    def view_frame_data(self) -> memoryview:
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

    def chunked_frame_data(self, chunksize: int, repeat: bool = False,
                           stopcondition: Callable[[], bool] = lambda: False) -> Generator[memoryview, None, None]:
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
    def __init__(self, volume: float = 1.0) -> None:
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

    def __enter__(self) -> 'SampleStream':
        return self

    def __exit__(self, exc_type: type, exc_val: Any, exc_tb: TracebackType) -> None:
        self.close()

    def add_frames_filter(self, flter: FramesFilter) -> None:
        flter.set_params(self.frames_per_sample, self.samplerate, self.samplewidth, self.nchannels)
        self.frames_filters.append(flter)

    def add_filter(self, flter: SampleFilter) -> None:
        self.filters.append(flter)

    def __iter__(self) -> Iterator[Sample]:
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

    def __init__(self, streams: Iterable[BinaryIO], endless: bool = False,
                 samplewidth: int = 0, samplerate: int = 0, nchannels: int = 0) -> None:
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

    def add_stream(self, stream: BinaryIO, filters: Optional[Iterable[SampleFilter]] = None,
                   endless: bool = False, end_callback: Optional[Callable[[], None]] = None) -> None:
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

    def add_sample(self, sample: Sample, end_callback: Optional[Callable[[], None]] = None) -> None:
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        stream = io.BytesIO()
        sample.write_wav(stream)
        stream.seek(0, io.SEEK_SET)
        self.add_stream(stream, end_callback=end_callback)

    def __enter__(self) -> 'StreamMixer':
        return self

    def __exit__(self, exc_type: type, exc_val: Any, exc_tb: TracebackType) -> None:
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
            sample = None
            for sample_stream in self.sample_streams:
                try:
                    sample = next(sample_stream)
                except StopIteration:
                    if self.endless:
                        sample = None
                    else:
                        self.remove_stream(sample_stream)
                except (os.error, ValueError):
                    # Problem reading from stream. Assume stream closed.
                    sample = None
                if sample:
                    mixed_sample.mix(sample)
            yield self.timestamp, mixed_sample
            self.timestamp += mixed_sample.duration


class RealTimeMixer:
    """
    Real-time audio sample mixer. Samples are played as soon as they're added into the mix.
    Simply adds a number of samples, clipping if values become too large.
    Produces (via a generator method) chunks of audio stream data to be fed to the sound output stream.
    """
    def __init__(self, chunksize: int, all_played_callback: Callable[[], None], pop_prevention: Optional[bool] = None) -> None:
        self.chunksize = chunksize
        self.all_played_callback = all_played_callback or (lambda: None)
        self.add_lock = threading.Lock()
        self.chunks_mixed = 0
        if pop_prevention is None:
            self.pop_prevention = params.auto_sample_pop_prevention
        else:
            self.pop_prevention = pop_prevention
        self._sid = 0
        self._closed = False
        self.active_samples = {}   # type: Dict[int, Tuple[str, float, Generator[memoryview, None, None]]]
        self.sample_counts = defaultdict(int)  # type: Dict[str, int]
        self.sample_limits = defaultdict(lambda: 9999999)  # type: Dict[str, int]

    @staticmethod
    def antipop_fadein_fadeout(orig_generator: Generator[Union[memoryview, bytes], None, None]) -> Generator[bytes, None, None]:
        # very quickly fades in the first chunk,and fades out the last chunk,
        # to avoid clicks/pops when the sound suddenly starts playing or is stopped.
        chunk = next(orig_generator)
        sample = Sample.from_raw_frames(chunk,      # type: ignore
                                        params.norm_samplewidth,
                                        params.norm_samplerate,
                                        params.norm_nchannels)
        sample.fadein(antipop_fadein)
        fadeout = yield sample.view_frame_data()        # type: ignore
        while not fadeout:
            try:
                fadeout = yield next(orig_generator)    # type: ignore
            except StopIteration:
                return
        chunk = next(orig_generator)
        yield chunk  # to satisfy the result for the .send() on this generator
        sample = Sample.from_raw_frames(chunk,
                                        params.norm_samplewidth,
                                        params.norm_samplerate,
                                        params.norm_nchannels)
        sample.fadeout(antipop_fadeout)
        yield sample.view_frame_data()  # the actual last chunk, faded out

    def add_sample(self, sample: Sample, repeat: bool = False, chunk_delay: int = 0, sid: Optional[int] = None) -> Union[int, None]:
        if not self.allow_sample(sample, repeat):
            return None
        with self.add_lock:
            sample_chunks = sample.chunked_frame_data(chunksize=self.chunksize, repeat=repeat)
            if self.pop_prevention:
                sample_chunks = self.antipop_fadein_fadeout(sample_chunks)  # type: ignore
            self._sid += 1
            sid = sid or self._sid
            self.active_samples[sid] = (sample.name, float(self.chunks_mixed+chunk_delay), sample_chunks)
            self.sample_counts[sample.name] += 1
            return sid

    def allow_sample(self, sample: Sample, repeat: bool = False) -> bool:
        if repeat and self.sample_counts[sample.name] >= 1:  # don't allow more than one repeating sample
            return False
        if not sample.name:
            return True     # samples without a name can't be checked
        return self.sample_counts[sample.name] < self.sample_limits[sample.name]

    def determine_samples_to_mix(self) -> List[Tuple[int, Tuple[str, Generator[memoryview, None, None]]]]:
        active = []
        with self.add_lock:
            for sid, (name, play_at_chunk, sample) in self.active_samples.items():
                if play_at_chunk <= self.chunks_mixed:
                    active.append((sid, (name, sample)))
        return active

    def clear_sources(self) -> None:
        # clears all sources
        with self.add_lock:
            self.active_samples.clear()
            self.sample_counts.clear()
            self.all_played_callback()

    def clear_source(self, sid_or_name: Union[int, str]) -> None:
        # clear a single sample source by its sid or all sources with the sample name
        if isinstance(sid_or_name, int):
            self.remove_sample(sid_or_name)
        else:
            active_samples = self.determine_samples_to_mix()
            for sid, (name, _) in active_samples:
                if name == sid_or_name:
                    self.remove_sample(sid)

    def chunks(self) -> Generator[memoryview, None, None]:
        silence = b"\0" * self.chunksize
        while not self._closed:
            chunks_to_mix = []
            active_samples = self.determine_samples_to_mix()
            for i, (name, s) in active_samples:
                try:
                    chunk = next(s)
                    if len(chunk) > self.chunksize:
                        raise ValueError("chunk from sample is larger than chunksize from mixer (" +
                                         str(len(chunk)) + " vs " + str(self.chunksize) + ")")
                    if len(chunk) < self.chunksize:
                        # pad the chunk with some silence
                        chunk = memoryview(chunk.tobytes() + silence[len(chunk):])
                    chunks_to_mix.append(chunk)
                except StopIteration:
                    self.remove_sample(i, True)
            chunks_to_mix = chunks_to_mix or [silence]      # type: ignore
            assert all(len(c) == self.chunksize for c in chunks_to_mix)
            mixed = chunks_to_mix[0]
            if len(chunks_to_mix) > 1:
                for to_mix in chunks_to_mix[1:]:
                    mixed = audioop.add(mixed, to_mix, params.norm_nchannels)
                mixed = memoryview(mixed)
            self.chunks_mixed += 1
            yield mixed

    def remove_sample(self, sid: int, sample_exhausted: bool = False) -> None:
        def actually_remove(sid: int, name: str) -> None:
            del self.active_samples[sid]
            self.sample_counts[name] -= 1
            if not self.active_samples:
                self.all_played_callback()
        with self.add_lock:
            if sid in self.active_samples:
                name, play_at_chunk, generator = self.active_samples[sid]
                if self.pop_prevention and not sample_exhausted:
                    # first let the generator produce a fadeout
                    try:
                        generator.send("fadeout")       # type: ignore
                    except (TypeError, ValueError, StopIteration):
                        # generator couldn't process the fadeout, just remote the sample...
                        actually_remove(sid, name)
                else:
                    # remove a finished sample (or directly, if no pop prevention active)
                    actually_remove(sid, name)

    def set_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.sample_limits[samplename] = max_simultaneously

    def close(self) -> None:
        self.clear_sources()
        self._closed = True
