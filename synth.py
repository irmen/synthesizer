"""
Sample waveform synthesizer.
Creates some simple waveform samples with adjustable parameters.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""
# @TODO the FM logic isn't quite correct it needs to compensate the phase change:
# see http://stackoverflow.com/questions/3089832/sine-wave-glissando-from-one-pitch-to-another-in-numpy
# and http://stackoverflow.com/questions/28185219/generating-vibrato-sine-wave
from rhythmbox import Sample
from math import sin, pi, floor
import random
import array

__all__ = ["key_freq", "Wavesynth"]


def key_freq(key_number, a4=440.0):
    """
    Return the note frequency for the given piano key number.
    C4 is key 40 and A4 is key 49 (=440 hz).
    https://en.wikipedia.org/wiki/Piano_key_frequencies
    """
    return 2**((key_number-49)/12) * a4


class Wavesynth:
    """
    Waveform sample synthesizer. Can generate various wave forms based on mathematic functions:
    sine, square (perfect or with harmonics), triangle, sawtooth (perfect or with harmonics),
    variable harmonics, white noise.  It also supports an optional LFO for Frequency Modulation.
    """
    def __init__(self, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth):
        if samplewidth not in (1, 2, 4):
            raise ValueError("only samplewidth sizes 1, 2 and 4 are supported")
        self.samplerate = samplerate
        self.samplewidth = samplewidth
        self.oscillator = Oscillator(self.samplerate)

    def _get_array(self):
        if self.samplewidth == 1:
            return array.array('b')
        elif self.samplewidth == 2:
            return array.array('h')
        elif self.samplewidth == 4:
            return array.array('l')
        else:
            raise ValueError("only samplewidth sizes 1, 2 and 4 are supported")

    def to_sample(self, sample_array, fadeout=True):
        s = Sample.from_array(sample_array, self.samplerate, 1)
        return s.fadeout(0.1 if fadeout else 0)

    def sine(self, frequency, duration, amplitude=1.0, phase=0.0, fmlfo=None):
        """Simple sine wave. Optional FM using a supplied LFO."""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.sine(frequency, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def square(self, frequency, duration, amplitude=0.8, phase=0.0, fmlfo=None):
        """
        Generate a perfect square wave [max/-max].
        It is fast, but the square wave is not as 'natural' sounding as the ones
        generated by the square_h function (which is based on harmonics).
        """
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.square(frequency, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def square_h(self, frequency, duration, num_harmonics=12, amplitude=1.0, phase=0.0, fmlfo=None):
        """Generate a square wave based on harmonic sine waves (more natural sounding than pure square)"""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.square_h(frequency, num_harmonics, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def triangle(self, frequency, duration, amplitude=1.0, phase=0.0, fmlfo=None):
        """Perfect triangle waveform (not using harmonics). Optional FM using a supplied LFO."""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.triangle(frequency, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def sawtooth(self, frequency, duration, amplitude=0.8, phase=0.0, fmlfo=None):
        """Perfect sawtooth waveform (not using harmonics)."""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.sawtooth(frequency, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def sawtooth_h(self, frequency, duration, num_harmonics=12, amplitude=0.8, phase=0.0, fmlfo=None):
        """Sawtooth waveform based on harmonic sine waves"""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.sawtooth_h(frequency, num_harmonics, amplitude, phase, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def pulse(self, frequency, width, duration, amplitude=0.8, phase=0.0, fmlfo=None, pwlfo=None):
        """Perfect pulse waveform (not using harmonics). Optional FM and/or Pulse-width modulation."""
        assert 0 <= amplitude <= 1.0
        assert 0 < width <= 0.5
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.pulse(frequency, width, amplitude, phase, fmlfo=fmlfo, pwlfo=pwlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def harmonics(self, frequency, duration, num_harmonics, amplitude=1.0, phase=0.0, only_even=False, only_odd=False, fmlfo=None):
        """Makes a waveform based on harmonics. This is slow because many sine waves are added together."""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.harmonics(frequency, num_harmonics, amplitude, phase, only_even=only_even, only_odd=only_odd, fmlfo=fmlfo)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples

    def white_noise(self, duration, amplitude=1.0):
        """White noise (randomness) waveform."""
        assert 0 <= amplitude <= 1.0
        samples = self._get_array()
        scale = 2**(self.samplewidth*8-1)-1
        waveform = self.oscillator.white_noise(amplitude)
        for _ in range(int(duration*self.samplerate)):
            samples.append(int(next(waveform)*scale))
        return samples


# @TODO add support to apply an ADSR envelope to the LFOs output
class Oscillator:
    """Oscillator that produces generators for several types of waveforms."""
    def __init__(self, samplerate=Sample.norm_samplerate):
        self.samplerate = samplerate

    def sine(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """Returns a generator that produces a sine wave. Optionally applies a FM LFO."""
        rate = self.samplerate/frequency
        increment = 1/rate*2*pi
        t = phase*2*pi
        if fmlfo:
            while True:
                yield sin(t+t*next(fmlfo))*amplitude+bias
                t += increment
        else:
            while True:
                yield sin(t)*amplitude+bias
                t += increment

    def sine_fm_correct_array(self, frequency, duration, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """XXX sine wave generator with correct FM using phase correction"""
        samples = []
        fmlfo = fmlfo or iter(int, 1)
        phase_correction = 0
        freq_previous = frequency
        for t in range(int(duration*self.samplerate)):
            t /= self.samplerate
            fm = next(fmlfo)
            fm_freq = frequency * (1+fm)
            phase_correction += (freq_previous-fm_freq)*2*pi*t
            freq_previous = fm_freq
            y = sin(2*pi*t*fm_freq+phase_correction+phase*2*pi)
            samples.append(y*amplitude+bias)
        return samples

    def sine_fm_correct_array_optimized(self, frequency, duration, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """XXX sine wave generator with correct FM using phase correction, optimized version (TODO)"""
        samples = []
        fmlfo = fmlfo or iter(int, 1)
        phase_correction = phase
        freq_previous = frequency
        for t in range(int(duration*self.samplerate)):
            t /= self.samplerate
            freq = frequency * (1+next(fmlfo))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            y = sin(2*pi*(t*freq+phase_correction))*amplitude+bias
            samples.append(y)
        return samples

    def triangle(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """Returns a generator that produces a perfect triangle wave (not using harmonics)."""
        rate = self.samplerate/frequency
        t = int(phase*rate)
        fmlfo = fmlfo or iter(int, 1)       # use endless zeros if no fmlfo supplied
        while True:
            tt = t + t*next(fmlfo)
            yield 4*amplitude/rate*(abs((tt+rate*0.75) % rate - rate/2)-rate/4)+bias
            t += 1

    def square(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """Returns a generator that produces a perfect square wave [max/-max] (not using harmonics)."""
        width = self.samplerate/frequency/2
        t = phase*2
        increment = 1/width
        if fmlfo:
            while True:
                yield (-amplitude if int(t+t*next(fmlfo)) % 2 else amplitude)+bias
                t += increment
        else:
            while True:
                yield (-amplitude if int(t) % 2 else amplitude)+bias
                t += increment

    def square_h(self, frequency, num_harmonics=12, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """
        Returns a generator that produces a square wave based on harmonic sine waves.
        It is a lot heavier to generate than square because it has to add many individual sine waves.
        It's done by adding only odd-integer harmonics, see https://en.wikipedia.org/wiki/Square_wave
        """
        return self.harmonics(frequency, num_harmonics, amplitude, phase, bias, only_odd=True, fmlfo=fmlfo)

    def sawtooth(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """Returns a generator that produces a perfect sawtooth waveform (not using harmonics)."""
        rate = self.samplerate/frequency
        increment = 1/rate
        t = phase
        if fmlfo:
            while True:
                tt = t + t*next(fmlfo)
                yield bias+amplitude*2*(tt - floor(0.5+tt))
                t += increment
        else:
            while True:
                yield bias+amplitude*2*(t - floor(0.5+t))
                t += increment

    def sawtooth_h(self, frequency, num_harmonics=12, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None):
        """
        Returns a generator that produces a sawtooth wave based on harmonic sine waves.
        It is a lot heavier to generate than square because it has to add many individual sine waves.
        It's done by adding all harmonics, see https://en.wikipedia.org/wiki/Sawtooth_wave
        """
        for y in self.harmonics(frequency, num_harmonics, amplitude, phase+0.5, bias, fmlfo=fmlfo):
            yield bias-y+bias

    def pulse(self, frequency, width, amplitude=1.0, phase=0.0, bias=0.0, fmlfo=None, pwlfo=None):
        """
        Returns a generator that produces a perfect pulse waveform (not using harmonics).
        Optional FM and/or Pulse-width modulation.
        """
        assert 0 < width <= 0.5
        wave_width = self.samplerate/frequency
        pulse_width = wave_width * width
        t = int(phase*wave_width)
        pwlfo = pwlfo or iter(int, 1)   # endless zeros if no pwm
        if fmlfo:
            while True:
                pw = pulse_width * (1+next(pwlfo))
                yield (amplitude if (t+t*next(fmlfo)) % wave_width < pw else -amplitude)+bias
                t += 1
        else:
            while True:
                pw = pulse_width * (1+next(pwlfo))
                yield (amplitude if t % wave_width < pw else -amplitude)+bias
                t += 1

    def harmonics(self, frequency, num_harmonics, amplitude=1.0, phase=0.0, bias=0.0, only_even=False, only_odd=False, fmlfo=None):
        """
        Returns a generator that produces a waveform based on harmonics.
        This is computationally intensive because many sine waves are added together.
        """
        f = frequency/self.samplerate
        t = phase
        while True:
            h = 0.0
            q = 2*pi*t
            if fmlfo:
                # loops including FM
                fm = next(fmlfo)
                if only_odd:
                    for k in range(1, 2*num_harmonics, 2):
                        v = q*k
                        h += sin(v+v*fm)/k
                elif only_even:
                    h += sin(q)*0.7  # always include harmonic #1 as base
                    for k in range(2, 2*num_harmonics, 2):
                        v = q*k
                        h += sin(v+v*fm)/k
                else:
                    for k in range(1, 1+num_harmonics):
                        v = q*k
                        h += sin(v+v*fm)/k/2
            else:
                # optimized loops without FM
                if only_odd:
                    for k in range(1, 2*num_harmonics, 2):
                        h += sin(q*k)/k
                elif only_even:
                    h += sin(q)*0.7  # always include harmonic #1 as base
                    for k in range(2, 2*num_harmonics, 2):
                        h += sin(q*k)/k
                else:
                    for k in range(1, 1+num_harmonics):
                        h += sin(q*k)/k/2
            yield h*amplitude + bias
            t += f

    def white_noise(self, amplitude=1.0, bias=0.0):
        """Returns a generator that produces white noise (randomness) waveform."""
        while True:
            yield random.uniform(-amplitude, amplitude) + bias
