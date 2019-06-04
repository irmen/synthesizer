"""
Oscillators for the Sample waveform synthesizer.
Inspired by FM synthesizers such as the Yamaha DX-7 and TX81Z.
Creates various waveforms with adjustable parameters.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import itertools
from math import pi, sin, cos, log, fabs, floor, sqrt
import sys
import random
from typing import Generator, List, Sequence, Optional, Tuple, Iterator
from abc import abstractmethod, ABC
from . import params


__all__ = ["Oscillator", "OscillatorFromSingleSamples", "Filter", "Sine", "Triangle", "Square",
           "SquareH", "Sawtooth", "SawtoothH", "Pulse", "Harmonics", "WhiteNoise", "Linear", "Semicircle", "Pointy",
           "FastSine", "FastPulse", "FastTriangle", "FastSawtooth", "FastSquare", "FastSemicircle", "FastPointy",
           "EnvelopeFilter", "MixingFilter", "AmpModulationFilter", "DelayFilter", "EchoFilter",
           "ClipFilter", "AbsFilter", "NullFilter"]


class Oscillator(ABC):
    """
    Oscillator base class for several types of waveforms.
    You can also apply FM to an osc, and/or an ADSR envelope.
    These are generic oscillators and as such have floating-point inputs and result values
    with variable amplitude (though usually -1.0...1.0), depending on what parameters you use.
    Using a FM LFO is computationally quite heavy, so if you know you don't use FM,
    consider using the Fast versions instead. They contain optimized algorithms but
    some of their parameters cannot be changed.

    For optimization reasons, the oscillator will always return a chunk/block of values
    rather than single individual values. When running this code using Pypy this
    results in a really big speedup. Also, usually, its not single values we're interested in,
    but rather a waveform.
    """
    def __init__(self, samplerate: int = 0) -> None:
        self.samplerate = samplerate or params.norm_samplerate

    @abstractmethod
    def blocks(self) -> Generator[List[float], None, None]:
        pass


class OscillatorFromSingleSamples(Oscillator):
    """
    Oscillator that wraps a generator of single sample values.
    (oscillators return their values in blocks)
    """
    def __init__(self, source: Iterator[float], samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.sample_source = source

    def blocks(self) -> Generator[List[float], None, None]:
        while True:
            block = list(itertools.islice(self.sample_source, params.norm_osc_blocksize))
            if block:
                yield block
            else:
                break


class Filter(Oscillator, ABC):
    def __init__(self, sources: Sequence[Oscillator]) -> None:
        super().__init__(sources[0].samplerate if sources else 0)
        self.sources = sources


class EnvelopeFilter(Filter):
    """
    Applies an ADSR volume envelope to the source.
    A,D,S,R are in seconds, sustain_level is an amplitude factor.
    """
    def __init__(self, source: Oscillator, attack: float, decay: float, sustain: float, sustain_level: float,
                 release: float, stop_at_end: bool = False) -> None:
        assert attack >= 0 and decay >= 0 and sustain >= 0 and release >= 0
        assert 0 <= sustain_level <= 1
        super().__init__([source])
        self._attack = attack
        self._decay = decay
        self._sustain = sustain
        self._sustain_level = sustain_level
        self._release = release
        self._stop_at_end = stop_at_end

    def blocks(self) -> Generator[List[float], None, None]:
        src = self.single_samples()
        try:
            while True:
                v = list(itertools.islice(src, params.norm_osc_blocksize))
                if not v:
                    return
                yield v
        except StopIteration:
            return

    def samples_from_source(self) -> Generator[float, None, None]:
        try:
            blocks = self.sources[0].blocks()
            while True:
                yield from next(blocks)
        except StopIteration:
            return

    def single_samples(self) -> Generator[float, None, None]:
        oscillator = self.samples_from_source()
        time = 0.0
        end_time_decay = self._attack + self._decay
        end_time_sustain = end_time_decay + self._sustain
        end_time_release = end_time_sustain + self._release
        increment = 1/self.samplerate
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
        if not self._stop_at_end:
            yield from itertools.repeat(0.0)


class MixingFilter(Filter):
    """Mixes (adds) the wave from various sources together into one output wave."""
    def __init__(self, *sources: Oscillator) -> None:
        super().__init__(sources)

    def blocks(self) -> Generator[List[float], None, None]:
        sources = [src.blocks() for src in self.sources]
        source_blocks = itertools.zip_longest(*sources, fillvalue=[0.0]*params.norm_osc_blocksize)
        try:
            while True:
                blocks = next(source_blocks)
                yield [sum(v) for v in zip(*blocks)]
        except StopIteration:
            return


class AmpModulationFilter(Filter):
    """Modulate the amplitude of the wave of the oscillator by another oscillator (the modulator)."""
    def __init__(self, source: Oscillator, modulator: Oscillator) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])
        self.modulator = modulator.blocks()

    def blocks(self) -> Generator[List[float], None, None]:
        source_blocks = self.sources[0].blocks()
        try:
            while True:
                block = next(source_blocks)
                amp = next(self.modulator)
                yield [v*a for (v, a) in zip(block, amp)]
        except StopIteration:
            return


class DelayFilter(Filter):
    """
    Delays the source, or skips ahead in time (when using a negative delay value).
    Note that if you want to precisely phase-shift an oscillator, you should
    use the phase parameter on the oscillator function itself instead.
    """
    def __init__(self, source: Oscillator, seconds: float) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])
        self._seconds = seconds

    def blocks(self) -> Generator[List[float], None, None]:
        blocks = self.sources[0].blocks()
        if self._seconds == 0.0:
            yield from blocks
            return
        elif self._seconds > 0.0:
            amount = int(self.samplerate * self._seconds)
            while amount >= params.norm_osc_blocksize:
                yield [0.0] * params.norm_osc_blocksize
                amount -= params.norm_osc_blocksize
            if amount == 0:
                yield from blocks
            residue = [0.0] * amount
        else:
            amount = -int(self.samplerate * self._seconds)
            while amount >= params.norm_osc_blocksize:
                next(blocks)
                amount -= params.norm_osc_blocksize
            if amount == 0:
                yield from blocks
            residue = next(blocks)[:amount]
        try:
            while True:
                sample_block = next(blocks)
                yield residue + sample_block[:-len(residue)]
                residue = sample_block[-len(residue):]
        except StopIteration:
            yield residue + [0.0] * (params.norm_osc_blocksize-len(residue))


class EchoFilter(Filter):
    """
    Mix given number of echos of the oscillator into itself.
    The amp_factor is the factor with which each echo changes in volume (<1 for decay, >1 to get louder).
    If you use a very short delay the echos blend into the sound and the effect is more like a reverb.
    """
    def __init__(self, source: Oscillator, after: float, amount: int, delay: float, amp_factor: float) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])
        if amp_factor < 1:
            # avoid computing echos that have virtually zero amplitude:
            amount = int(min(float(amount), log(0.000001, amp_factor)))
        self._after = after
        self._amount = amount
        self._delay = delay
        self._decay = amp_factor
        self.echo_duration = self._after + self._amount*self._delay

    def blocks(self) -> Generator[List[float], None, None]:
        src = self.single_samples()
        try:
            while True:
                v = list(itertools.islice(src, params.norm_osc_blocksize))
                if not v:
                    return
                yield v
        except StopIteration:
            return

    def samples_from_source(self) -> Generator[float, None, None]:
        try:
            blks = self.sources[0].blocks()
            while True:
                yield from next(blks)
        except StopIteration:
            return

    def single_samples(self) -> Generator[float, None, None]:
        # first play the first part normally until the echos start
        source_samples = self.samples_from_source()
        yield from itertools.islice(source_samples, int(self.samplerate * self._after))
        # now start mixing the echos
        amp = self._decay
        echo_oscs = [OscillatorFromSingleSamples(src) for src in itertools.tee(source_samples, self._amount+1)]     # type: List[Oscillator]
        echos = [echo_oscs[0]]
        echo_delay = self._delay
        for echo in echo_oscs[1:]:
            echo2 = AmpModulationFilter(DelayFilter(echo, echo_delay), Linear(amp))
            # @todo sometimes mixing the echos causes pops and clicks. Perhaps solvable by using a (very fast) fadein on the echo osc?
            echos.append(echo2)
            echo_delay += self._delay
            amp *= self._decay
        echo_blocks = [echo.blocks() for echo in echos]
        try:
            while True:
                blocks = [next(echoblock) for echoblock in echo_blocks]
                yield from [sum(x) for x in zip(*blocks)]
        except StopIteration:
            return


class ClipFilter(Filter):
    """Clips the values from a source at the given mininum and/or maximum value."""
    def __init__(self, source: Oscillator, minimum: float = sys.float_info.min, maximum: float = sys.float_info.max) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])
        self.min = minimum
        self.max = maximum

    def blocks(self) -> Generator[List[float], None, None]:
        try:
            for block in self.sources[0].blocks():
                yield [max(min(v, self.max), self.min) for v in block]
        except StopIteration:
            return


class AbsFilter(Filter):
    """Returns the absolute value of the samples from the source oscillator."""
    def __init__(self, source: Oscillator) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])

    def blocks(self) -> Generator[List[float], None, None]:
        try:
            for block in self.sources[0].blocks():
                yield [fabs(v) for v in block]
        except StopIteration:
            return


class NullFilter(Filter):
    """Wraps a single oscillator but does nothing."""
    def __init__(self, source: Oscillator) -> None:
        assert isinstance(source, Oscillator)
        super().__init__([source])

    def blocks(self) -> Generator[List[float], None, None]:
        return self.sources[0].blocks()


class Sine(Oscillator):
    """Sine Wave oscillator."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0, bias: float = 0.0,
                 fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        # The FM compensates for the phase change by means of phase_correction.
        # See http://stackoverflow.com/questions/3089832/sine-wave-glissando-from-one-pitch-to-another-in-numpy
        # and http://stackoverflow.com/questions/28185219/generating-vibrato-sine-wave
        # The same idea is applied to the other waveforms to correct their phase with FM.
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        phase_correction = self._phase*2*pi
        freq_previous = self.frequency
        increment = 2.0*pi/self.samplerate
        t = 0.0
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                block.append(sin(t*freq+phase_correction)*amplitude+bias)
                t += increment
            yield block


