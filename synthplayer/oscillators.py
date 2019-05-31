"""
Oscillators for the Sample waveform synthesizer.
Inspired by FM synthesizers such as the Yamaha DX-7 and TX81Z.
Creates various waveforms with adjustable parameters.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import itertools
import math
import sys
import random
from . import params


__all__ = ["Sine", "Triangle", "Square", "SquareH", "Sawtooth", "SawtoothH",
           "Pulse", "Harmonics", "WhiteNoise", "Linear", "Semicircle", "Pointy",
           "FastSine", "FastPulse", "FastTriangle", "FastSawtooth", "FastSquare", "FastSemicircle", "FastPointy",
           "EnvelopeFilter", "MixingFilter", "AmpModulationFilter", "DelayFilter", "EchoFilter",
           "ClipFilter", "AbsFilter", "NullFilter"]


class Oscillator:
    """
    Oscillator base class for several types of waveforms.
    You can also apply FM to an osc, and/or an ADSR envelope.
    These are generic oscillators and as such have floating-point inputs and result values
    with variable amplitude (though usually -1.0...1.0), depending on what parameters you use.
    Using a FM LFO is computationally quite heavy, so if you know you don't use FM,
    consider using the Fast versions instead. They contain optimized algorithms but
    some of their parameters cannot be changed.
    """
    def __init__(self, source=None, samplerate=0):
        self._samplerate = samplerate or source._samplerate
        self._source = source

    def __iter__(self):
        return self.generator()

    def generator(self):
        yield from self._source


class EnvelopeFilter(Oscillator):
    """
    Applies an ADSR volume envelope to the source.
    A,D,S,R are in seconds, sustain_level is an amplitude factor.
    """
    def __init__(self, source, attack, decay, sustain, sustain_level, release, stop_at_end=False, cycle=False):
        assert attack >= 0 and decay >= 0 and sustain >= 0 and release >= 0
        assert 0 <= sustain_level <= 1
        super().__init__(source)
        self._attack = attack
        self._decay = decay
        self._sustain = sustain
        self._sustain_level = sustain_level
        self._release = release
        self._stop_at_end = stop_at_end
        self._cycle = cycle

    def generator(self):
        oscillator = iter(self._source)
        while True:
            time = 0.0
            end_time_decay = self._attack + self._decay
            end_time_sustain = end_time_decay + self._sustain
            end_time_release = end_time_sustain + self._release
            increment = 1/self._samplerate
            if self._attack:
                amp_change = 1.0/self._attack*increment
                amp = 0.0
                while time < self._attack:
                    yield next(oscillator)*amp
                    amp += amp_change
                    time += increment
            if self._decay:
                amp = 1.0
                amp_change = (self._sustain_level-1.0)/self._decay*increment
                while time < end_time_decay:
                    yield next(oscillator)*amp
                    amp += amp_change
                    time += increment
            while time < end_time_sustain:
                yield next(oscillator)*self._sustain_level
                time += increment
            if self._release:
                amp = self._sustain_level
                amp_change = (-self._sustain_level)/self._release*increment
                while time < end_time_release:
                    yield next(oscillator)*amp
                    amp += amp_change
                    time += increment
                if amp > 0.0:
                    yield next(oscillator)*amp
            if not self._cycle:
                break
        if not self._stop_at_end:
            yield from itertools.repeat(0.0)


class MixingFilter(Oscillator):
    """Mixes (adds) the wave from various sources together into one output wave."""
    def __init__(self, *sources):
        super().__init__(sources[0])
        self._sources = sources

    def generator(self):
        sources = [iter(src) for src in self._sources]
        source_values = itertools.zip_longest(*sources, fillvalue=0.0)
        try:
            while True:
                yield sum(next(source_values))
        except StopIteration:
            return


class AmpModulationFilter(Oscillator):
    """Modulate the amplitude of the wave of the oscillator by another oscillator (the modulator)."""
    def __init__(self, source, modulator):
        super().__init__(source)
        self.modulator = modulator

    def generator(self):
        modulator = iter(self.modulator)
        try:
            for v in self._source:
                yield v*next(modulator)
        except StopIteration:
            return


class DelayFilter(Oscillator):
    """
    Delays the source, or skips ahead in time (when using a negative delay value).
    Note that if you want to precisely phase-shift an oscillator, you should
    use the phase parameter on the oscillator function itself instead.
    """
    def __init__(self, source, seconds):
        super().__init__(source)
        self._seconds = seconds

    def generator(self):
        if self._seconds < 0.0:
            amount = int(-self._samplerate*self._seconds)
            next(itertools.islice(self._source, amount, amount), None)   # consume
        else:
            yield from itertools.repeat(0.0, int(self._samplerate*self._seconds))
        yield from self._source


class EchoFilter(Oscillator):
    """
    Mix given number of echos of the oscillator into itself.
    The decay is the factor with which each echo is decayed in volume (can be >1 to increase in volume instead).
    If you use a very short delay the echos blend into the sound and the effect is more like a reverb.
    """
    def __init__(self, source, after, amount, delay, decay):
        super().__init__(source)
        if decay < 1:
            # avoid computing echos that have virtually zero amplitude:
            amount = int(min(amount, math.log(0.000001, decay)))
        self._after = after
        self._amount = amount
        self._delay = delay
        self._decay = decay
        self.echo_duration = self._after + self._amount*self._delay

    def generator(self):
        # first play the first part till the echos start
        yield from itertools.islice(self._source, int(self._samplerate*self._after))
        # now start mixing the echos
        amp = self._decay
        echo_oscs = [Oscillator(src, samplerate=self._samplerate) for src in itertools.tee(self._source, self._amount+1)]
        echos = [echo_oscs[0]]
        echo_delay = self._delay
        for echo in echo_oscs[1:]:
            echo = DelayFilter(echo, echo_delay)
            echo = AmpModulationFilter(echo, itertools.repeat(amp))
            # @todo sometimes mixing the echos causes pops and clicks. Perhaps solvable by using a (very fast) fadein on the echo osc?
            echos.append(echo)
            echo_delay += self._delay
            amp *= self._decay
        echos = [iter(echo) for echo in echos]
        try:
            while True:
                yield sum([next(echo) for echo in echos])
        except StopIteration:
            return


class ClipFilter(Oscillator):
    """Clips the values from a source at the given mininum and/or maximum value."""
    def __init__(self, source, minimum=sys.float_info.min, maximum=sys.float_info.max):
        super().__init__(source)
        self.min = minimum
        self.max = maximum

    def generator(self):
        vmax, vmin = self.max, self.min     # optimization
        try:
            for v in self._source:
                yield max(min(v, vmax), vmin)
        except StopIteration:
            return


class AbsFilter(Oscillator):
    """Returns the absolute value of the source values."""
    def __init__(self, source):
        super().__init__(source)

    def generator(self):
        fabs = math.fabs  # optimization
        try:
            for v in self._source:
                yield fabs(v)
        except StopIteration:
            return


class NullFilter(Oscillator):
    """Wraps an oscillator but does nothing."""
    def __init__(self, source):
        super().__init__(source)

    def generator(self):
        yield from self._source


class Sine(Oscillator):
    """Sine Wave oscillator."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        # The FM compensates for the phase change by means of phase_correction.
        # See http://stackoverflow.com/questions/3089832/sine-wave-glissando-from-one-pitch-to-another-in-numpy
        # and http://stackoverflow.com/questions/28185219/generating-vibrato-sine-wave
        # The same idea is applied to the other waveforms to correct their phase with FM.
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase

    def generator(self):
        phase_correction = self._phase*2*math.pi
        freq_previous = self.frequency
        increment = 2.0*math.pi/self._samplerate
        t = 0.0
        # optimizations:
        sin = math.sin
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            yield sin(t*freq+phase_correction)*amplitude+bias
            t += increment


