from rhythmbox import Sample
from math import sin, pi, floor
import array
import sys
import audioop

__all__ = ["sine", "square", "squareh", "triangle", "sawtooth"]


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
        return Sample.from_raw_frames(frames, samplewidth, samplerate, 1)

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
        rate = samplerate/frequency/4
        for t in range(int(duration*samplerate)):
            samples.append(int(scale*(abs((t/rate) % 4 - 2)-1)))
        return self._to_sample(samples, samplewidth, samplerate)

    def sawtooth(self, frequency, duration, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_sampwidth, amplitude=1.0):
        samples = self._get_array(samplewidth)
        scale = amplitude*(2**(samplewidth*8-1)-1)
        a = samplerate/frequency
        for t in range(int(duration*samplerate)):
            y = 2*(t/a - floor(0.5+t/a))
            samples.append(int(scale*y))
        return self._to_sample(samples, samplewidth, samplerate)


def demo():
    synth = Wavesynth()
    from rhythmbox import Repl
    r = Repl()
    waves = [synth.squareh, synth.square, synth.sine, synth.triangle, synth.sawtooth]
    for wave in waves:
        print(wave.__name__)
        freq = 110
        for i in range(5):
            sample = wave(freq, duration=0.5)
            print("   {:d} hz".format(freq))
            r.play_sample(sample)
            freq *= 2

if __name__ == "__main__":
    demo()