class Triangle(Oscillator):
    """Perfect triangle wave oscillator (not using harmonics)."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0, bias: float = 0.0,
                 fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        phase_correction = self._phase
        freq_previous = self.frequency
        increment = 1.0/self.samplerate
        t = 0.0
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency * (1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                tt = t*freq+phase_correction
                block.append(4.0*amplitude*(fabs((tt+0.75) % 1.0 - 0.5)-0.25)+bias)
                t += increment
            yield block


class Square(Oscillator):
    """Perfect square wave [max/-max] oscillator (not using harmonics)."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0, bias: float = 0.0,
                 fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        phase_correction = self._phase
        freq_previous = self.frequency
        increment = 1.0/self.samplerate
        t = 0.0
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                tt = t*freq + phase_correction
                block.append((-amplitude if int(tt*2) % 2 else amplitude)+bias)
                t += increment
            yield block


class Sawtooth(Oscillator):
    """Perfect sawtooth waveform oscillator (not using harmonics)."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0, bias: float = 0.0,
                 fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        increment = 1.0/self.samplerate
        freq_previous = self.frequency
        phase_correction = self._phase
        t = 0.0
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                tt = t*freq + phase_correction
                block.append(bias+amplitude*2.0*(tt - floor(0.5+tt)))
                t += increment
            yield block


class Pulse(Oscillator):
    """
    Oscillator for a perfect pulse waveform (not using harmonics).
    Optional FM and/or Pulse-width modulation. If you use PWM, pulsewidth is ignored.
    The pwm_lfo oscillator will be clipped between 0 and 1 as pulse width factor.
    """
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0, bias: float = 0.0,
                 pulsewidth: float = 0.1, fm_lfo: Optional[Oscillator] = None,
                 pwm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        assert 0 <= pulsewidth <= 1
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.pulsewidth = pulsewidth
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self.pwm = pwm_lfo.blocks() if pwm_lfo else Linear(pulsewidth).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        increment = 1.0/self.samplerate
        freq_previous = self.frequency
        phase_correction = self._phase
        t = 0.0
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            pwm_block = next_pwm_block(self.pwm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                tt = t*freq+phase_correction
                block.append((amplitude if tt % 1.0 < pwm_block[i] else -amplitude)+bias)
                t += increment
            yield block


class Harmonics(Oscillator):
    """
    Oscillator that produces a waveform based on harmonics.
    This is computationally intensive because many sine waves are added together.
    """
    def __init__(self, frequency: float, harmonics: List[Tuple[int, float]], amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase
        self.harmonics = harmonics

    def blocks(self) -> Generator[List[float], None, None]:
        increment = 2.0*pi/self.samplerate
        phase_correction = self._phase*2.0*pi
        freq_previous = self.frequency
        t = 0.0
        # only keep harmonics below the Nyquist frequency
        harmonics = list(filter(lambda h: h[0] * self.frequency <= self.samplerate / 2, self.harmonics))
        # optimizations:
        frequency = self.frequency
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                h = 0.0
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                q = t*freq + phase_correction
                for k, amp in harmonics:
                    h += sin(q*k)*amp
                block.append(h*amplitude+bias)
                t += increment
            yield block


class SquareH(Harmonics):
    """
    Oscillator that produces a square wave based on harmonic sine waves.
    It is a lot heavier to generate than square because it has to add many individual sine waves.
    It's done by adding only odd-integer harmonics, see https://en.wikipedia.org/wiki/Square_wave
    """
    def __init__(self, frequency: float, num_harmonics: int = 16, amplitude: float = 0.9999, phase: float = 0.0,
                 bias: float = 0.0, fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        harmonics = [(n, 1.0/n) for n in range(1, num_harmonics*2, 2)]  # only the odd harmonics
        super().__init__(frequency, harmonics, amplitude, phase, bias, fm_lfo=fm_lfo, samplerate=samplerate)


class SawtoothH(Harmonics):
    """
    Oscillator that produces a sawtooth wave based on harmonic sine waves.
    It is a lot heavier to generate than square because it has to add many individual sine waves.
    It's done by adding all harmonics, see https://en.wikipedia.org/wiki/Sawtooth_wave
    """
    def __init__(self, frequency: float, num_harmonics: int = 16, amplitude: float = 0.9999, phase: float = 0.0,
                 bias: float = 0.0, fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        harmonics = [(n, 1.0/n) for n in range(1, num_harmonics+1)]  # all harmonics
        super().__init__(frequency, harmonics, amplitude, phase+0.5, bias, fm_lfo=fm_lfo, samplerate=samplerate)

    def blocks(self) -> Generator[List[float], None, None]:
        try:
            for block in super().blocks():
                yield [self.bias*2.0-y for y in block]
        except StopIteration:
            return


class WhiteNoise(Oscillator):
    """Oscillator that produces white noise (randomness) waveform."""
    def __init__(self, frequency: float, amplitude: float = 1.0, bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.amplitude = amplitude
        self.bias = bias
        self.frequency = frequency

    def random_values(self) -> Generator[float, None, None]:
        cycles = int(self.samplerate / self.frequency)
        if cycles < 1:
            raise ValueError("whitenoise frequency cannot be bigger than the sample rate")
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            value = random.uniform(-amplitude, amplitude) + bias
            yield from [value] * cycles

    def blocks(self) -> Generator[List[float], None, None]:
        cycles = int(self.samplerate / self.frequency)
        if cycles < 1:
            raise ValueError("whitenoise frequency cannot be bigger than the sample rate")
        values = self.random_values()
        while True:
            v = list(itertools.islice(values, params.norm_osc_blocksize))
            if not v:
                return
            yield v


class Linear(Oscillator):
    """Oscillator that produces a linear sloped value, until it reaches a maximum or minimum value."""
    def __init__(self, startlevel: float, increment: float = 0.0,
                 min_value: float = -1.0, max_value: float = 1.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.value = startlevel
        self.increment = increment
        self.min_value = min_value
        self.max_value = max_value

    def blocks(self) -> Generator[List[float], None, None]:
        # optimizations
        value = self.value
        incr = self.increment
        maxv = self.max_value
        minv = self.min_value
        if incr:
            while True:
                block = []  # type: List[float]
                for _ in range(params.norm_osc_blocksize):
                    block.append(value)
                    value = min(maxv, max(minv, value+incr))
                yield block
        else:
            block = [value] * params.norm_osc_blocksize
            while True:
                yield list(block)


class Semicircle(Oscillator):
    """Semicircle half wave ('W3') oscillator."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._phase = phase
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()

    def blocks(self) -> Generator[List[float], None, None]:
        phase_correction = self._phase * 2.0
        freq_previous = self.frequency
        increment = 2.0/self.samplerate
        t = -1.0
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        frequency = self.frequency
        while True:
            block = []  # type: List[float]
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                ft = t*freq + phase_correction
                ft = (ft % 2.0) - 1.0
                block.append(sqrt(1.0 - ft*ft) * amplitude + bias)
                t += increment
            yield block