class Triangle(Oscillator):
    """Perfect triangle wave oscillator (not using harmonics)."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase

    def generator(self):
        phase_correction = self._phase
        freq_previous = self.frequency
        increment = 1.0/self._samplerate
        t = 0.0
        # optimizations:
        fabs = math.fabs
        frequency = self.frequency
        fm = self.fm
        bias = self.bias
        amplitude = self.amplitude
        # loop:
        while True:
            freq = frequency * (1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            tt = t*freq+phase_correction
            yield 4.0*amplitude*(fabs((tt+0.75) % 1.0 - 0.5)-0.25)+bias
            t += increment


class Square(Oscillator):
    """Perfect square wave [max/-max] oscillator (not using harmonics)."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase

    def generator(self):
        phase_correction = self._phase
        freq_previous = self.frequency
        increment = 1.0/self._samplerate
        t = 0.0
        # optimizations:
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            tt = t*freq + phase_correction
            yield (-amplitude if int(tt*2) % 2 else amplitude)+bias
            t += increment


class Sawtooth(Oscillator):
    """Perfect sawtooth waveform oscillator (not using harmonics)."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase

    def generator(self):
        increment = 1.0/self._samplerate
        freq_previous = self.frequency
        phase_correction = self._phase
        t = 0.0
        # optimizations:
        floor = math.floor
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            tt = t*freq + phase_correction
            yield bias+amplitude*2.0*(tt - floor(0.5+tt))
            t += increment


class Pulse(Oscillator):
    """
    Oscillator for a perfect pulse waveform (not using harmonics).
    Optional FM and/or Pulse-width modulation. If you use PWM, pulsewidth is ignored.
    The pwm_lfo oscillator will be clipped between 0 and 1 as pulse width factor.
    """
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, pulsewidth=0.1, fm_lfo=None, pwm_lfo=None, samplerate=0):
        assert 0 <= pulsewidth <= 1
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.pulsewidth = pulsewidth
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self.pwm = iter(pwm_lfo or itertools.repeat(pulsewidth))
        self._phase = phase

    def generator(self):
        epsilon = sys.float_info.epsilon
        increment = 1.0/self._samplerate
        freq_previous = self.frequency
        phase_correction = self._phase
        t = 0.0
        # optimizations:
        frequency = self.frequency
        fm = self.fm
        pwm = self.pwm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            pw = next(pwm)
            if pw <= 0.0:
                pw = epsilon
            elif pw >= 1.0:
                pw = 1.0-epsilon
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            tt = t*freq+phase_correction
            yield (amplitude if tt % 1.0 < pw else -amplitude)+bias
            t += increment


class Harmonics(Oscillator):
    """
    Oscillator that produces a waveform based on harmonics.
    This is computationally intensive because many sine waves are added together.
    """
    def __init__(self, frequency, harmonics, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase
        self.harmonics = harmonics

    def generator(self):
        increment = 2.0*math.pi/self._samplerate
        phase_correction = self._phase*2.0*math.pi
        freq_previous = self.frequency
        t = 0.0
        # only keep harmonics below the Nyquist frequency
        harmonics = list(filter(lambda h: h[0]*self.frequency <= self._samplerate/2, self.harmonics))
        # optimizations:
        sin = math.sin
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            h = 0.0
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            q = t*freq + phase_correction
            for k, amp in harmonics:
                h += sin(q*k)*amp
            yield h*amplitude+bias
            t += increment


class SquareH(Harmonics):
    """
    Oscillator that produces a square wave based on harmonic sine waves.
    It is a lot heavier to generate than square because it has to add many individual sine waves.
    It's done by adding only odd-integer harmonics, see https://en.wikipedia.org/wiki/Square_wave
    """
    def __init__(self, frequency, num_harmonics=16, amplitude=0.9999, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        harmonics = [(n, 1.0/n) for n in range(1, num_harmonics*2, 2)]  # only the odd harmonics
        super().__init__(frequency, harmonics, amplitude, phase, bias, fm_lfo=fm_lfo, samplerate=samplerate or params.norm_samplerate)


class SawtoothH(Harmonics):
    """
    Oscillator that produces a sawtooth wave based on harmonic sine waves.
    It is a lot heavier to generate than square because it has to add many individual sine waves.
    It's done by adding all harmonics, see https://en.wikipedia.org/wiki/Sawtooth_wave
    """
    def __init__(self, frequency, num_harmonics=16, amplitude=0.9999, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        harmonics = [(n, 1.0/n) for n in range(1, num_harmonics+1)]  # all harmonics
        super().__init__(frequency, harmonics, amplitude, phase+0.5, bias, fm_lfo=fm_lfo, samplerate=samplerate or params.norm_samplerate)

    def generator(self):
        try:
            for y in super().generator():
                yield self.bias*2.0-y
        except StopIteration:
            return


class WhiteNoise(Oscillator):
    """Oscillator that produces white noise (randomness) waveform."""
    def __init__(self, frequency, amplitude=1.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.amplitude = amplitude
        self.bias = bias
        self.frequency = frequency

    def generator(self):
        cycles = int(self._samplerate / self.frequency)
        if cycles < 1:
            raise ValueError("whitenoise frequency cannot be bigger than the sample rate")
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            value = random.uniform(-amplitude, amplitude) + bias
            yield from [value] * cycles


class Linear(Oscillator):
    """Oscillator that produces a linear sloped value, until it reaches a maximum or minimum value."""
    def __init__(self, startlevel, increment=0.0, min_value=-1.0, max_value=1.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.value = startlevel
        self.increment = increment
        self.min_value = min_value
        self.max_value = max_value

    def generator(self):
        # optimizations:
        value = self.value
        max_value = self.max_value
        min_value = self.min_value
        increment = self.increment
        # loop:
        while True:
            yield value
            if increment:
                value = min(max_value, max(min_value, value+increment))


class Semicircle(Oscillator):
    """Semicircle half wave ('W3') oscillator."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._phase = phase
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))

    def generator(self):
        phase_correction = self._phase * 2.0
        freq_previous = self.frequency
        increment = 2.0/self._samplerate
        t = -1.0
        # optimizations:
        sqrt = math.sqrt
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            ft = t*freq + phase_correction
            ft = (ft % 2.0) - 1.0
            yield sqrt(1.0 - ft*ft) * amplitude + bias
            t += increment


