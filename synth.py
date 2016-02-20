"""
Sample waveform synthesizer.
Creates some simple waveform samples with adjustable parameters:
sine, triangle, square, sawtooth and white noise.

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


def key_freq(key_number):
    """
    Return the note frequency for the given piano key number.
    C4 is key 40 and A4 is key 49 (=440 hz).
    https://en.wikipedia.org/wiki/Piano_key_frequencies
    """
    return 2**((key_number-49)/12) * 440.0

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

    def _get_array(self, samplewidth):
        if samplewidth == 1:
            return array.array('b')
        elif samplewidth == 2:
            return array.array('h')
        elif samplewidth == 4:
            return array.array('l')
        else:
            raise ValueError("only samplewidth sizes 1, 2 and 4 are supported")

    def _to_sample(self, samplearray, samplewidth, samplerate):
        frames = samplearray.tobytes()
        if sys.byteorder == "big":
            frames = audioop.byteswap(bytes, samplewidth)
        return Sample.from_raw_frames(frames, samplewidth, samplerate, 1).fadeout(0.1)

    def sine(self, frequency, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        samples = self._get_array(samplewidth)
        scale = amplitude*(2**(samplewidth*8-1)-1)
        rate = samplerate/frequency/2.0/pi
        for t in range(int(duration*samplerate)):
            samples.append(int(sin(t/rate)*scale))
        return self._to_sample(samples, samplewidth, samplerate)

    def square(self, frequency, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        """Generate a perfect square wave [max/-max]"""
        samples = self._get_array(samplewidth)
        scale = int(amplitude*(2**(samplewidth*8-1)-1))
        rate = samplerate/frequency
        for t in range(int(duration*samplerate)):
            x = t/rate
            y = 2*floor(x)-floor(x*2)+1
            samples.append(y*scale)
        return self._to_sample(samples, samplewidth, samplerate)

    def squareh(self, frequency, duration, num_harmonics=10, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        """Generate a square wave based on harmonic sine waves (more natural)"""
        samples = self._get_array(samplewidth)
        scale = int(amplitude*(2**(samplewidth*8-1)-1))
        f = frequency/samplerate
        for t in range(int(duration*samplerate)):
            h = 0.0
            q = 2*pi*f*t
            for k in range(1, num_harmonics+1):
                m = 2*k-1
                h += sin(q*m)/m
            # Formula says 4/pi but that only works on infinite series.
            # When dealing with a non infinite number of harmonics, the signal
            # can get 'off the scale' and needs to be clamped. We compensate
            # a little by not using 4/pi but 3.7/pi to reduce the number of clamps needed.
            # (clamping will distort the signal)
            y = int(3.7/pi*h*scale)
            y = max(min(y, scale), -scale)
            samples.append(y)
        return self._to_sample(samples, samplewidth, samplerate)

    def triangle(self, frequency, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        samples = self._get_array(samplewidth)
        scale = amplitude*(2**(samplewidth*8-1)-1)
        p = samplerate/frequency
        for t in range(int(duration*samplerate)):
            y = 4*amplitude/p*(abs((t+p*0.75) % p - p/2)-p/4)
            samples.append(int(scale*y))
        return self._to_sample(samples, samplewidth, samplerate)

    def sawtooth(self, frequency, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        samples = self._get_array(samplewidth)
        scale = amplitude*(2**(samplewidth*8-1)-1)
        a = samplerate/frequency
        for t in range(int(duration*samplerate)):
            y = 2*(t/a - floor(0.5+t/a))
            samples.append(int(scale*y))
        return self._to_sample(samples, samplewidth, samplerate)

    def pulse(self, frequency, duration, width=500, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        raise NotImplementedError  # XXX to be done

    def white_noise(self, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        samples = self._get_array(samplewidth)
        scale = amplitude*(2**(samplewidth*8-1)-1)
        for t in range(int(duration*samplerate)):
            samples.append(random.randint(-scale, scale))
        return self._to_sample(samples, samplewidth, samplerate)


def demo():
    synth = Wavesynth()
    waves = [synth.squareh, synth.square, synth.sine, synth.triangle, synth.sawtooth, synth.pulse]
    from rhythmbox import Repl
    r = Repl()
    for wave in waves:
        print(wave.__name__)
        for note, freq in notes4.items():
            print("   {:f} hz".format(freq))
            sample = wave(freq, duration=0.2)
            r.play_sample(sample)


def demo2():
    synth = Wavesynth()
    from rhythmbox import Repl
    import time
    r = Repl()
    print("Synthesizing tones...")
    notes = {note: key_freq(49+i) for i, note in enumerate(['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#'])}
    tempo = 0.2
    quarter_notes = {note: synth.triangle(notes[note], tempo) for note in notes}
    half_notes = {note: synth.triangle(notes[note], tempo*2) for note in notes}
    full_notes = {note: synth.triangle(notes[note], tempo*4) for note in notes}
    song = "A A B. A D. C#.. ;  A A B. A E. D.. ;  A A A. F#.. D C#.. B ;  G G F#.. D E D ; ; ; ; "\
        "A A B. A D C#.. ; A A B. A E D. ; A A A. F#.. D C#.. B ; G G F#.. D E D ; ".split()
    for note in song:
        print(note, end="  ", flush=True)
        if note == ";":
            time.sleep(tempo)
            continue
        if note.endswith(".."):
            sample = full_notes[note[:-2]]
        elif note.endswith("."):
            sample = half_notes[note[:-1]]
        else:
            sample = quarter_notes[note]
        r.play_sample(sample)
    print()


if __name__ == "__main__":
    demo2()
    demo()
