import sys
import os
import wave
import audioop
import time
import contextlib
from configparser import ConfigParser

__all__ = ["Sample", "Mixer", "Song"]


class Sample(object):
    """
    Audio sample data, usually normalized to a fixed set of parameters: 16 bit stereo 48000khz.
    """
    norm_samplerate = 48000
    norm_nchannels = 2
    norm_sampwidth = 2

    def __init__(self, frames=b"", wave_file=None, duration=0):
        self.locked = False
        if wave_file:
            self.load_wav(wave_file)
        else:
            self.samplerate = self.norm_samplerate
            self.nchannels = self.norm_nchannels
            self.sampwidth = self.norm_sampwidth
            self.frames = frames
        if duration > 0:
            if len(frames) > 0:
                raise ValueError("cannot specify a duration if frames are provided")
            self.append(duration)

    def dup(self):
        copy = Sample(self.frames)
        copy.sampwidth = self.sampwidth
        copy.samplerate = self.samplerate
        copy.nchannels = self.nchannels
        return copy

    def lock(self):
        self.locked = True
        return self

    @property
    def duration(self):
        return len(self.frames) / self.samplerate / self.sampwidth / self.nchannels

    def frame_idx(self, seconds):
        return self.nchannels*self.sampwidth*int(self.samplerate*seconds)

    def load_wav(self, file):
        assert not self.locked
        with contextlib.closing(wave.open(file)) as w:
            if not 2 <= w.getsampwidth() <= 4:
                raise IOError("only supports sample sizes of 2, 3 or 4 bytes")
            if not 1 <= w.getnchannels() <= 2:
                raise IOError("only supports mono or stereo channels")
            self.frames = w.readframes(w.getnframes())
            self.nchannels = w.getnchannels()
            self.samplerate = w.getframerate()
            self.sampwidth = w.getsampwidth()
            return self

    def write_wav(self, file):
        with contextlib.closing(wave.open(file, "wb")) as out:
            out.setparams((self.nchannels, self.sampwidth, self.samplerate, 0, "NONE", "not compressed"))
            out.writeframes(self.frames)

    def normalize(self):
        assert not self.locked
        if self.samplerate != self.norm_samplerate:
            # convert sample rate
            self.frames = audioop.ratecv(self.frames, self.sampwidth, self.nchannels, self.samplerate, self.norm_samplerate, None)[0]
            self.samplerate = self.norm_samplerate
        if self.sampwidth != self.norm_sampwidth:
            # Convert to 16 bit sample size.
            # Note that Python 3.4+ is required to be able to convert from 24 bits sample sizes.
            self.frames = audioop.lin2lin(self.frames, self.sampwidth, self.norm_sampwidth)
            self.sampwidth = self.norm_sampwidth
        if self.nchannels == 1:
            # convert to stereo
            self.frames = audioop.tostereo(self.frames, self.sampwidth, 1, 1)
            self.nchannels = 2
        return self

    def make_32bit(self, scale_amplitude=True):
        assert not self.locked
        self.frames = self.get_32bit_frames(scale_amplitude)
        self.sampwidth = 4
        return self

    def get_32bit_frames(self, scale_amplitude=True):
        if self.sampwidth == 4:
            return self.frames
        frames = audioop.lin2lin(self.frames, self.sampwidth, 4)
        if not scale_amplitude:
            # we need to scale back the sample amplitude to fit back into 16 bit range
            factor = 1.0/2**(8*abs(self.sampwidth-4))
            frames = audioop.mul(frames, 4, factor)
        return frames

    def make_16bit(self, maximize_amplitude=True):
        assert not self.locked
        assert self.sampwidth >= 2
        if maximize_amplitude:
            self.amplify_max()
        if self.sampwidth > 2:
            self.frames = audioop.lin2lin(self.frames, self.sampwidth, 2)
            self.sampwidth = 2
        return self

    def amplify_max(self):
        assert not self.locked
        max_amp = audioop.max(self.frames, self.sampwidth)
        max_target = 2 ** (8 * self.sampwidth - 1) - 2
        factor = max_target / max_amp
        self.frames = audioop.mul(self.frames, self.sampwidth, factor)
        return self

    def amplify(self, factor):
        assert not self.locked
        self.frames = audioop.mul(self.frames, self.sampwidth, factor)
        return self

    def cut(self, start_seconds, end_seconds):
        assert not self.locked
        assert end_seconds > start_seconds
        start = self.frame_idx(start_seconds)
        end = self.frame_idx(end_seconds)
        if end != len(self.frames):
            self.frames = self.frames[start:end]
        return self

    def append(self, seconds):
        assert not self.locked
        required_extra = self.frame_idx(seconds)
        self.frames += b"\0"*required_extra

    def mix(self, other, other_seconds=None, pad_shortest=True):
        assert not self.locked
        assert self.sampwidth == other.sampwidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        frames1 = self.frames
        if other_seconds:
            frames2 = other.frames[:other.frame_idx(other_seconds)]
        else:
            frames2 = other.frames
        if pad_shortest:
            if len(frames1) < len(frames2):
                frames1 += b"\0"*(len(frames2)-len(frames1))
            elif len(frames2) < len(frames1):
                frames2 += b"\0"*(len(frames1)-len(frames2))
        self.frames = audioop.add(frames1, frames2, self.sampwidth)
        return self

    def mix_at(self, seconds, other, other_seconds=None):
        assert not self.locked
        assert self.sampwidth == other.sampwidth
        assert self.samplerate == other.samplerate
        assert self.nchannels == other.nchannels
        start_frame_idx = self.frame_idx(seconds)
        if other_seconds:
            other_frames = other.frames[:other.frame_idx(other_seconds)]
        else:
            other_frames = other.frames
        required_length = start_frame_idx + len(other_frames)
        if required_length > len(self.frames):
            # we need to extend the current sample buffer to make room for the mixed sample at the end
            self.frames += b"\0"*(required_length - len(self.frames))
        pre = self.frames[:start_frame_idx]
        to_mix = self.frames[start_frame_idx:start_frame_idx+len(other_frames)]
        post = self.frames[start_frame_idx+len(other_frames):]
        self.frames = None  # allow for garbage collection
        mixed = audioop.add(to_mix, other_frames, self.sampwidth)
        del to_mix  # more garbage collection
        self.frames = pre+mixed+post
        return self