class Pointy(Oscillator):
    """Pointy Wave ('inverted cosine', 'W2') oscillator."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, fm_lfo=None, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = iter(fm_lfo or itertools.repeat(0.0))
        self._phase = phase

    def generator(self):
        two_pi = 2*math.pi
        phase_correction = self._phase*two_pi
        freq_previous = self.frequency
        increment = two_pi/self._samplerate
        t = 0.0
        # optimizations:
        cos = math.cos
        frequency = self.frequency
        fm = self.fm
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            freq = frequency*(1.0+next(fm))
            phase_correction += (freq_previous-freq)*t
            freq_previous = freq
            tt = t*freq + phase_correction
            vv = 1.0-abs(cos(tt))
            if tt % two_pi > math.pi:
                yield -vv*vv*amplitude+bias
            else:
                yield vv*vv*amplitude+bias
            t += increment


class FastSine(Oscillator):
    """Fast sine wave oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        rate = self._samplerate/self._frequency
        increment = 2.0*math.pi/rate
        t = self._phase*2.0*math.pi
        # optimizations:
        sin = math.sin
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            yield sin(t)*amplitude+bias
            t += increment


class FastTriangle(Oscillator):
    """Fast perfect triangle wave oscillator (not using harmonics). Some parameters cannot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self._samplerate
        # optimizations:
        fabs = math.fabs
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            yield 4.0*amplitude*(fabs((t*freq+0.75) % 1.0 - 0.5)-0.25)+bias
            t += increment


class FastSquare(Oscillator):
    """Fast perfect square wave [max/-max] oscillator (not using harmonics). Some parameters cannot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self._samplerate
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            yield (-amplitude if int(t*freq*2) % 2 else amplitude)+bias
            t += increment


