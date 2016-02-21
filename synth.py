"""
Sample waveform synthesizer.
Creates some simple waveform samples with adjustable parameters:
sine, triangle, square, sawtooth, pulse, and white noise.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""
from rhythmbox import Sample
from math import sin, pi, floor
import random
import array
import sys
import audioop
from collections import OrderedDict

__all__ = ["key_freq", "Wavesynth"]


def key_freq(key_number, a4=440.0):
    """
    Return the note frequency for the given piano key number.
    C4 is key 40 and A4 is key 49 (=440 hz).
    https://en.wikipedia.org/wiki/Piano_key_frequencies
    """
    return 2**((key_number-49)/12) * a4

# some note frequencies for the 3rd, 4th and 5th octaves
octave_notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
notes3 = OrderedDict((note, key_freq(28+i)) for i, note in enumerate(octave_notes))
notes4 = OrderedDict((note, key_freq(40+i)) for i, note in enumerate(octave_notes))
notes5 = OrderedDict((note, key_freq(52+i)) for i, note in enumerate(octave_notes))


class Wavesynth:
    """
    Simple waveform sample synthesizer. Can generate various wave forms:
    sine, square (perfect or with harmonics), triangle and sawtooth.
    """
    def __init__(self, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth):
        if samplewidth not in (1, 2, 4):
            raise ValueError("only samplewidth sizes 1, 2 and 4 are supported")
        self.samplerate = samplerate
        self.samplewidth = samplewidth

    def _get_array(self):
        if self.samplewidth == 1:
            return array.array('b')
        elif self.samplewidth == 2:
            return array.array('h')
        elif self.samplewidth == 4:
            return array.array('l')
        else:
            raise ValueError("only samplewidth sizes 1, 2 and 4 are supported")

    def to_sample(self, sample_array):
        frames = sample_array.tobytes()
        if sys.byteorder == "big":
            frames = audioop.byteswap(bytes, self.samplewidth)
        return Sample.from_raw_frames(frames, self.samplewidth, self.samplerate, 1).fadeout(0.1)

    def sine(self, frequency, duration, amplitude=1.0):
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = amplitude*(2**(self.samplewidth*8-1)-1)
        rate = self.samplerate/frequency/2.0/pi
        for t in range(int(duration*self.samplerate)):
            samples.append(int(sin(t/rate)*scale))
        return samples

    def square(self, frequency, duration, amplitude=1.0):
        """Generate a perfect square wave [max/-max]"""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = int(0.8*amplitude*(2**(self.samplewidth*8-1)-1))
        width = self.samplerate/frequency/2
        for t in range(int(duration*self.samplerate)):
            samples.append(-scale if int(t/width) % 2 else scale)
        return samples

    def squareh(self, frequency, duration, num_harmonics=12, amplitude=1.0):
        """Generate a square wave based on harmonic sine waves (more natural)"""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = amplitude*(2**(self.samplewidth*8-1)-1)
        f = frequency/self.samplerate
        for t in range(int(duration*self.samplerate)):
            h = 0.0
            q = 2*pi*f*t
            for k in range(1, num_harmonics+1):
                m = 2*k-1
                h += sin(q*m)/m
            # Formula says 4/pi but that only works on infinite series.
            # When dealing with a non infinite number of harmonics, the signal
            # can get 'off the scale' and needs to be clamped. We compensate
            # a little by not using 4/pi but just 1, to reduce the number of clamps needed.
            # (clamping will distort the signal)
            samples.append(int(h*scale))
        return samples

    def triangle(self, frequency, duration, amplitude=1.0):
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = amplitude*(2**(self.samplewidth*8-1)-1)
        p = self.samplerate/frequency
        for t in range(int(duration*self.samplerate)):
            y = 4*amplitude/p*(abs((t+p*0.75) % p - p/2)-p/4)
            samples.append(int(scale*y))
        return samples

    def sawtooth(self, frequency, duration, amplitude=1.0):
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 0.8*amplitude*(2**(self.samplewidth*8-1)-1)
        a = self.samplerate/frequency
        for t in range(int(duration*self.samplerate)):
            y = 2*(t/a - floor(0.5+t/a))
            samples.append(int(scale*y))
        return samples

    def pulse(self, frequency, width, duration, amplitude=1.0):
        assert 0 <= amplitude <= 1.0
        assert 0 < width <= 0.5
        samples = self._get_array()
        wave_width = self.samplerate/frequency
        pulse_width = wave_width * width
        scale = int(0.8*amplitude*(2**(self.samplewidth*8-1)-1))
        for t in range(int(duration*self.samplerate)):
            x = t % wave_width
            if x < pulse_width:
                samples.append(scale)
            else:
                samples.append(-scale)
        return samples

    def white_noise(self, duration, amplitude=1.0):
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = amplitude*(2**(self.samplewidth*8-1)-1)
        for t in range(int(duration*self.samplerate)):
            samples.append(random.randint(-scale, scale))
        return samples


def demo_tones():
    synth = Wavesynth()
    from pyaudio import PyAudio
    audio = PyAudio()
    stream = audio.open(format=audio.get_format_from_width(synth.samplewidth),
                        channels=1, rate=synth.samplerate, output=True)
    for wave in [synth.squareh, synth.square, synth.sine, synth.triangle, synth.sawtooth]:
        print(wave.__name__)
        for note, freq in notes4.items():
            print("   {:f} hz".format(freq))
            sample = wave(freq, duration=0.4)
            sample = synth.to_sample(sample).fadeout(0.1).fadein(0.02)
            sample.write_frames(stream)
    print("pulse")
    for note, freq in notes4.items():
        print("   {:f} hz".format(freq))
        sample = synth.pulse(freq, 0.1, duration=0.4)
        sample = synth.to_sample(sample).fadeout(0.1).fadein(0.02)
        sample.write_frames(stream)
    print("noise")
    sample = synth.white_noise(duration=1.5)
    sample = synth.to_sample(sample).fadeout(0.5).fadein(0.1)
    sample.write_frames(stream)
    stream.close()


def demo_song():
    synth = Wavesynth()
    import time
    print("Synthesizing tones...")
    notes = {note: key_freq(49+i) for i, note in enumerate(['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#'])}
    tempo = 0.3
    quarter_notes = {note: synth.to_sample(synth.sine(notes[note], tempo)).fadeout(0.1).fadein(0.02) for note in notes}
    half_notes = {note: synth.to_sample(synth.sine(notes[note], tempo*2)).fadeout(0.1).fadein(0.02) for note in notes}
    full_notes = {note: synth.to_sample(synth.sine(notes[note], tempo*4)).fadeout(0.1).fadein(0.02) for note in notes}
    song = "A A B. A D. C#.. ;  A A B. A E. D.. ;  A A A. F#.. D C#.. B ;  G G F#.. D E D ; ; "\
        "A A B. A D C#.. ; A A B. A E D. ; A A A. F#.. D C#.. B ; G G F#.. D E D ; ; "
    from pyaudio import PyAudio
    audio = PyAudio()
    stream = audio.open(format=audio.get_format_from_width(synth.samplewidth),
                        channels=1, rate=synth.samplerate, output=True)
    for note in song.split():
        if note == ";":
            print()
            time.sleep(tempo*2)
            continue
        print(note, end="  ", flush=True) 
        if note.endswith(".."):
            sample = full_notes[note[:-2]]
        elif note.endswith("."):
            sample = half_notes[note[:-1]]
        else:
            sample = quarter_notes[note]
        sample.write_frames(stream)
    stream.close()
    print()


def demo_plot():
    from matplotlib import pyplot as plot
    synth=Wavesynth(samplerate=1000)
    freq = 4
    s = synth.sawtooth(freq, duration=1)
    plot.plot(s)
    s = synth.sine(freq, duration=1)
    plot.plot(s)
    s = synth.triangle(freq, duration=1)
    plot.plot(s)
    s = synth.square(freq, duration=1)
    plot.plot(s)
    s = synth.squareh(freq, duration=1)
    plot.plot(s)
    s = synth.pulse(freq, 0.2, duration=1)
    plot.plot(s)
    plot.show()


if __name__ == "__main__":
    # demo_plot()
    # demo_tones()
    demo_song()