class Mixer(object):
    """
    Mixes a set of ascii-bar tracks using the given sample instruments,
    into a resulting big sample.
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

    def mix(self):
        total_seconds = 0.0
        for p in self.patterns:
            bar = next(iter(p.values()))
            total_seconds += len(bar) * 60.0 / self.bpm / self.ticks
        print("Mixing {:d} patterns...".format(len(self.patterns)))
        mixed = Sample().make_32bit()
        timestamp = 0.0
        start_time = time.time()
        total_nr_of_triggers = 0
        for num, pattern in enumerate(self.patterns, start=1):
            print("  pattern {:d}".format(num))
            pattern = list(pattern.items())  # make it indexable
            num_triggers = len(pattern[0][1])
            for i in range(num_triggers):
                for instrument, bars in pattern:
                    if bars[i] not in ". ":
                        sample = self.instruments[instrument]
                        mixed.mix_at(timestamp, sample)
                timestamp += 60.0 / self.bpm / self.ticks
            total_nr_of_triggers += num_triggers
        mixing_time = time.time()-start_time
        # chop/extend to get to the precise total duration (in case of silence in the last bars etc)
        missing = total_seconds-mixed.duration
        if missing > 0:
            mixed.append(missing)
        elif missing < 0:
            mixed.cut(0, total_seconds)
        print("Mix done ({:.2f} triggers/sec).".format(total_nr_of_triggers/mixing_time))
        return mixed


class Song(object):
    def __init__(self):
        self.instruments = {}
        self.sample_path = None
        self.output_path = None
        self.bpm = 0
        self.ticks = 0
        self.patterns = []

    def read(self, song_file):
        with open(song_file):
            pass    # test for file existance
        print("Loading song...")
        cp = ConfigParser()
        cp.read(song_file)
        self.sample_path = cp['paths']['samples']
        self.output_path = cp['paths']['output']
        self.bpm = cp['song'].getint('bpm')
        self.ticks = cp['song'].getint('ticks')
        self.read_samples(cp['instruments'], self.sample_path)
        self.read_patterns(cp, cp['song']['patterns'].split())
        print("Done; {:d} instruments and {:d} patterns.".format(len(self.instruments), len(self.patterns)))
        unused_instruments = self.instruments.keys()
        for pattern in self.patterns:
            unused_instruments -= pattern.keys()
        if unused_instruments:
            for instrument in unused_instruments:
                del self.instruments[instrument]
            print("Warning: there are unused instruments. I've unloaded them from memory.")
            print("The unused instruments are:", ", ".join(sorted(unused_instruments)))

    def read_samples(self, instruments, samples_path):
        self.instruments = {}
        for name, file in sorted(instruments.items()):
            self.instruments[name] = Sample(wave_file=os.path.join(samples_path, file)).normalize().make_32bit(scale_amplitude=False).lock()

    def read_patterns(self, songdef, names):
        self.patterns = []
        for name in names:
            pattern = {}
            if "pattern."+name not in songdef:
                raise ValueError("pattern definition not found: "+name)
            bar_length = 0
            for instrument, bars in songdef["pattern."+name].items():
                if instrument not in self.instruments:
                    raise ValueError("instrument '{instr:s}' not defined (pattern: {pattern:s})".format(instr=instrument, pattern=name))
                bars = bars.replace(' ', '')
                if len(bars) % self.ticks != 0:
                    raise ValueError("all patterns must be multiple of song ticks (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                pattern[instrument] = bars
                if 0 < bar_length != len(bars):
                    raise ValueError("all bars must be of equal length in the same pattern (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                bar_length = len(bars)
            self.patterns.append(pattern)

    def mix(self, output_filename):
        mixer = Mixer(self.patterns, self.bpm, self.ticks, self.instruments)
        result = mixer.mix()
        output_filename = os.path.join(self.output_path, output_filename)
        result.make_16bit().write_wav(output_filename)
        print("Output is {:.2f} seconds, written to: {:s}".format(result.duration, output_filename))


def main(songfile, outputfile):
    song = Song()
    song.read(songfile)
    song.mix(outputfile)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Give track file as argument.")
        raise SystemExit(1)
    song_file = sys.argv[1]
    output_file = os.path.splitext(song_file)[0]+".wav"
    main(song_file, output_file)