class FastSawtooth(Oscillator):
    """Fast perfect sawtooth waveform oscillator (not using harmonics). Some parameters canot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self._samplerate
        # optimizations:
        floor = math.floor
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            tt = t*freq
            yield bias+2.0*amplitude*(tt - floor(0.5+tt))
            t += increment


class FastPulse(Oscillator):
    """
    Fast oscillator that produces a perfect pulse waveform (not using harmonics).
    Some parameters cannot be changed.
    Optional Pulse-width modulation. If used, the pulsewidth argument is ignored.
    The pwm_lfo oscillator will be clipped between 0 and 1 as pulse width factor.
    """
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, pulsewidth=0.1, pwm_lfo=None, samplerate=0):
        assert 0 <= pulsewidth <= 1
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self._pulsewidth = pulsewidth
        self._pwm = pwm_lfo
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        if self._pwm:
            # optimized loop without FM, but with PWM
            epsilon = sys.float_info.epsilon
            freq = self._frequency
            pwm = iter(self._pwm)
            t = self._phase/freq
            increment = 1.0/self._samplerate
            while True:
                pw = next(pwm)
                if pw <= 0.0:
                    pw = epsilon
                elif pw >= 1.0:
                    pw = 1.0-epsilon
                yield (amplitude if t*freq % 1.0 < pw else -amplitude)+bias
                t += increment
        else:
            # no FM, no PWM
            freq = self._frequency
            pw = self._pulsewidth
            t = self._phase/freq
            increment = 1.0/self._samplerate
            while True:
                yield (amplitude if t*freq % 1.0 < pw else -amplitude)+bias
                t += increment


class FastSemicircle(Oscillator):
    """Fast semicircle half wave ('W3') oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        rate = self._samplerate/self._frequency
        increment = 2.0/rate
        t = -1.0 + self._phase * 2
        sqrt = math.sqrt   # optimization
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            yield sqrt(1.0 - t*t) * amplitude + bias
            t += increment
            if t >= 1.0:
                t -= 2.0


class FastPointy(Oscillator):
    """Fast pointy wave ('inverted cosine', 'W2') oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency, amplitude=1.0, phase=0.0, bias=0.0, samplerate=0):
        super().__init__(samplerate=samplerate or params.norm_samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def generator(self):
        rate = self._samplerate/self._frequency
        two_pi = 2.0*math.pi
        increment = two_pi/rate
        t = self._phase*two_pi
        # optimizations:
        cos = math.cos
        amplitude = self.amplitude
        bias = self.bias
        # loop:
        while True:
            t %= two_pi
            vv = 1.0-abs(cos(t))
            if t > math.pi:
                yield -vv*vv*amplitude+bias
            else:
                yield vv*vv*amplitude+bias
            t += increment