class Pointy(Oscillator):
    """Pointy Wave ('inverted cosine', 'W2') oscillator."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, fm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self.frequency = frequency
        self.amplitude = amplitude
        self.bias = bias
        self.fm = fm_lfo.blocks() if fm_lfo else Linear(0.0).blocks()
        self._phase = phase

    def blocks(self) -> Generator[List[float], None, None]:
        two_pi = 2*pi
        phase_correction = self._phase*two_pi
        freq_previous = self.frequency
        increment = two_pi/self.samplerate
        t = 0.0
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        frequency = self.frequency
        while True:
            block = []
            fm_block = next(self.fm)
            for i in range(params.norm_osc_blocksize):
                freq = frequency*(1.0+fm_block[i])
                phase_correction += (freq_previous-freq)*t
                freq_previous = freq
                tt = t*freq + phase_correction
                vv = 1.0-abs(cos(tt))
                if tt % two_pi > pi:
                    block.append(-vv*vv*amplitude+bias)
                else:
                    block.append(vv*vv*amplitude+bias)
                t += increment
            yield block


class FastSine(Oscillator):
    """Fast sine wave oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        rate = self.samplerate / self._frequency
        increment = 2.0*pi/rate
        t = self._phase*2.0*pi
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []
            for _ in range(params.norm_osc_blocksize):
                block.append(sin(t)*amplitude+bias)
                t += increment
            yield block


