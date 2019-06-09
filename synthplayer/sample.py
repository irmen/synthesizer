"""
Sample and Sample-output related code.
No actual audio library dependent playback code is present in this module.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import sys
import wave
import audioop
import array
import math
import itertools
from typing import Callable, Generator, Iterable, Any, Tuple, Union, Optional, BinaryIO, Sequence, Iterator
from . import params
from .oscillators import Oscillator
try:
    import numpy
except ImportError:
    numpy = None


__all__ = ["Sample", "LevelMeter"]


samplewidths_to_arraycode = {
    1: 'b',
    2: 'h',
    4: 'l'    # or 'i' on 64 bit systems
}

# the actual array type code for the given sample width varies
if array.array('i').itemsize == 4:
    samplewidths_to_arraycode[4] = 'i'


class Sample:
    """
    Audio sample data. Supports integer sample formats of 2, 3 and 4 bytes per sample (no floating-point).
    Most operations modify the sample data in place (if it's not locked) and return the sample object,
    so you can easily chain several operations.
    """
    def __init__(self, wave_file: Optional[Union[str, BinaryIO]] = None, name: str = "",
                 samplerate: int = 0, nchannels: int = 0, samplewidth: int = 0) -> None:
        """Creates a new empty sample, or loads it from a wav file."""
        self.name = name
        self.__locked = False
        self.__samplerate = self.__nchannels = self.__samplewidth = 0
        if wave_file:
            self.load_wav(wave_file)
            if isinstance(wave_file, str):
                self.__filename = wave_file
            else:
                self.__filename = wave_file.name
            assert 1 <= self.__nchannels <= 2
            assert 2 <= self.__samplewidth <= 4
            assert self.__samplerate > 1
        else:
            self.__samplerate = samplerate or params.norm_samplerate
            self.__nchannels = nchannels or params.norm_nchannels
            self.__samplewidth = samplewidth or params.norm_samplewidth
            self.__frames = b""
            self.__filename = ""

    def __repr__(self) -> str:
        locked = " (locked)" if self.__locked else ""
        return "<Sample '{6:s}' at 0x{0:x}, {1:g} seconds, {2:d} channels, {3:d} bits, rate {4:d}{5:s}>"\
            .format(id(self), self.duration, self.__nchannels, 8*self.__samplewidth, self.__samplerate, locked, self.name)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Sample):
            return False
        return self.__samplewidth == other.__samplewidth and \
            self.__samplerate == other.__samplerate and \
            self.__nchannels == other.__nchannels and \
            self.__frames == other.__frames

    @classmethod
    def from_raw_frames(cls, frames: Union[bytes, list, memoryview], samplewidth: int, samplerate: int,
                        numchannels: int, name: str = "") -> 'Sample':
        """Creates a new sample directly from the raw sample data."""
        assert 1 <= numchannels <= 2
        assert 2 <= samplewidth <= 4
        assert samplerate > 1
        s = cls(name=name)
        if isinstance(frames, (list, memoryview)):
            s.__frames = bytes(frames)
        else:
            s.__frames = frames
        s.__samplerate = int(samplerate)
        s.__samplewidth = int(samplewidth)
        s.__nchannels = int(numchannels)
        return s

    @classmethod
    def from_array(cls, array_or_list: Sequence[Union[int, float]], samplerate: int, numchannels: int, name: str = "") -> 'Sample':
        assert 1 <= numchannels <= 2
        assert samplerate > 1
        if isinstance(array_or_list, list):
            try:
                array_or_list = cls.get_array(2, array_or_list)
            except OverflowError:
                array_or_list = cls.get_array(4, array_or_list)
        elif numpy:
            if isinstance(array_or_list, numpy.ndarray) and any(array_or_list):
                if not isinstance(array_or_list[0], (int, numpy.integer)):
                    raise TypeError("the sample values must be integer")
        else:
            if any(array_or_list):
                if type(array_or_list[0]) is not int:
                    raise TypeError("the sample values must be integer")
        samplewidth = array_or_list.itemsize
        assert 2 <= samplewidth <= 4
        frames = array_or_list.tobytes()
        if sys.byteorder == "big":
            frames = audioop.byteswap(frames, samplewidth)
        return Sample.from_raw_frames(frames, samplewidth, samplerate, numchannels, name=name)

    @classmethod
    def from_osc_block(cls, block: Iterable[float], samplerate: int, amplitude_scale: Optional[float] = None,
                       samplewidth: int = params.norm_samplewidth) -> 'Sample':
        amplitude_scale = amplitude_scale or 2 ** (8 * samplewidth - 1)
        if amplitude_scale and amplitude_scale != 1.0:
            block = [amplitude_scale * v for v in block]
        intblk = list(map(int, block))
        return cls.from_array(intblk, samplerate, 1)

    @classmethod
    def from_oscillator(cls, osc: Oscillator, duration: float, amplitude_scale: Optional[float] = None,
                        samplewidth: int = params.norm_samplewidth) -> 'Sample':
        amplitude_scale = amplitude_scale or 2 ** (8 * samplewidth - 1)
        required_samples = int(duration * osc.samplerate)
        num_blocks, last_block = divmod(required_samples, params.norm_osc_blocksize)
        if last_block > 0:
            num_blocks += 1
        block_gen = osc.blocks()
        sample = cls(None, osc.__class__.__name__, samplerate=osc.samplerate, nchannels=1, samplewidth=samplewidth)
        if num_blocks > 0:
            for block in block_gen:
                num_blocks -= 1
                if num_blocks == 0:
                    block = block[:last_block]
                sample.join(Sample.from_osc_block(block, osc.samplerate, amplitude_scale, samplewidth))
                if num_blocks == 0:
                    break
        return sample

    @property
    def samplewidth(self) -> int:
        return self.__samplewidth

    @property
    def samplerate(self) -> int:
        """You can also set this to a new value, but that will directly affect the pitch and the duration of the sample."""
        return self.__samplerate

    @samplerate.setter
    def samplerate(self, rate: int) -> None:
        assert rate > 0
        self.__samplerate = int(rate)

    @property
    def nchannels(self) -> int:
        return self.__nchannels

    @property
    def filename(self) -> str:
        return self.__filename

    @property
    def duration(self) -> float:
        return len(self.__frames) / self.__samplerate / self.__samplewidth / self.__nchannels

    @property
    def maximum(self) -> int:
        return audioop.max(self.__frames, self.samplewidth)     # type: ignore

    @property
    def rms(self) -> float:
        return audioop.rms(self.__frames, self.samplewidth)     # type: ignore

    @property
    def level_db_peak(self) -> Tuple[float, float]:
        return self.__db_level(False)

    @property
    def level_db_rms(self) -> Tuple[float, float]:
        return self.__db_level(True)

    def __db_level(self, rms_mode: bool = False) -> Tuple[float, float]:
        """
        Returns the average audio volume level measured in dB (range -60 db to 0 db)
        If the sample is stereo, you get back a tuple: (left_level, right_level)
        If the sample is mono, you still get a tuple but both values will be the same.
        This method is probably only useful if processed on very short sample fragments in sequence,
        so the db levels could be used to show a level meter for the duration of the sample.
        """
        maxvalue = 2**(8*self.__samplewidth-1)
        if self.nchannels == 1:
            if rms_mode:
                peak_left = peak_right = (audioop.rms(self.__frames, self.__samplewidth)+1)/maxvalue
            else:
                peak_left = peak_right = (audioop.max(self.__frames, self.__samplewidth)+1)/maxvalue
        else:
            left_frames = audioop.tomono(self.__frames, self.__samplewidth, 1, 0)
            right_frames = audioop.tomono(self.__frames, self.__samplewidth, 0, 1)
            if rms_mode:
                peak_left = (audioop.rms(left_frames, self.__samplewidth)+1)/maxvalue
                peak_right = (audioop.rms(right_frames, self.__samplewidth)+1)/maxvalue
            else:
                peak_left = (audioop.max(left_frames, self.__samplewidth)+1)/maxvalue
                peak_right = (audioop.max(right_frames, self.__samplewidth)+1)/maxvalue
        # cut off at the bottom at -60 instead of all the way down to -infinity
        return max(20.0*math.log(peak_left, 10), -60.0), max(20.0*math.log(peak_right, 10), -60.0)

    def __len__(self) -> int:
        """returns the number of sample frames (not the number of bytes!)"""
        return len(self.__frames) // self.__samplewidth // self.__nchannels

    def view_frame_data(self) -> memoryview:
        """return a memoryview on the raw frame data."""
        return memoryview(self.__frames)

    def chunked_frame_data(self, chunksize: int, repeat: bool = False,
                           stopcondition: Callable[[], bool] = lambda: False) -> Generator[memoryview, None, None]:
        """
        Generator that produces chunks of raw frame data bytes of the given length.
        Stops when the stopcondition function returns True or the sample runs out,
        unless repeat is set to True to let it loop endlessly.
        This is used by the realtime mixing output mode, which processes sounds in small chunks.
        """
        if repeat:
            # continuously repeated
            bdata = self.__frames
            if len(bdata) < chunksize:
                bdata = bdata * int(math.ceil(chunksize / len(bdata)))
            length = len(bdata)
            bdata += bdata[:chunksize]
            mdata = memoryview(bdata)
            i = 0
            while not stopcondition():
                yield mdata[i: i + chunksize]
                i = (i + chunksize) % length
        else:
            # one-shot
            mdata = memoryview(self.__frames)
            i = 0
            while i < len(mdata) and not stopcondition():
                yield mdata[i: i + chunksize]
                i += chunksize

    def get_frame_array(self) -> 'array.ArrayType[int]':
        """Returns the sample values as array. Warning: this can copy large amounts of data."""
        return Sample.get_array(self.samplewidth, self.__frames)

    def get_frames_numpy_float(self) -> 'numpy.array':
        """return the sample values as a numpy float32 array (0.0 ... 1.0) with shape frames * channels.
         (if numpy is available)"""
        if numpy:
            maxsize = 2**(8*self.__samplewidth-1)
            datatype = {
                1: numpy.int8,
                2: numpy.int16,
                4: numpy.int32
            }[self.samplewidth]
            na = numpy.frombuffer(self.__frames, dtype=datatype).reshape((-1, self.nchannels))
            return na.astype(numpy.float32) / float(maxsize)
        else:
            raise RuntimeError("numpy is not available")

    @staticmethod
    def get_array(samplewidth: int, initializer: Optional[Iterable[int]] = None) -> 'array.ArrayType[int]':
        """Returns an array with the correct type code, optionally initialized with values."""
        arraycode = samplewidths_to_arraycode[samplewidth]
        return array.array(arraycode, initializer or [])

    def copy(self) -> 'Sample':
        """Returns a copy of the sample (unlocked)."""
        cpy = self.__class__()
        cpy.copy_from(self)
        return cpy

    def copy_from(self, other: 'Sample') -> 'Sample':
        """Overwrite the current sample with a copy of the other."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.__frames = other.__frames
        self.__samplewidth = other.__samplewidth
        self.__samplerate = other.__samplerate
        self.__nchannels = other.__nchannels
        self.__filename = other.__filename
        self.name = other.name
        return self

    def lock(self) -> 'Sample':
        """Lock the sample against modifications."""
        self.__locked = True
        return self

    def frame_idx(self, seconds: float) -> int:
        """Calculate the raw frame bytes index for the sample at the given timestamp."""
        return self.nchannels*self.samplewidth*int(self.samplerate*seconds)

    def load_wav(self, file_or_stream: Union[str, BinaryIO]) -> 'Sample':
        """Loads sample data from the wav file. You can use a filename or a stream object."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        with wave.open(file_or_stream) as w:
            if not 2 <= w.getsampwidth() <= 4:
                raise IOError("only supports sample sizes of 2, 3 or 4 bytes")
            if not 1 <= w.getnchannels() <= 2:
                raise IOError("only supports mono or stereo channels")
            self.__nchannels = w.getnchannels()
            self.__samplerate = w.getframerate()
            self.__samplewidth = w.getsampwidth()
            nframes = w.getnframes()
            if nframes*self.__nchannels*self.__samplewidth > 2**26:
                # Requested number of frames is way to large. Probably dealing with a stream.
                # Try to read it in chunks of 1 Mb each and hope the stream is not infinite.
                self.__frames = bytearray()
                while True:
                    chunk = w.readframes(1024*1024)
                    self.__frames.extend(chunk)
                    if not chunk:
                        break
            else:
                self.__frames = w.readframes(nframes)
            return self

    def write_wav(self, file_or_stream: Union[str, BinaryIO]) -> None:
        """Write a wav file with the current sample data. You can use a filename or a stream object."""
        with wave.open(file_or_stream, "wb") as out:
            out.setparams((self.nchannels, self.samplewidth, self.samplerate, 0, "NONE", "not compressed"))
            out.writeframes(self.__frames)

    @classmethod
    def wave_write_begin(cls, filename: str, first_sample: 'Sample') -> wave.Wave_write:
        """
        Part of the sample stream output api: begin writing a sample to an output file.
        Returns the open file for future writing.
        """
        out = wave.open(filename, "wb")     # type: wave.Wave_write
        out.setnchannels(first_sample.nchannels)
        out.setsampwidth(first_sample.samplewidth)
        out.setframerate(first_sample.samplerate)
        return out

    @classmethod
    def wave_write_append(cls, out: wave.Wave_write, sample: 'Sample') -> None:
        """Part of the sample stream output api: write more sample data to an open output stream."""
        out.writeframesraw(sample.__frames)

    @classmethod
    def wave_write_end(cls, out: wave.Wave_write) -> None:
        """Part of the sample stream output api: finalize and close the open output stream."""
        out.writeframes(b"")  # make sure the updated header gets written
        out.close()

    def write_frames(self, stream: BinaryIO) -> None:
        """Write the raw sample data to the output stream."""
        stream.write(self.__frames)

    def normalize(self) -> 'Sample':
        """
        Normalize the sample, meaning: convert it to the default samplerate, sample width and number of channels.
        When mixing samples, they should all have the same properties, and this method is ideal to make sure of that.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.resample(params.norm_samplerate)
        if self.samplewidth != params.norm_samplewidth:
            # Convert to 16 bit sample size.
            self.__frames = audioop.lin2lin(self.__frames, self.samplewidth, params.norm_samplewidth)
            self.__samplewidth = params.norm_samplewidth
        if self.nchannels == 1:
            # convert to stereo
            self.__frames = audioop.tostereo(self.__frames, self.samplewidth, 1, 1)
            self.__nchannels = 2
        return self

    def resample(self, samplerate: int) -> 'Sample':
        """
        Resamples to a different sample rate, without changing the pitch and duration of the sound.
        The algorithm used is simple, and it will cause a loss of sound quality.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if samplerate == self.__samplerate:
            return self
        self.__frames = audioop.ratecv(self.__frames, self.samplewidth, self.nchannels, self.samplerate, samplerate, None)[0]
        self.__samplerate = samplerate
        return self

    def speed(self, speed: float) -> 'Sample':
        """
        Changes the playback speed of the sample, without changing the sample rate.
        This will change the pitch and duration of the sound accordingly.
        The algorithm used is simple, and it will cause a loss of sound quality.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert speed > 0
        if speed == 1.0:
            return self
        rate = self.samplerate
        self.__frames = audioop.ratecv(self.__frames, self.samplewidth, self.nchannels, int(self.samplerate*speed), rate, None)[0]
        self.__samplerate = rate
        return self

    def make_32bit(self, scale_amplitude: bool = True) -> 'Sample':
        """
        Convert to 32 bit integer sample width, usually also scaling the amplitude to fit in the new 32 bits range.
        Not scaling the amplitude means that the sample values will remain in their original range (usually 16 bit).
        This is ideal to create sample value headroom to mix multiple samples together without clipping or overflow issues.
        Usually after mixing you will convert back to 16 bits using maximized amplitude to have no quality loss.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.__frames = self.get_32bit_frames(scale_amplitude)
        self.__samplewidth = 4
        return self

    def get_32bit_frames(self, scale_amplitude: bool = True) -> bytes:
        """Returns the raw sample frames scaled to 32 bits. See make_32bit method for more info."""
        if self.samplewidth == 4:
            return self.__frames
        frames = audioop.lin2lin(self.__frames, self.samplewidth, 4)   # type: bytes
        if not scale_amplitude:
            # we need to scale back the sample amplitude to fit back into 24/16/8 bit range
            factor = 1.0/2**(8*abs(self.samplewidth-4))
            frames = audioop.mul(frames, 4, factor)
        return frames

    def make_16bit(self, maximize_amplitude: bool = True) -> 'Sample':
        """
        Convert to 16 bit sample width, usually by using a maximized amplification factor to
        scale into the full 16 bit range without clipping or overflow.
        This is used for example to downscale a 32 bits mixed sample back into 16 bit width.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.samplewidth >= 2
        if maximize_amplitude:
            self.amplify_max()
        if self.samplewidth > 2:
            self.__frames = audioop.lin2lin(self.__frames, self.samplewidth, 2)
            self.__samplewidth = 2
        return self

    def amplify_max(self) -> 'Sample':
        """Amplify the sample to maximum volume without clipping or overflow happening."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        max_amp = audioop.max(self.__frames, self.samplewidth)
        max_target = 2 ** (8 * self.samplewidth - 1) - 2
        if max_amp > 0:
            factor = max_target/max_amp
            self.__frames = audioop.mul(self.__frames, self.samplewidth, factor)
        return self

    def amplify(self, factor: float) -> 'Sample':
        """Amplifies (multiplies) the sample by the given factor. May cause clipping/overflow if factor is too large."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.__frames = audioop.mul(self.__frames, self.samplewidth, factor)
        return self

    def at_volume(self, volume: float) -> 'Sample':
        """
        Returns a copy of the sample at the given volume level 0-1, leaves original untouched.
        This is a special method (next to amplify) because often the same sample will be used
        at different volume levels, and it is cumbersome to drag copies around for every volume desired.
        This also enables you to use this on locked samples.
        """
        cpy = self.copy()
        cpy.amplify(volume)
        return cpy

    def clip(self, start_seconds: float, end_seconds: float) -> 'Sample':
        """Keep only a given clip from the sample."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert end_seconds >= start_seconds
        start = self.frame_idx(start_seconds)
        end = self.frame_idx(end_seconds)
        self.__frames = self.__frames[start:end]
        return self

    def split(self, seconds: float) -> 'Sample':
        """Splits the sample in two parts, keep the first and return the chopped off bit at the end."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        end = self.frame_idx(seconds)
        if end != len(self.__frames):
            chopped = self.copy()
            chopped.__frames = self.__frames[end:]
            self.__frames = self.__frames[:end]
            return chopped
        return Sample.from_raw_frames(b"", self.__samplewidth, self.__samplerate, self.__nchannels)

    def add_silence(self, seconds: float, at_start: bool = False) -> 'Sample':
        """Add silence at the end (or at the start)"""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        required_extra = self.frame_idx(seconds)
        if at_start:
            self.__frames = b"\0"*required_extra + self.__frames
        else:
            self.__frames += b"\0"*required_extra
        return self

    def join(self, other: 'Sample') -> 'Sample':
        """Add another sample at the end of the current one. The other sample must have the same properties."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.samplewidth == other.samplewidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        self.__frames += other.__frames
        return self

    def fadeout(self, seconds: float, target_volume: float = 0.0) -> 'Sample':
        """Fade the end of the sample out to the target volume (usually zero) in the given time."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if not self.__frames:
            return self
        seconds = min(seconds, self.duration)
        i = self.frame_idx(self.duration-seconds)
        begin = self.__frames[:i]
        end = self.__frames[i:]  # we fade this chunk
        numsamples = len(end)/self.__samplewidth
        decrease = 1.0-target_volume
        _sw = self.__samplewidth     # optimization
        _getsample = audioop.getsample   # optimization
        faded = Sample.get_array(_sw, [int(_getsample(end, _sw, i)*(1.0-i*decrease/numsamples)) for i in range(int(numsamples))])
        end = faded.tobytes()
        if sys.byteorder == "big":
            end = audioop.byteswap(end, self.__samplewidth)
        self.__frames = begin + end
        return self

    def fadein(self, seconds: float, start_volume: float = 0.0) -> 'Sample':
        """Fade the start of the sample in from the starting volume (usually zero) in the given time."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if not self.__frames:
            return self
        seconds = min(seconds, self.duration)
        i = self.frame_idx(seconds)
        begin = self.__frames[:i]  # we fade this chunk
        end = self.__frames[i:]
        numsamples = len(begin)/self.__samplewidth
        increase = 1.0-start_volume
        _sw = self.__samplewidth     # optimization
        _getsample = audioop.getsample   # optimization
        _incr = increase/numsamples    # optimization
        faded = Sample.get_array(_sw, [int(_getsample(begin, _sw, i)*(i*_incr+start_volume)) for i in range(int(numsamples))])
        begin = faded.tobytes()
        if sys.byteorder == "big":
            begin = audioop.byteswap(begin, self.__samplewidth)
        self.__frames = begin + end
        return self

    def modulate_amp(self, modulation_source: Union[Oscillator, Sequence[float], 'Sample', Iterator[float]]) -> 'Sample':
        """
        Perform amplitude modulation by another waveform or oscillator.
        You can use a Sample (or array of sample values) or an oscillator as modulator.
        If you use a Sample (or array), it will be cycled if needed and its maximum amplitude
        is scaled to be 1.0, effectively using it as if it was an oscillator.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        frames = self.get_frame_array()
        if isinstance(modulation_source, (Sample, list, array.array)):
            # modulator is a waveform, turn that into an 'oscillator' ran
            if isinstance(modulation_source, Sample):
                modulation_source = modulation_source.get_frame_array()
            biggest = max(max(modulation_source), abs(min(modulation_source)))
            actual_modulator = (v/biggest for v in itertools.cycle(modulation_source))   # type: ignore
        elif isinstance(modulation_source, Oscillator):
            actual_modulator = itertools.chain.from_iterable(modulation_source.blocks())    # type: ignore
        else:
            actual_modulator = iter(modulation_source)  # type: ignore
        for i in range(len(frames)):
            frames[i] = int(frames[i] * next(actual_modulator))
        self.__frames = frames.tobytes()
        if sys.byteorder == "big":
            self.__frames = audioop.byteswap(self.__frames, self.__samplewidth)
        return self

    def reverse(self) -> 'Sample':
        """Reverse the sound."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.__frames = audioop.reverse(self.__frames, self.__samplewidth)
        return self

    def invert(self) -> 'Sample':
        """Invert every sample value around 0."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        return self.amplify(-1)

    def delay(self, seconds: float, keep_length: bool = False) -> 'Sample':
        """
        Delay the sample for a given time (inserts silence).
        If delay<0, instead, skip a bit from the start.
        This is a nice wrapper around the add_silence and clip functions.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if seconds > 0:
            if keep_length:
                num_frames = len(self.__frames)
                self.add_silence(seconds, at_start=True)
                self.__frames = self.__frames[:num_frames]
                return self
            else:
                return self.add_silence(seconds, at_start=True)
        elif seconds < 0:
            seconds = -seconds
            if keep_length:
                num_frames = len(self.__frames)
                self.add_silence(seconds)
                self.__frames = self.__frames[len(self.__frames)-num_frames:]
                return self
            else:
                self.__frames = self.__frames[self.frame_idx(seconds):]
        return self

    def bias(self, bias: int) -> 'Sample':
        """Add a bias constant to each sample value."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        self.__frames = audioop.bias(self.__frames, self.__samplewidth, bias)
        return self

    def mono(self, left_factor: float = 1.0, right_factor: float = 1.0) -> 'Sample':
        """Make the sample mono (1-channel) applying the given left/right channel factors when downmixing"""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if self.__nchannels == 1:
            return self
        if self.__nchannels == 2:
            self.__frames = audioop.tomono(self.__frames, self.__samplewidth, left_factor, right_factor)
            self.__nchannels = 1
            return self
        raise ValueError("sample must be stereo or mono already")

    def left(self) -> 'Sample':
        """Only keeps left channel."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.__nchannels == 2
        return self.mono(1.0, 0)

    def right(self) -> 'Sample':
        """Only keeps right channel."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.__nchannels == 2
        return self.mono(0, 1.0)

    def stereo(self, left_factor: float = 1.0, right_factor: float = 1.0) -> 'Sample':
        """
        Turn a mono sample into a stereo one with given factors/amplitudes for left and right channels.
        Note that it is a fast but simplistic conversion; the waveform in both channels is identical
        so you may suffer from phase cancellation when playing the resulting stereo sample.
        If the sample is already stereo, the left/right channel separation is changed instead.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if self.__nchannels == 2:
            # first split the left and right channels and then remix them
            right = self.copy().right()
            self.left().amplify(left_factor)
            return self.stereo_mix(right, 'R', right_factor)
        if self.__nchannels == 1:
            self.__frames = audioop.tostereo(self.__frames, self.__samplewidth, left_factor, right_factor)
            self.__nchannels = 2
            return self
        raise ValueError("sample must be mono or stereo already")

    def stereo_mix(self, other: 'Sample', other_channel: str, other_mix_factor: float = 1.0,
                   mix_at: float = 0.0, other_seconds: Optional[float] = None) -> 'Sample':
        """
        Mixes another mono channel into the current sample as left or right channel.
        The current sample will be the other channel.
        If the current sample already was stereo, the new mono channel is mixed with the existing left or right channel.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert other.__nchannels == 1
        assert other.__samplerate == self.__samplerate
        assert other.__samplewidth == self.__samplewidth
        assert other_channel in ('L', 'R')
        if self.__nchannels == 1:
            # turn self into stereo first
            if other_channel == 'L':
                self.stereo(left_factor=0, right_factor=1)
            else:
                self.stereo(left_factor=1, right_factor=0)
        # turn other sample into stereo and mix it efficiently
        other = other.copy()
        if other_channel == 'L':
            other = other.stereo(left_factor=other_mix_factor, right_factor=0)
        else:
            other = other.stereo(left_factor=0, right_factor=other_mix_factor)
        return self.mix_at(mix_at, other, other_seconds)

    def pan(self, panning: float = 0.0, lfo: Optional[Union[Iterable[float], Oscillator]] = None) -> 'Sample':
        """
        Linear Stereo panning, -1 = full left, 1 = full right.
        If you provide a LFO that will be used for panning instead.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if not lfo:
            return self.stereo((1-panning)/2, (1+panning)/2)
        if isinstance(lfo, Oscillator):
            lfo = itertools.chain.from_iterable(lfo.blocks())
        else:
            lfo = iter(lfo)
        if self.__nchannels == 2:
            right = self.copy().right().get_frame_array()
            left = self.copy().left().get_frame_array()
            stereo = self.get_frame_array()
            for i in range(len(right)):
                panning = next(lfo)
                left_s = left[i]*(1-panning)/2
                right_s = right[i]*(1+panning)/2
                stereo[i*2] = int(left_s)
                stereo[i*2+1] = int(right_s)
        else:
            mono = self.get_frame_array()
            stereo = mono+mono
            for i, sample in enumerate(mono):
                panning = next(lfo)
                stereo[i*2] = int(sample*(1-panning)/2)
                stereo[i*2+1] = int(sample*(1+panning)/2)
            self.__nchannels = 2
        self.__frames = Sample.from_array(stereo, self.__samplerate, 2).__frames
        return self

    def echo(self, length: float, amount: int, delay: float, decay: float) -> 'Sample':
        """
        Adds the given amount of echos into the end of the sample,
        using a given length of sample data (from the end of the sample).
        The decay is the factor with which each echo is decayed in volume (can be >1 to increase in volume instead).
        If you use a very short delay the echos blend into the sound and the effect is more like a reverb.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        if amount > 0:
            length = max(0, self.duration - length)
            echo = self.copy()
            echo.__frames = self.__frames[self.frame_idx(length):]
            echo_amp = decay
            for _ in range(amount):
                if echo_amp < 1.0/(2**(8*self.__samplewidth-1)):
                    # avoid computing echos that you can't hear
                    break
                length += delay
                echo = echo.copy().amplify(echo_amp)
                self.mix_at(length, echo)
                echo_amp *= decay
        return self

    def envelope(self, attack: float, decay: float, sustainlevel: float, release: float) -> 'Sample':
        """Apply an ADSR volume envelope. A,D,R are in seconds, Sustainlevel is a factor."""
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert attack >= 0 and decay >= 0 and release >= 0
        assert 0 <= sustainlevel <= 1
        D = self.split(attack)   # self = A
        S = D.split(decay)
        if sustainlevel < 1:
            S.amplify(sustainlevel)   # apply the sustain level to S now so that R gets it as well
        R = S.split(S.duration - release)
        if attack > 0:
            self.fadein(attack)
        if decay > 0:
            D.fadeout(decay, sustainlevel)
        if release > 0:
            R.fadeout(release)
        self.join(D).join(S).join(R)
        return self

    def mix(self, other: 'Sample', other_seconds: Optional[float] = None, pad_shortest: bool = True) -> 'Sample':
        """
        Mix another sample into the current sample.
        You can limit the length taken from the other sample.
        When pad_shortest is False, no sample length adjustment is done.
        """
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.samplewidth == other.samplewidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        frames1 = self.__frames
        if other_seconds:
            frames2 = other.__frames[:other.frame_idx(other_seconds)]
        else:
            frames2 = other.__frames
        if pad_shortest:
            if len(frames1) < len(frames2):
                frames1 += b"\0"*(len(frames2)-len(frames1))
            elif len(frames2) < len(frames1):
                frames2 += b"\0"*(len(frames1)-len(frames2))
        self.__frames = audioop.add(frames1, frames2, self.samplewidth)
        return self

    def mix_at(self, seconds: float, other: 'Sample', other_seconds: Optional[float] = None) -> 'Sample':
        """
        Mix another sample into the current sample at a specific time point.
        You can limit the length taken from the other sample.
        """
        if seconds == 0.0:
            return self.mix(other, other_seconds)
        if self.__locked:
            raise RuntimeError("cannot modify a locked sample")
        assert self.samplewidth == other.samplewidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        start_frame_idx = self.frame_idx(seconds)
        if other_seconds:
            other_frames = other.__frames[:other.frame_idx(other_seconds)]
        else:
            other_frames = other.__frames
        # Mix the frames. Unfortunately audioop requires splitting and copying the sample data, which is slow.
        pre, to_mix, post = self._mix_split_frames(len(other_frames), start_frame_idx)
        self.__frames = b""  # allow for garbage collection
        mixed = audioop.add(to_mix, other_frames, self.samplewidth)
        del to_mix  # more garbage collection
        self.__frames = self._mix_join_frames(pre, mixed, post)
        return self

    def _mix_join_frames(self, pre: bytes, mid: bytes, post: bytes) -> bytes:
        # warning: slow due to copying (but only significant when not streaming)
        return pre + mid + post

    def _mix_split_frames(self, other_frames_length: int, start_frame_idx: int) -> Tuple[bytes, bytes, bytes]:
        # warning: slow due to copying (but only significant when not streaming)
        self._mix_grow_if_needed(start_frame_idx, other_frames_length)
        pre = self.__frames[:start_frame_idx]
        to_mix = self.__frames[start_frame_idx:start_frame_idx + other_frames_length]
        post = self.__frames[start_frame_idx + other_frames_length:]
        return pre, to_mix, post

    def _mix_grow_if_needed(self, start_frame_idx: int, other_length: int) -> None:
        # warning: slow due to copying (but only significant when not streaming)
        required_length = start_frame_idx + other_length
        if required_length > len(self.__frames):
            # we need to extend the current sample buffer to make room for the mixed sample at the end
            self.__frames += b"\0" * (required_length - len(self.__frames))


# noinspection PyAttributeOutsideInit
class LevelMeter:
    """
    Keeps track of sound level (measured on the decibel scale where 0 db=max level).
    It has state, because it keeps track of the peak levels as well over time.
    The peaks eventually decay slowly if the actual level is decreased.
    """
    def __init__(self, rms_mode: bool = False, lowest: float = -60.0) -> None:
        """
        Creates a new Level meter.
        Rms mode means that instead of peak volume, RMS volume will be used.
        """
        assert -60.0 <= lowest < 0.0
        self._rms = rms_mode
        self._lowest = lowest
        self.reset()

    def reset(self) -> None:
        """Resets the meter to its initial state with lowest levels."""
        self.peak_left = self.peak_right = self._lowest
        self._peak_left_hold = self._peak_right_hold = 0.0
        self.level_left = self.level_right = self._lowest
        self._time = 0.0

    def update(self, sample: Sample) -> Tuple[float, float, float, float]:
        """
        Process a sample and calculate new levels (Left/Right) and new peak levels.
        This works best if you use short sample fragments (say < 0.1 seconds).
        It will update the level meter's state, but for convenience also returns
        the left, peakleft, right, peakright levels as a tuple.
        """
        if self._rms:
            left, right = sample.level_db_rms
        else:
            left, right = sample.level_db_peak
        left = max(left, self._lowest)
        right = max(right, self._lowest)
        time = self._time + sample.duration
        if (time-self._peak_left_hold) > 0.4:
            self.peak_left -= sample.duration*30.0
        if left >= self.peak_left:
            self.peak_left = left
            self._peak_left_hold = time
        if (time-self._peak_right_hold) > 0.4:
            self.peak_right -= sample.duration*30.0
        if right >= self.peak_right:
            self.peak_right = right
            self._peak_right_hold = time
        self.level_left = left
        self.level_right = right
        self._time = time
        return left, self.peak_left, right, self.peak_right

    def print(self, bar_width: int = 60, stereo: bool = False) -> None:
        """
        Prints the current level meter as one ascii art line to standard output.
        Left and right levels are joined into one master level,
        unless you set stereo to True which will print L+R.
        """
        if stereo:
            bar_width //= 2
            db_level_left = int(bar_width - bar_width * self.level_left / self._lowest)
            db_level_right = int(bar_width - bar_width * self.level_right / self._lowest)
            peak_indicator_left = int(bar_width * self.peak_left / self._lowest)
            peak_indicator_right = int(bar_width - bar_width * self.peak_right / self._lowest)
            bar_left = ("#" * db_level_left).rjust(bar_width)
            bar_right = ("#" * db_level_right).ljust(bar_width)
            bar_left = bar_left[:peak_indicator_left] + ':' + bar_left[peak_indicator_left:]
            bar_right = bar_right[:peak_indicator_right] + ':' + bar_right[peak_indicator_right:]
            print(" |", bar_left, "| L-R |", bar_right, "|", end="\r")
        else:
            db_mixed = (self.level_left + self.level_right) / 2
            peak_mixed = (self.peak_left + self.peak_right) / 2
            db_level = int(bar_width - bar_width * db_mixed / self._lowest)
            peak_indicator = int(bar_width - bar_width * peak_mixed / self._lowest)
            db_meter = ("#" * db_level).ljust(bar_width)
            db_meter = db_meter[:peak_indicator] + ':' + db_meter[peak_indicator:]
            print(" {:d} dB |{:s}| 0 dB".format(int(self._lowest), db_meter), end="\r")
