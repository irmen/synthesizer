from __future__ import division, print_function
import wave
import audioop
import contextlib
from tqdm import trange


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
    def __init__(self, tracks, bpm, ticks, instruments):
        self.tracks = [track.replace(' ', '') for track in tracks]
        if (len(self.tracks[0]) % ticks) != 0:
            raise ValueError("track length must be multiple of the number of ticks")
        self.instruments = instruments
        self.bpm = bpm
        self.ticks = ticks

    def mix(self):
        total_seconds = len(self.tracks[0]) / self.ticks / self.bpm * 60.0
        print("Mixing tracks (length of mix: {:.2f} seconds)...".format(total_seconds))
        mixed = Sample().make_32bit()
        for i in trange(len(self.tracks[0])):
            letters = [track[i] for track in self.tracks]
            for letter in letters:
                if letter in ". ":
                    continue
                try:
                    sample = self.instruments[letter]
                except KeyError:
                    print("  * WARNING: sample '{:s}' not defined".format(letter))
                else:
                    time = i / self.ticks / self.bpm * 60.0
                    mixed.mix_at(time, sample)
        missing = total_seconds - mixed.duration
        if missing > 0:
            mixed.append(missing)
        elif missing < 0:
            mixed.cut(0, total_seconds)
        return mixed

