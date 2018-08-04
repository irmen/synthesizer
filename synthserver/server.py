import itertools
from typing import Sequence
from synthplayer import synth, sample
import Pyro4
from Pyro4.util import SerializerBase


Pyro4.config.SERIALIZER = "marshal"
Pyro4.config.SERIALIZERS_ACCEPTED = {"marshal"}


def sample_serializer(s: sample.Sample):
    return {
        "__class__": "synthplayer.sample.Sample",
        "samplerate": s.samplerate,
        "samplewidth": s.samplewidth,
        "duration": s.duration,
        "nchannels": s.nchannels,
        "name": s.name,
        "frames": s.view_frame_data()
    }


SerializerBase.register_class_to_dict(sample.Sample, sample_serializer)


@Pyro4.expose
@Pyro4.behavior(instance_mode="session")
class WaveSynthServer:
    def __init__(self):
        self.synth = None       # type: synth.WaveSynth

    def setup(self, samplerate: int=44100, samplewidth: int=2) -> None:
        self.synth = synth.WaveSynth(samplerate, samplewidth)

    def sine(self, frequency, duration, amplitude=0.9999, phase=0.0, bias=0.0):
        return self.synth.sine(frequency, duration, amplitude, phase, bias)

    def sine_gen(self, chunksize, frequency, amplitude=0.9999, phase=0.0, bias=0.0):
        gen = self.synth.sine_gen(frequency, amplitude, phase, bias)
        while True:
            values = list(itertools.islice(gen, chunksize))
            yield sample.Sample.from_array(values, self.synth.samplerate, 1)

    def square(self, frequency, duration, amplitude=0.75, phase=0.0, bias=0.0):
        return self.synth.square(frequency, duration, amplitude, phase, bias)

    def square_gen(self, chunksize, frequency, amplitude=0.75, phase=0.0, bias=0.0):
        gen = self.synth.square_gen(frequency, amplitude, phase, bias)
        return gen  # XXX

    def square_h(self, frequency, duration, num_harmonics=16, amplitude=0.9999, phase=0.0, bias=0.0):
        return self.synth.square_h(frequency, duration, num_harmonics, amplitude, phase, bias)

    def square_h_gen(self, chunksize, frequency, num_harmonics=16, amplitude=0.9999, phase=0.0, bias=0.0):
        gen = self.synth.square_h_gen(frequency, num_harmonics, amplitude, phase, bias)
        return gen  # XXX

    def triangle(self, frequency, duration, amplitude=0.9999, phase=0.0, bias=0.0):
        return self.synth.triangle(frequency, duration, amplitude, phase, bias)

    def triangle_gen(self, chunksize, frequency, amplitude=0.9999, phase=0.0, bias=0.0):
        gen = self.synth.triangle_gen(frequency, amplitude, phase, bias)
        return gen  # XXX

    def sawtooth(self, frequency, duration, amplitude=0.75, phase=0.0, bias=0.0):
        return self.synth.sawtooth(frequency, duration, amplitude, phase, bias)

    def sawtooth_gen(self, chunksize, frequency, amplitude=0.75, phase=0.0, bias=0.0):
        gen = self.synth.sawtooth_gen(frequency, amplitude, phase, bias)
        return gen  # XXX

    def sawtooth_h(self, frequency, duration, num_harmonics=16, amplitude=0.5, phase=0.0, bias=0.0):
        return self.synth.sawtooth_h(frequency, duration, num_harmonics, amplitude, phase, bias)

    def sawtooth_h_gen(self, chunksize, frequency, num_harmonics=16, amplitude=0.5, phase=0.0, bias=0.0):
        gen = self.synth.sawtooth_h_gen(frequency, num_harmonics, amplitude, phase, bias)
        return gen  # XXX

    def pulse(self, frequency, duration, amplitude=0.75, phase=0.0, bias=0.0, pulsewidth=0.1):
        return self.synth.pulse(frequency, duration, amplitude, phase, bias, pulsewidth)

    def pulse_gen(self, chunksize, frequency, amplitude=0.75, phase=0.0, bias=0.0, pulsewidth=0.1):
        gen = self.synth.pulse_gen(frequency, amplitude, phase, bias, pulsewidth)
        return gen  # XXX

    def harmonics(self, frequency, duration, harmonics, amplitude=0.5, phase=0.0, bias=0.0):
        return self.synth.harmonics(frequency, duration, harmonics, amplitude, phase, bias)

    def harmonics_gen(self, chunksize, frequency, harmonics, amplitude=0.5, phase=0.0, bias=0.0):
        gen = self.synth.harmonics_gen(frequency, harmonics, amplitude, phase, bias)
        return gen  # XXX

    def white_noise(self, frequency, duration, amplitude=0.9999, bias=0.0):
        return self.synth.white_noise(frequency, duration, amplitude, bias)

    def white_noise_gen(self, chunksize, frequency, amplitude=0.9999, bias=0.0):
        gen = self.synth.white_noise_gen(frequency, amplitude, bias)
        return gen  # XXX

    def semicircle(self, frequency, duration, amplitude=0.9999, phase=0.0, bias=0.0):
        return self.synth.semicircle(frequency, duration, amplitude, phase, bias)

    def semicircle_gen(self, chunksize, frequency, amplitude=0.9999, phase=0.0, bias=0.0):
        gen = self.synth.semicircle_gen(frequency, amplitude, phase, bias)
        return gen  # XXX

    def pointy(self, frequency, duration, amplitude=0.9999, phase=0.0, bias=0.0):
        return self.synth.pointy(frequency, duration, amplitude, phase, bias)

    def pointy_gen(self, chunksize, frequency, amplitude=0.9999, phase=0.0, bias=0.0):
        gen = self.synth.pointy_gen(frequency, amplitude, phase, bias)
        return gen  # XXX


Pyro4.Daemon.serveSimple({
    WaveSynthServer: "synth.wavesynth"
})