class FastTriangle(Oscillator):
    """Fast perfect triangle wave oscillator (not using harmonics). Some parameters cannot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self.samplerate
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []
            for _ in range(params.norm_osc_blocksize):
                block.append(4.0*amplitude*(fabs((t*freq+0.75) % 1.0 - 0.5)-0.25)+bias)
                t += increment
            yield block


class FastSquare(Oscillator):
    """Fast perfect square wave [max/-max] oscillator (not using harmonics). Some parameters cannot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self.samplerate
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            for _ in range(params.norm_osc_blocksize):
                block.append((-amplitude if int(t*freq*2) % 2 else amplitude)+bias)
                t += increment
            yield block


class FastSawtooth(Oscillator):
    """Fast perfect sawtooth waveform oscillator (not using harmonics). Some parameters canot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        freq = self._frequency
        t = self._phase/freq
        increment = 1.0/self.samplerate
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            for _ in range(params.norm_osc_blocksize):
                tt = t*freq
                block.append(bias+2.0*amplitude*(tt - floor(0.5+tt)))
                t += increment
            yield block


class FastPulse(Oscillator):
    """
    Fast oscillator that produces a perfect pulse waveform (not using harmonics).
    Some parameters cannot be changed.
    Optional Pulse-width modulation. If used, the pulsewidth argument is ignored.
    The pwm_lfo oscillator will be clipped between 0 and 1 as pulse width factor.
    """
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, pulsewidth: float = 0.1,
                 pwm_lfo: Optional[Oscillator] = None, samplerate: int = 0) -> None:
        assert 0 <= pulsewidth <= 1
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self._pulsewidth = pulsewidth
        self._pwm = pwm_lfo
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        # optimizations:
        amplitude = self.amplitude
        frequency = self._frequency
        bias = self.bias
        if self._pwm:
            # loop without FM, but with PWM
            pwm = self._pwm.blocks()
            t = self._phase/self._frequency
            increment = 1.0/self.samplerate
            while True:
                block = []  # type: List[float]
                pwm_block = next_pwm_block(pwm)
                for i in range(params.norm_osc_blocksize):
                    block.append((amplitude if t*frequency % 1.0 < pwm_block[i] else -amplitude)+bias)
                    t += increment
                yield block
        else:
            # no FM, no PWM
            pulsewidth = self._pulsewidth
            t = self._phase/self._frequency
            increment = 1.0/self.samplerate
            while True:
                block = []
                for _ in range(params.norm_osc_blocksize):
                    block.append((amplitude if t*frequency % 1.0 < pulsewidth else -amplitude)+bias)
                    t += increment
                yield block


def next_pwm_block(pwm: Generator[List[float], None, None]) -> List[float]:
    epsilon = sys.float_info.epsilon
    pwm_block = next(pwm)
    return [min(1.0-epsilon, max(epsilon, p)) for p in pwm_block]


class FastSemicircle(Oscillator):
    """Fast semicircle half wave ('W3') oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        rate = self.samplerate / self._frequency
        increment = 2.0/rate
        t = -1.0 + self._phase * 2
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            for _ in range(params.norm_osc_blocksize):
                block.append(sqrt(1.0 - t*t) * amplitude + bias)
                t += increment
                if t >= 1.0:
                    t -= 2.0
            yield block


