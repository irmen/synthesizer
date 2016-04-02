"""
Sample mixer and sequencer meant to create rhythms. Inspired by the Roland TR-909.
Uses PyAudio (https://pypi.python.org/pypi/PyAudio) for playing sound. On windows
it can fall back to using the winsound module if pysound isn't available.

Sample mix rate is configured at 44.1 khz. You may want to change this if most of
the samples you're using are of a different sample rate (such as 48Khz), to avoid
the slight loss of quality due to resampling.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import sys
import os
import wave
import audioop
import array
import threading
import queue
from configparser import ConfigParser
try:
    import pyaudio
except ImportError:
    pyaudio = None
    import winsound
import cmd
if sys.version_info < (3, 0):
    raise RuntimeError("This module requires python 3.x")

__all__ = ["Sample", "Mixer", "Song", "Repl"]


class Sample:
    """
    Audio sample data. Supports integer sample formats of 1, 2, 3 and 4 bytes per sample (no floating-point).
    Python 3.4+ is required to support 3-bytes/24-bits sample sizes.
    Most operations modify the sample data in place (if it's not locked) and return the sample object,
    so you can easily chain several operations.
    """
    norm_samplerate = 44100
    norm_nchannels = 2
    norm_samplewidth = 2

    def __init__(self, wave_file=None):
        """Creates a new empty sample, or loads it from a wav file."""
        self.__locked = False
        if wave_file:
            self.load_wav(wave_file)
            self.__filename = wave_file
            assert 1 <= self.__nchannels <= 2
            assert 1 <= self.__samplewidth <= 4
            assert self.__samplerate > 1
        else:
            self.__samplerate = self.norm_samplerate
            self.__nchannels = self.norm_nchannels
            self.__samplewidth = self.norm_samplewidth
            self.__frames = b""
            self.__filename = None

    def __repr__(self):
        locked = " (locked)" if self.__locked else ""
        return "<Sample at 0x{0:x}, {1:g} seconds, {2:d} channels, {3:d} bytes/sample, rate {4:d}{5:s}>"\
            .format(id(self), self.duration, self.__nchannels, self.__samplewidth, self.__samplerate, locked)

    @classmethod
    def from_raw_frames(cls, frames, samplewidth, samplerate, numchannels):
        """Creates a new sample directly from the raw sample data."""
        assert 1 <= numchannels <= 2
        assert 1 <= samplewidth <= 4
        assert samplerate > 1
        s = cls()
        s.__frames = frames
        s.__samplerate = int(samplerate)
        s.__samplewidth = int(samplewidth)
        s.__nchannels = int(numchannels)
        return s

    @classmethod
    def from_array(cls, array, samplerate, numchannels):
        samplewidth = array.itemsize
        assert 1 <= numchannels <= 2
        assert 1 <= samplewidth <= 4
        assert samplerate > 1
        frames = array.tobytes()
        if sys.byteorder == "big":
            frames = audioop.byteswap(frames, samplewidth)
        return Sample.from_raw_frames(frames, samplewidth, samplerate, numchannels)

    @property
    def samplewidth(self): return self.__samplewidth

    @property
    def samplerate(self):
        """You can also set this to a new value, but that will directly affect the pitch and the duration of the sample."""
        return self.__samplerate

    @samplerate.setter
    def samplerate(self, rate):
        assert rate > 0
        self.__samplerate = int(rate)

    @property
    def nchannels(self): return self.__nchannels

    @property
    def filename(self): return self.__filename

    @property
    def duration(self):
        return len(self.__frames) / self.__samplerate / self.__samplewidth / self.__nchannels

    def __len__(self):
        """returns the number of sample frames"""
        return len(self.__frames) // self.__samplewidth // self.__nchannels

    def get_frame_array(self):
        """Returns the sample values as array. Warning: this can copy large amounts of data."""
        if self.__samplewidth == 1:
            return array.array('b', self.__frames)
        elif self.__samplewidth == 2:
            return array.array('h', self.__frames)
        elif self.__samplewidth == 4:
            return array.array('l', self.__frames)
        else:
            raise ValueError("can only fade sample widths 1, 2 and 4")

    def copy(self):
        """Returns a copy of the sample (unlocked)."""
        cpy = Sample()
        cpy.__frames = self.__frames
        cpy.__samplewidth = self.__samplewidth
        cpy.__samplerate = self.__samplerate
        cpy.__nchannels = self.__nchannels
        cpy.__filename = self.__filename
        cpy.__locked = False
        return cpy

    def lock(self):
        """Lock the sample against modifications."""
        self.__locked = True
        return self

    def frame_idx(self, seconds):
        """Calculate the raw frame index for the sample at the given timestamp."""
        return self.nchannels*self.samplewidth*int(self.samplerate*seconds)

    def load_wav(self, file_or_stream):
        """Loads sample data from the wav file. You can use a filename or a stream object."""
        assert not self.__locked
        with wave.open(file_or_stream) as w:
            if not 2 <= w.getsampwidth() <= 4:
                raise IOError("only supports sample sizes of 2, 3 or 4 bytes")
            if not 1 <= w.getnchannels() <= 2:
                raise IOError("only supports mono or stereo channels")
            self.__frames = w.readframes(w.getnframes())
            self.__nchannels = w.getnchannels()
            self.__samplerate = w.getframerate()
            self.__samplewidth = w.getsampwidth()
            return self

    def write_wav(self, file_or_stream):
        """Write a wav file with the current sample data. You can use a filename or a stream object."""
        with wave.open(file_or_stream, "wb") as out:
            out.setparams((self.nchannels, self.samplewidth, self.samplerate, 0, "NONE", "not compressed"))
            out.writeframes(self.__frames)

    @classmethod
    def wave_write_begin(cls, filename, first_sample):
        """
        Part of the sample stream output api: begin writing a sample to an output file.
        Returns the open file for future writing.
        """
        out = wave.open(filename, "wb")
        out.setparams((first_sample.nchannels, first_sample.samplewidth, first_sample.samplerate, 0, "NONE", "not compressed"))
        out.writeframesraw(first_sample.__frames)
        return out

    @classmethod
    def wave_write_append(cls, out, sample):
        """Part of the sample stream output api: write more sample data to an open output stream."""
        out.writeframesraw(sample.__frames)

    @classmethod
    def wave_write_end(cls, out):
        """Part of the sample stream output api: finalize and close the open output stream."""
        out.writeframes(b"")  # make sure the updated header gets written
        out.close()

    def write_frames(self, stream):
        """Write the raw sample data to the output stream."""
        stream.write(self.__frames)

    def normalize(self):
        """
        Normalize the sample, meaning: convert it to the default samplerate, sample width and number of channels.
        When mixing samples, they should all have the same properties, and this method is ideal to make sure of that.
        """
        assert not self.__locked
        self.resample(self.norm_samplerate)
        if self.samplewidth != self.norm_samplewidth:
            # Convert to 16 bit sample size.
            self.__frames = audioop.lin2lin(self.__frames, self.samplewidth, self.norm_samplewidth)
            self.__samplewidth = self.norm_samplewidth
        if self.nchannels == 1:
            # convert to stereo
            self.__frames = audioop.tostereo(self.__frames, self.samplewidth, 1, 1)
            self.__nchannels = 2
        return self

    def resample(self, samplerate):
        """
        Resamples to a different sample rate, without changing the pitch and duration of the sound.
        The algorithm used is simple, and it will cause a loss of sound quality.
        """
        assert not self.__locked
        if samplerate == self.__samplerate:
            return self
        self.__frames = audioop.ratecv(self.__frames, self.samplewidth, self.nchannels, self.samplerate, samplerate, None)[0]
        self.__samplerate = samplerate
        return self

    def speed(self, speed):
        """
        Changes the playback speed of the sample, without changing the sample rate.
        This will change the pitch and duration of the sound accordingly.
        The algorithm used is simple, and it will cause a loss of sound quality.
        """
        assert not self.__locked
        assert speed > 0
        if speed == 1.0:
            return self
        rate = self.samplerate
        self.__frames = audioop.ratecv(self.__frames, self.samplewidth, self.nchannels, int(self.samplerate*speed), rate, None)[0]
        self.__samplerate = rate
        return self

    def make_32bit(self, scale_amplitude=True):
        """
        Convert to 32 bit integer sample width, usually also scaling the amplitude to fit in the new 32 bits range.
        Not scaling the amplitude means that the sample values will remain in their original range (usually 16 bit).
        This is ideal to create sample value headroom to mix multiple samples together without clipping or overflow issues.
        Usually after mixing you will convert back to 16 bits using maximized amplitude to have no quality loss.
        """
        assert not self.__locked
        self.__frames = self.get_32bit_frames(scale_amplitude)
        self.__samplewidth = 4
        return self

    def get_32bit_frames(self, scale_amplitude=True):
        """Returns the raw sample frames scaled to 32 bits. See make_32bit method for more info."""
        if self.samplewidth == 4:
            return self.__frames
        frames = audioop.lin2lin(self.__frames, self.samplewidth, 4)
        if not scale_amplitude:
            # we need to scale back the sample amplitude to fit back into 24/16/8 bit range
            factor = 1.0/2**(8*abs(self.samplewidth-4))
            frames = audioop.mul(frames, 4, factor)
        return frames

    def make_16bit(self, maximize_amplitude=True):
        """
        Convert to 16 bit sample width, usually by using a maximized amplification factor to
        scale into the full 16 bit range without clipping or overflow.
        This is used for example to downscale a 32 bits mixed sample back into 16 bit width.
        """
        assert not self.__locked
        assert self.samplewidth >= 2
        if maximize_amplitude:
            self.amplify_max()
        if self.samplewidth > 2:
            self.__frames = audioop.lin2lin(self.__frames, self.samplewidth, 2)
            self.__samplewidth = 2
        return self

    def amplify_max(self):
        """Amplify the sample to maximum volume without clipping or overflow happening."""
        assert not self.__locked
        max_amp = audioop.max(self.__frames, self.samplewidth)
        max_target = 2 ** (8 * self.samplewidth - 1) - 2
        if max_amp > 0:
            factor = max_target/max_amp
            self.__frames = audioop.mul(self.__frames, self.samplewidth, factor)
        return self

    def amplify(self, factor):
        """Amplifies (multiplies) the sample by the given factor. May cause clipping/overflow if factor is too large."""
        assert not self.__locked
        self.__frames = audioop.mul(self.__frames, self.samplewidth, factor)
        return self

    def at_volume(self, volume):
        """
        Returns a copy of the sample at the given volume level 0-1, leaves original untouched.
        This is a special method (next to amplify) because often the same sample will be used
        at different volume levels, and it is cumbersome to drag copies around for every volume desired.
        This also enables you to use this on locked samples.
        """
        cpy = self.copy()
        cpy.amplify(volume)
        return cpy

    def clip(self, start_seconds, end_seconds):
        """Keep only a given clip from the sample."""
        assert not self.__locked
        assert end_seconds > start_seconds
        start = self.frame_idx(start_seconds)
        end = self.frame_idx(end_seconds)
        self.__frames = self.__frames[start:end]
        return self

    def split(self, seconds):
        """Splits the sample in two parts, keep the first and return the chopped off bit at the end."""
        assert not self.__locked
        end = self.frame_idx(seconds)
        if end != len(self.__frames):
            chopped = self.copy()
            chopped.__frames = self.__frames[end:]
            self.__frames = self.__frames[:end]
            return chopped
        return Sample.from_raw_frames(b"", self.__samplewidth, self.__samplerate, self.__nchannels)

    def add_silence(self, seconds, at_start=False):
        """Add silence at the end (or at the start)"""
        assert not self.__locked
        required_extra = self.frame_idx(seconds)
        if at_start:
            self.__frames = b"\0"*required_extra + self.__frames
        else:
            self.__frames += b"\0"*required_extra
        return self

    def join(self, other):
        """Add another sample at the end of the current one. The other sample must have the same properties."""
        assert not self.__locked
        assert self.samplewidth == other.samplewidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        self.__frames += other.__frames
        return self

    def fadeout(self, seconds, target_volume=0.0):
        """Fade the end of the sample out to the target volume (usually zero) in the given time."""
        assert not self.__locked
        if self.__samplewidth == 1:
            faded = array.array('b')
        elif self.__samplewidth == 2:
            faded = array.array('h')
        elif self.__samplewidth == 4:
            faded = array.array('l')
        else:
            raise ValueError("can only fade sample widths 1, 2 and 4")
        seconds = min(seconds, self.duration)
        i = self.frame_idx(self.duration-seconds)
        begin = self.__frames[:i]
        end = self.__frames[i:]  # we fade this chunk
        numsamples = len(end)/self.__samplewidth
        decrease = 1-target_volume
        for i in range(int(numsamples)):
            amplitude = 1-(i/numsamples)*decrease
            s = audioop.getsample(end, self.__samplewidth, i)
            faded.append(int(s*amplitude))
        end = faded.tobytes()
        if sys.byteorder == "big":
            end = audioop.byteswap(end, self.__samplewidth)
        self.__frames = begin + end
        return self

    def fadein(self, seconds, start_volume=0.0):
        """Fade the start of the sample in from the starting volume (usually zero) in the given time."""
        assert not self.__locked
        if self.__samplewidth == 1:
            faded = array.array('b')
        elif self.__samplewidth == 2:
            faded = array.array('h')
        elif self.__samplewidth == 4:
            faded = array.array('l')
        else:
            raise ValueError("can only fade sample widths 1, 2 and 4")
        seconds = min(seconds, self.duration)
        i = self.frame_idx(seconds)
        begin = self.__frames[:i]  # we fade this chunk
        end = self.__frames[i:]
        numsamples = len(begin)/self.__samplewidth
        increase = 1-start_volume
        for i in range(int(numsamples)):
            amplitude = i*increase/numsamples+start_volume
            s = audioop.getsample(begin, self.__samplewidth, i)
            faded.append(int(s*amplitude))
        begin = faded.tobytes()
        if sys.byteorder == "big":
            begin = audioop.byteswap(begin, self.__samplewidth)
        self.__frames = begin + end
        return self

    def modulate_amp(self, modulation_wave):
        """
        Perform amplitude modulation by another waveform (which will be cycled).
        This is similar but not the same as AM by an LFO.
        The maximum amplitude of the modulator waveform is scaled to be 1.0 so no overflow/clipping will occur.
        """
        assert not self.__locked
        if self.__samplewidth == 1:
            frames = array.array('b', self.__frames)
        elif self.__samplewidth == 2:
            frames = array.array('h', self.__frames)
        elif self.__samplewidth == 4:
            frames = array.array('l', self.__frames)
        else:
            raise ValueError("can only modulate sample widths 1, 2 and 4")
        if isinstance(modulation_wave, Sample):
            modulation_wave = modulation_wave.get_frame_array()
        factor = 1.0/max(modulation_wave)
        import itertools
        modulation_wave = itertools.cycle(modulation_wave)
        for i in range(len(frames)):
            frames[i] = int(frames[i] * next(modulation_wave) * factor)
        self.__frames = frames.tobytes()
        if sys.byteorder == "big":
            self.__frames = audioop.byteswap(self.__frames, self.__samplewidth)
        return self

    def reverse(self):
        """Reverse the sound."""
        assert not self.__locked
        self.__frames = audioop.reverse(self.__frames, self.__samplewidth)
        return self

    def invert(self):
        """Invert every sample value around 0."""
        assert not self.__locked
        return self.amplify(-1)

    def delay(self, seconds, keep_length=False):
        """
        Delay the sample for a given time (inserts silence).
        If delay<0, instead, skip a bit from the start.
        This is a nice wrapper around the add_silence and clip functions.
        """
        assert not self.__locked
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

    def bias(self, bias):
        """Add a bias constant to each sample value."""
        assert not self.__locked
        self.__frames = audioop.bias(self.__frames, self.__samplewidth, bias)
        return self

    def mono(self, left_factor=1.0, right_factor=1.0):
        """Make the sample mono (1-channel) applying the given left/right channel factors when downmixing"""
        assert not self.__locked
        if self.__nchannels == 1:
            return self
        if self.__nchannels == 2:
            self.__frames = audioop.tomono(self.__frames, self.__samplewidth, left_factor, right_factor)
            self.__nchannels = 1
            return self
        raise ValueError("sample must be stereo or mono already")

    def stereo(self, left_factor=1.0, right_factor=1.0):
        """
        Turn a mono sample into a stereo one with given factors/amplitudes for left and right channels.
        Note that it is a fast but simplistic conversion; the waveform in both channels is identical
        so you may suffer from phase cancellation when playing the resulting stereo sample.
        """
        assert not self.__locked
        if self.__nchannels == 2:
            return self
        if self.__nchannels == 1:
            self.__frames = audioop.tostereo(self.__frames, self.__samplewidth, left_factor, right_factor)
            self.__nchannels = 2
            return self
        raise ValueError("sample must be mono or stereo already")

    def stereo_mix(self, other, other_channel, other_mix_factor=1.0):
        """
        Mixes another mono channel into the current sample as left or right channel.
        The current sample will be the other channel.
        If the current sample already was stereo, the new mono channel is mixed with the existing left or right channel.
        """
        assert not self.__locked
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
        return self.mix(other)

    def echo(self, length, amount, delay, decay):
        """
        Adds the given amount of echos into the end of the sample,
        using a given length of sample data (from the end of the sample).
        The decay is the factor with which each echo is decayed in volume (can be >1 to increase in volume instead).
        If you use a very short delay the echos blend into the sound and the effect is more like a reverb.
        """
        assert not self.__locked
        if amount > 0:
            length = max(0, self.duration - length)
            echo = self.copy()
            echo.__frames = self.__frames[self.frame_idx(length):]
            for _ in range(amount):
                length += delay
                echo.amplify(decay)
                self.mix_at(length, echo)
        return self

    def envelope(self, attack, decay, sustainlevel, release):
        """Apply an ADSR volume envelope. A,D,R are in seconds, Sustainlevel is a factor."""
        assert not self.__locked
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

    def mix(self, other, other_seconds=None, pad_shortest=True):
        """
        Mix another sample into the current sample.
        You can limit the length taken from the other sample.
        When pad_shortest is False, no sample length adjustment is done.
        """
        assert not self.__locked
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

    def mix_at(self, seconds, other, other_seconds=None):
        """
        Mix another sample into the current sample at a specific time point.
        You can limit the length taken from the other sample.
        """
        assert not self.__locked
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
        self.__frames = None  # allow for garbage collection
        mixed = audioop.add(to_mix, other_frames, self.samplewidth)
        del to_mix  # more garbage collection
        self.__frames = self._mix_join_frames(pre, mixed, post)
        return self

    def _mix_join_frames(self, pre, mid, post):
        # warning: slow due to copying (but only significant when not streaming)
        return pre + mid + post

    def _mix_split_frames(self, other_frames_length, start_frame_idx):
        # warning: slow due to copying (but only significant when not streaming)
        self._mix_grow_if_needed(start_frame_idx, other_frames_length)
        pre = self.__frames[:start_frame_idx]
        to_mix = self.__frames[start_frame_idx:start_frame_idx + other_frames_length]
        post = self.__frames[start_frame_idx + other_frames_length:]
        return pre, to_mix, post

    def _mix_grow_if_needed(self, start_frame_idx, other_length):
        # warning: slow due to copying (but only significant when not streaming)
        required_length = start_frame_idx + other_length
        if required_length > len(self.__frames):
            # we need to extend the current sample buffer to make room for the mixed sample at the end
            self.__frames += b"\0" * (required_length - len(self.__frames))


class Mixer:
    """
    Mixes a set of ascii-bar tracks using the given sample instruments, into a resulting big sample.
    """
    def __init__(self, patterns, bpm, ticks, instruments):
        for p in patterns:
            bar_length = 0
            for instrument, bars in p.items():
                if instrument not in instruments:
                    raise ValueError("instrument '{:s}' not defined".format(instrument))
                if len(bars) % ticks != 0:
                    raise ValueError("bar length must be multiple of the number of ticks")
                if 0 < bar_length != len(bars):
                    raise ValueError("all bars must be of equal length in the same pattern")
                bar_length = len(bars)
        self.patterns = patterns
        self.instruments = instruments
        self.bpm = bpm
        self.ticks = ticks

    def mix(self, verbose=True):
        """
        Mix all the patterns into a single result sample.
        """
        if not self.patterns:
            if verbose:
                print("No patterns to mix, output is empty.")
            return Sample()
        total_seconds = 0.0
        for p in self.patterns:
            bar = next(iter(p.values()))
            total_seconds += len(bar) * 60.0 / self.bpm / self.ticks
        if verbose:
            print("Mixing {:d} patterns...".format(len(self.patterns)))
        mixed = Sample().make_32bit()
        for index, timestamp, sample in self.mixed_samples(tracker=False):
            if verbose:
                print("\r{:3.0f} % ".format(timestamp/total_seconds*100), end="")
            mixed.mix_at(timestamp, sample)
        # chop/extend to get to the precise total duration (in case of silence in the last bars etc)
        missing = total_seconds-mixed.duration
        if missing > 0:
            mixed.add_silence(missing)
        elif missing < 0:
            mixed.clip(0, total_seconds)
        if verbose:
            print("\rMix done.")
        return mixed

    def mix_generator(self):
        """
        Returns a generator that produces samples that are the chronological
        chunks of the final output mix. This avoids having to mix it into one big
        output mix sample.
        """
        if not self.patterns:
            yield Sample()
            return
        total_seconds = 0.0
        for p in self.patterns:
            bar = next(iter(p.values()))
            total_seconds += len(bar) * 60.0 / self.bpm / self.ticks
        mixed_duration = 0.0
        samples = self.mixed_samples()
        # get the first sample
        index, previous_timestamp, sample = next(samples)
        mixed = Sample().make_32bit()
        mixed.mix_at(previous_timestamp, sample)
        # continue mixing the following samples
        for index, timestamp, sample in samples:
            trigger_duration = timestamp-previous_timestamp
            overflow = None
            if mixed.duration < trigger_duration:
                # fill with some silence to reach the next sample position
                mixed.add_silence(trigger_duration - mixed.duration)
            elif mixed.duration > trigger_duration:
                # chop off the sound that extends into the next sample position
                # keep this overflow and mix it later!
                overflow = mixed.split(trigger_duration)
            mixed_duration += mixed.duration
            yield mixed
            mixed = overflow if overflow else Sample().make_32bit()
            mixed.mix(sample)
            previous_timestamp = timestamp
        # output the last remaining sample and extend it to the end of the duration if needed
        timestamp = total_seconds
        trigger_duration = timestamp-previous_timestamp
        if mixed.duration < trigger_duration:
            mixed.add_silence(trigger_duration - mixed.duration)
        elif mixed.duration > trigger_duration:
            mixed.clip(0, trigger_duration)
        mixed_duration += mixed.duration
        yield mixed

    def mixed_triggers(self, tracker):
        """
        Generator for all triggers in chronological sequence.
        Every element is a tuple: (trigger index, time offset (seconds), list of (instrumentname, sample tuples)
        """
        time_per_index = 60.0 / self.bpm / self.ticks
        index = 0
        for pattern_nr, pattern in enumerate(self.patterns, start=1):
            pattern = list(pattern.items())
            num_triggers = len(pattern[0][1])
            for i in range(num_triggers):
                triggers = []
                triggered_instruments = set()
                for instrument, bars in pattern:
                    if bars[i] not in ". ":
                        sample = self.instruments[instrument]
                        triggers.append((instrument, sample))
                        triggered_instruments.add(instrument)
                if triggers:
                    if tracker:
                        triggerdots = ['#' if instr in triggered_instruments else '.' for instr in self.instruments]
                        print("\r{:3d} [{:3d}] ".format(index, pattern_nr), "".join(triggerdots), end="   ", flush=True)
                    yield index, time_per_index*index, triggers
                index += 1

    def mixed_samples(self, tracker=True):
        """
        Generator for all samples-to-mix.
        Every element is a tuple: (trigger index, time offset (seconds), sample)
        """
        mix_cache = {}  # we cache stuff to avoid repeated mixes of the same instruments
        for index, timestamp, triggers in self.mixed_triggers(tracker):
            if len(triggers) > 1:
                # sort the samples to have the longest one as the first
                # this allows us to allocate the target mix buffer efficiently
                triggers = sorted(triggers, key=lambda t: t[1].duration, reverse=True)
                instruments_key = tuple(instrument for instrument, _ in triggers)
                if instruments_key in mix_cache:
                    yield index, timestamp, mix_cache[instruments_key]
                    continue
                # duplicate the longest sample as target mix buffer, then mix the remaining samples into it
                mixed = triggers[0][1].copy()
                for _, sample in triggers[1:]:
                    mixed.mix(sample)
                mixed.lock()
                mix_cache[instruments_key] = mixed   # cache the mixed instruments sample
                yield index, timestamp, mixed
            else:
                # simply yield the unmixed sample from the single trigger
                yield index, timestamp, triggers[0][1]


class Song:
    """
    Represents a set of instruments, patterns and bars that make up a 'song'.
    """
    def __init__(self):
        self.instruments = {}
        self.sample_path = None
        self.bpm = 128
        self.ticks = 4
        self.pattern_sequence = []
        self.patterns = {}

    def read(self, song_file, discard_unused_instruments=True):
        """Read a song from a saved file."""
        with open(song_file):
            pass    # test for file existence
        print("Loading song...")
        cp = ConfigParser()
        cp.read(song_file)
        self.sample_path = cp["paths"]["samples"]
        self.read_samples(cp["samples"], self.sample_path)
        if "song" in cp:
            self.bpm = cp["song"].getint("bpm")
            self.ticks = cp["song"].getint("ticks")
            self.read_patterns(cp, cp["song"]["patterns"].split())
        print("Done; {:d} instruments and {:d} patterns.".format(len(self.instruments), len(self.patterns)))
        unused_instruments = self.instruments.keys()
        for pattern_name in self.pattern_sequence:
            unused_instruments -= self.patterns[pattern_name].keys()
        if unused_instruments and discard_unused_instruments:
            for instrument in list(unused_instruments):
                del self.instruments[instrument]
            print("Warning: there are unused instruments. They have been unloaded to save memory, and can safely be removed from the song file.")
            print("The unused instruments are:", ", ".join(sorted(unused_instruments)))

    def read_samples(self, instruments, samples_path):
        """Reads the sample files for the instruments."""
        self.instruments = {}
        for name, file in sorted(instruments.items()):
            self.instruments[name] = Sample(wave_file=os.path.join(samples_path, file)).normalize().make_32bit(scale_amplitude=False).lock()

    def read_patterns(self, songdef, names):
        """Reads and parses the pattern specs from the song."""
        self.pattern_sequence = []
        self.patterns = {}
        for name in names:
            if "pattern."+name not in songdef:
                raise ValueError("pattern definition not found: "+name)
            bar_length = 0
            self.patterns[name] = {}
            for instrument, bars in songdef["pattern."+name].items():
                if instrument not in self.instruments:
                    raise ValueError("instrument '{instr:s}' not defined (pattern: {pattern:s})".format(instr=instrument, pattern=name))
                bars = bars.replace(' ', '')
                if len(bars) % self.ticks != 0:
                    raise ValueError("all patterns must be multiple of song ticks (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                self.patterns[name][instrument] = bars
                if 0 < bar_length != len(bars):
                    raise ValueError("all bars must be of equal length in the same pattern (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                bar_length = len(bars)
            self.pattern_sequence.append(name)

    def write(self, output_filename):
        """Save the song definitions to an output file."""
        import collections
        cp = ConfigParser(dict_type=collections.OrderedDict)
        cp["paths"] = {"samples": self.sample_path}
        cp["song"] = {"bpm": self.bpm, "ticks": self.ticks, "patterns": " ".join(self.pattern_sequence)}
        cp["samples"] = {}
        for name, sample in sorted(self.instruments.items()):
            cp["samples"][name] = os.path.basename(sample.filename)
        for name, pattern in sorted(self.patterns.items()):
            # Note: the layout of the patterns is not optimized for human viewing. You may want to edit it afterwards.
            cp["pattern."+name] = collections.OrderedDict(sorted(pattern.items()))
        with open(output_filename, 'w') as f:
            cp.write(f)
        print("Saved to '{:s}'.".format(output_filename))

    def mix(self, output_filename):
        """Mix the song into a resulting mix sample."""
        if not self.pattern_sequence:
            raise ValueError("There's nothing to be mixed; no song loaded or song has no patterns.")
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        result = mixer.mix()
        result.make_16bit()
        result.write_wav(output_filename)
        print("Output is {:.2f} seconds, written to: {:s}".format(result.duration, output_filename))
        return result

    def mixed_triggers(self):
        """
        Generator that produces all the instrument triggers needed to mix/stream the song.
        Shortcut for Mixer.mixed_triggers, see there for more details.
        """
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        yield from mixer.mixed_triggers()

    def mix_generator(self):
        """
        Generator that produces samples that together form the mixed song.
        Shortcut for Mixer.mix_generator(), see there for more details.
        """
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        yield from mixer.mix_generator()


class Output:
    """Plays samples to audio output device or streams them to a file."""

    class SoundOutputter(threading.Thread):
        """Sound outputter running in its own thread. Requires PyAudio."""
        def __init__(self, samplerate, samplewidth, nchannels, queuesize=100):
            super().__init__(name="soundoutputter", daemon=True)
            self.audio = pyaudio.PyAudio()
            self.stream = self.audio.open(
                    format=self.audio.get_format_from_width(samplewidth),
                    channels=nchannels, rate=samplerate, output=True)
            self.queue = queue.Queue(maxsize=queuesize)

        def run(self):
            while True:
                sample = self.queue.get()
                if not sample:
                    break
                sample.write_frames(self.stream)
            # time.sleep(self.stream.get_output_latency()+self.stream.get_input_latency()+0.001)

        def play_immediately(self, sample, continuous=False):
            sample.write_frames(self.stream)
            if not continuous:
                filler = b"\0"*sample.samplewidth*sample.nchannels*self.stream.get_write_available()
                self.stream.write(filler)
                # time.sleep(self.stream.get_output_latency()+self.stream.get_input_latency()+0.001)

        def add_to_queue(self, sample):
            self.queue.put(sample)

        def close(self):
            if self.stream:
                self.stream.close()
                self.stream = None
            if self.audio:
                self.audio.terminate()
                self.audio = None

    def __init__(self, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_samplewidth, nchannels=Sample.norm_nchannels):
        if pyaudio:
            self.outputter = Output.SoundOutputter(samplerate, samplewidth, nchannels)
            self.outputter.start()
        else:
            self.outputter = None

    @classmethod
    def for_sample(cls, sample):
        return cls(sample.samplerate, sample.samplewidth, sample.nchannels)

    def __enter__(self):
        return self

    def __exit__(self, xtype, value, traceback):
        self.close()

    def close(self):
        if self.outputter:
            self.outputter.add_to_queue(None)

    def play_sample(self, sample, async=True):
        """Play a single sample."""
        if sample.samplewidth not in (2, 3):
            sample = sample.copy().make_16bit()
        if self.outputter:
            if async:
                self.outputter.add_to_queue(sample)
            else:
                self.outputter.play_immediately(sample)
        else:
            # try to fallback to winsound (only works on windows)
            sample_file = "__temp_sample.wav"
            sample.write_wav(sample_file)
            winsound.PlaySound(sample_file, winsound.SND_FILENAME)
            os.remove(sample_file)

    def play_samples(self, samples, async=True):
        """Plays all the given samples immediately after each other, with no pauses."""
        if self.outputter:
            for s in self.normalized_samples(samples, 26000):
                if async:
                    self.outputter.add_to_queue(s)
                else:
                    self.outputter.play_immediately(s, True)
        else:
            # winsound doesn't cut it when playing many small sample files...
            raise RuntimeError("Sorry but pyaudio is not installed. You need it to play streaming audio output.")

    def normalized_samples(self, samples, global_amplification=26000):
        """Generator that produces samples normalized to 16 bit using a single amplification value for all."""
        for sample in samples:
            if sample.samplewidth != 2:
                # We can't use automatic global max amplitude because we're streaming
                # the samples individually. So use a fixed amplification value instead
                # that will be used to amplify all samples in stream by the same amount.
                sample = sample.amplify(global_amplification).make_16bit(False)
            if sample.nchannels == 1:
                sample.stereo()
            assert sample.nchannels == 2
            assert sample.samplerate == 44100
            assert sample.samplewidth == 2
            yield sample

    def stream_to_file(self, filename, samples):
        """Saves the samples after each other into one single output wav file."""
        samples = self.normalized_samples(samples, 26000)
        sample = next(samples)
        with Sample.wave_write_begin(filename, sample) as out:
            for sample in samples:
                Sample.wave_write_append(out, sample)
            Sample.wave_write_end(out)


class Repl(cmd.Cmd):
    """
    Interactive command line interface to load/record/save and play samples, patterns and whole tracks.
    Currently it has no way of defining and loading samples manually. This means you need to initialize
    it with a track file containing at least the instruments (samples) that you will be using.
    """
    def __init__(self, discard_unused_instruments=False):
        self.song = Song()
        self.discard_unused_instruments = discard_unused_instruments
        self.out = Output()
        super(Repl, self).__init__()

    def do_quit(self, args):
        """quits the session"""
        print("Bye.", args)
        self.out.close()
        return True

    def do_bpm(self, bpm):
        """set the playback BPM (such as 174 for some drum'n'bass)"""
        try:
            self.song.bpm = int(bpm)
        except ValueError as x:
            print("ERROR:", x)

    def do_ticks(self, ticks):
        """set the number of pattern ticks per beat (usually 4 or 8)"""
        try:
            self.song.ticks = int(ticks)
        except ValueError as x:
            print("ERROR:", x)

    def do_samples(self, args):
        """show the loaded samples"""
        print("Samples:")
        print(",  ".join(self.song.instruments))

    def do_patterns(self, args):
        """show the loaded patterns"""
        print("Patterns:")
        for name, pattern in sorted(self.song.patterns.items()):
            self.print_pattern(name, pattern)

    def print_pattern(self, name, pattern):
        print("PATTERN {:s}".format(name))
        for instrument, bars in pattern.items():
            print("   {:>15s} = {:s}".format(instrument, bars))

    def do_pattern(self, names):
        """play the pattern with the given name(s)"""
        names = names.split()
        for name in sorted(set(names)):
            try:
                pat = self.song.patterns[name]
                self.print_pattern(name, pat)
            except KeyError:
                print("no such pattern '{:s}'".format(name))
                return
        patterns = [self.song.patterns[name] for name in names]
        try:
            m = Mixer(patterns, self.song.bpm, self.song.ticks, self.song.instruments)
            result = m.mix(verbose=len(patterns) > 1)
            self.out.play_sample(result)
        except ValueError as x:
            print("ERROR:", x)

    def do_play(self, args):
        """play a single sample by giving its name, add a bar (xx..x.. etc) to play it in a bar"""
        if ' ' in args:
            instrument, pattern = args.split(maxsplit=1)
            pattern = pattern.replace(' ', '')
        else:
            instrument = args
            pattern = None
        instrument = instrument.strip()
        try:
            sample = self.song.instruments[instrument]
        except KeyError:
            print("unknown sample")
            return
        if pattern:
            self.play_single_bar(sample, pattern)
        else:
            self.out.play_sample(sample)

    def play_single_bar(self, sample, pattern):
        try:
            m = Mixer([{"sample": pattern}], self.song.bpm, self.song.ticks, {"sample": sample})
            result = m.mix(verbose=False)
            self.out.play_sample(result)
        except ValueError as x:
            print("ERROR:", x)

    def do_mix(self, args):
        """mix and play all patterns of the song"""
        if not self.song.pattern_sequence:
            print("Nothing to be mixed.")
            return
        output = "__temp_mix.wav"
        self.song.mix(output)
        mix = Sample(wave_file=output)
        print("Playing sound...")
        self.out.play_sample(mix, async=False)
        os.remove(output)

    def do_stream(self, args):
        """
        mix all patterns of the song and stream the output to your speakers in real-time,
        or to an output file if you give a filename argument.
        This is the fastest and most efficient way of generating the output mix because
        it uses very little memory and avoids large buffer copying.
        """
        if not self.song.pattern_sequence:
            print("Nothing to be mixed.")
            return
        if args:
            filename = args.strip()
            print("Mixing and streaming to output file '{0}'...".format(filename))
            self.out.stream_to_file(filename, self.song.mix_generator())
            print("\r                          ")
            return
        print("Mixing and streaming to speakers...")
        try:
            self.out.play_samples(self.song.mix_generator(), async=False)
            print("\r                          ")
        except KeyboardInterrupt:
            print("Stopped.")

    def do_rec(self, args):
        """Record (or overwrite) a new sample (instrument) bar in a pattern.
Args: [pattern name] [sample] [bar(s)].
Omit bars to remove the sample from the pattern.
If a pattern with the name doesn't exist yet it will be added."""
        args = args.split(maxsplit=2)
        if len(args) not in (2, 3):
            print("Wrong arguments. Use: patternname sample bar(s)")
            return
        if len(args) == 2:
            args.append(None)   # no bars
        pattern_name, instrument, bars = args
        if instrument not in self.song.instruments:
            print("Unknown sample '{:s}'.".format(instrument))
            return
        if pattern_name not in self.song.patterns:
            self.song.patterns[pattern_name] = {}
        pattern = self.song.patterns[pattern_name]
        if bars:
            bars = bars.replace(' ', '')
            if len(bars) % self.song.ticks != 0:
                print("Bar length must be multiple of the number of ticks.")
                return
            pattern[instrument] = bars
        else:
            if instrument in pattern:
                del pattern[instrument]
        if pattern_name in self.song.patterns:
            if not self.song.patterns[pattern_name]:
                del self.song.patterns[pattern_name]
                print("Pattern was empty and has been removed.")
            else:
                self.print_pattern(pattern_name, self.song.patterns[pattern_name])

    def do_seq(self, names):
        """
        Print the sequence of patterns that form the current track,
        or if you give a list of names: use that as the new pattern sequence.
        """
        if not names:
            print("  ".join(self.song.pattern_sequence))
            return
        names = names.split()
        for name in names:
            if name not in self.song.patterns:
                print("Unknown pattern '{:s}'.".format(name))
                return
        self.song.pattern_sequence = names

    def do_load(self, filename):
        """Load a new song file"""
        song = Song()
        try:
            song.read(filename, self.discard_unused_instruments)
            self.song = song
        except IOError as x:
            print("ERROR:", x)

    def do_save(self, filename):
        """Save current song to file"""
        if not filename:
            print("Give filename to save song to.")
            return
        if not filename.endswith(".ini"):
            filename += ".ini"
        if os.path.exists(filename):
            if input("File exists: '{:s}'. Overwrite y/n? ".format(filename)) not in ('y', 'yes'):
                return
        self.song.write(filename)


def main(track_file, outputfile=None, interactive=False):
    discard_unused = not interactive
    if interactive:
        repl = Repl(discard_unused_instruments=discard_unused)
        repl.do_load(track_file)
        repl.cmdloop("Interactive Samplebox session. Type 'help' for help on commands.")
    else:
        song = Song()
        song.read(track_file, discard_unused_instruments=discard_unused)
        if pyaudio:
            # mix and stream output in real time
            print("Mixing and streaming to speakers...")
            with Output() as out:
                out.play_samples(song.mix_generator(), async=False)
            print("\r                          ")
        else:
            # pyaudio is needed to stream, fallback on mixing everything to a wav
            print("(Sorry, you don't have pyaudio installed. Streaming audio is not possible.)")
            song.mix(outputfile)
            mix = Sample(wave_file=outputfile)
            print("Playing sound...")
            with Output() as out:
                out.play_sample(mix)


def usage():
    print("Arguments:  [-i] trackfile.ini")
    print("   -i = start interactive editing mode")
    raise SystemExit(1)

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        usage()
    track_file = None
    interactive = False
    if len(sys.argv) == 2:
        if sys.argv[1] == "-i":
            usage()  # need a trackfile as well to at least initialize the samples
        else:
            track_file = sys.argv[1]
    elif len(sys.argv) == 3:
        if sys.argv[1] != "-i":
            usage()
        interactive = True
        track_file = sys.argv[2]
    if interactive:
        main(track_file, interactive=True)
    else:
        output_file = os.path.splitext(track_file)[0]+".wav"
        main(track_file, output_file)