class FastPointy(Oscillator):
    """Fast pointy wave ('inverted cosine', 'W2') oscillator. Some parameters cannot be changed."""
    def __init__(self, frequency: float, amplitude: float = 1.0, phase: float = 0.0,
                 bias: float = 0.0, samplerate: int = 0) -> None:
        super().__init__(samplerate)
        self._frequency = frequency
        self._phase = phase
        self.amplitude = amplitude
        self.bias = bias

    def blocks(self) -> Generator[List[float], None, None]:
        rate = self.samplerate / self._frequency
        two_pi = 2.0*pi
        increment = two_pi/rate
        t = self._phase*two_pi
        # optimizations:
        amplitude = self.amplitude
        bias = self.bias
        while True:
            block = []  # type: List[float]
            for _ in range(params.norm_osc_blocksize):
                t %= two_pi
                vv = 1.0-abs(cos(t))
                if t > pi:
                    block.append(-vv*vv*amplitude+bias)
                else:
                    block.append(vv*vv*amplitude+bias)
                t += increment
            yield block


def plot_waveforms() -> None:
    import matplotlib.pyplot as plot

    def get_data(osc: Oscillator) -> List[float]:
        return next(osc.blocks())

    samplerate = params.norm_osc_blocksize
    ncols = 4
    nrows = 3
    freq = 2.0
    harmonics = [(n, 1.0 / n) for n in range(3, 5 * 2, 2)]
    fm = FastSine(1, amplitude=0, bias=0, samplerate=samplerate)
    waveforms = [
        ('sine', get_data(Sine(freq, samplerate=samplerate))),
        ('square', get_data(Square(freq, samplerate=samplerate))),
        ('square_h', get_data(SquareH(freq, num_harmonics=5, samplerate=samplerate))),
        ('triangle', get_data(Triangle(freq, samplerate=samplerate))),
        ('sawtooth', get_data(Sawtooth(freq, samplerate=samplerate))),
        ('sawtooth_h', get_data(SawtoothH(freq, num_harmonics=5, samplerate=samplerate))),
        ('pulse', get_data(Pulse(freq, samplerate=samplerate))),
        ('harmonics', get_data(Harmonics(freq, harmonics=harmonics, samplerate=samplerate))),
        ('white_noise', get_data(WhiteNoise(50.0, samplerate=samplerate))),
        ('linear', get_data(Linear(20, 0.2, max_value=100, samplerate=samplerate))),
        ('W2-pointy', get_data(Pointy(freq, fm_lfo=fm, samplerate=samplerate))),
        ('W3-semicircle', get_data(Semicircle(freq, fm_lfo=fm, samplerate=samplerate)))
    ]
    plot.figure(1, figsize=(16, 10))
    plot.suptitle("waveforms (2 cycles)")
    for i, (waveformname, values) in enumerate(waveforms, start=1):
        ax = plot.subplot(nrows, ncols, i)
        ax.set_yticklabels([])
        ax.set_xticklabels([])
        plot.title(waveformname)
        plot.grid(True)
        plot.plot(values)
    plot.subplots_adjust(hspace=0.5, wspace=0.5, top=0.90, bottom=0.1, left=0.05, right=0.95)
    plot.show()


if __name__ == "__main__":
    plot_waveforms()
