"""
Wave synth server.
Uses Pyro4 for the communication.
You can run this server in a separate process, perhaps using Pypy, to offload
the sample generation to another CPU core (at the cost of network communication overhead)

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

from typing import Any, Dict, Generator, List, Tuple
from synthplayer import synth, sample, params
import Pyro4
from Pyro4.util import SerializerBase


def sample_serializer(s: sample.Sample) -> Dict[str, Any]:
    return {
        "__class__": "synthplayer.sample.Sample",
        "samplerate": s.samplerate,
        "samplewidth": s.samplewidth,
        "duration": s.duration,
        "nchannels": s.nchannels,
        "name": s.name,
        "frames": s.view_frame_data()
    }


def sample_deserializer(classname: str, data: Dict[str, Any]) -> sample.Sample:
    return sample.Sample.from_raw_frames(data["frames"], data["samplewidth"],
                                         data["samplerate"], data["nchannels"], data["name"])


def register_client_sample_deserializer() -> None:
    """can/must be used by clients to deserialize data back into Sample objects"""
    SerializerBase.register_dict_to_class("synthplayer.sample.Sample", sample_deserializer)
    Pyro4.config.SERIALIZER = "marshal"


@Pyro4.expose
@Pyro4.behavior(instance_mode="session")
class WaveSynthServer:
    def __init__(self) -> None:
        self.synth = synth.WaveSynth()    # the synthesizer can be reconfigured by a call to setup()

    def setup(self, samplerate: int = 44100, samplewidth: int = 2, blocksize: int = 512) -> None:
        params.norm_osc_blocksize = blocksize
        self.synth = synth.WaveSynth(samplerate, samplewidth)

    def sine(self, frequency: int, duration: float, amplitude: float = 0.9999, phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.sine(frequency, duration, amplitude, phase, bias)

    def sine_gen(self, frequency: int, amplitude: float = 0.9999,
                 phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.sine_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def square(self, frequency: int, duration: float, amplitude: float = 0.75, phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.square(frequency, duration, amplitude, phase, bias)

    def square_gen(self, frequency: int, amplitude: float = 0.75,
                   phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.square_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def square_h(self, frequency: int, duration: float, num_harmonics: int = 16, amplitude: float = 0.9999,
                 phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.square_h(frequency, duration, num_harmonics, amplitude, phase, bias)

    def square_h_gen(self, frequency: int, num_harmonics: int = 16, amplitude: float = 0.9999,
                     phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.square_h_gen(frequency, num_harmonics, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def triangle(self, frequency: int, duration: float, amplitude: float = 0.9999, phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.triangle(frequency, duration, amplitude, phase, bias)

    def triangle_gen(self, frequency: int, amplitude: float = 0.9999,
                     phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.triangle_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def sawtooth(self, frequency: int, duration: float, amplitude: float = 0.75, phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.sawtooth(frequency, duration, amplitude, phase, bias)

    def sawtooth_gen(self, frequency: int, amplitude: float = 0.75,
                     phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.sawtooth_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def sawtooth_h(self, frequency: int, duration: float, num_harmonics: int = 16, amplitude: float = 0.5,
                   phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.sawtooth_h(frequency, duration, num_harmonics, amplitude, phase, bias)

    def sawtooth_h_gen(self, frequency: int, num_harmonics: int = 16, amplitude: float = 0.5,
                       phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.sawtooth_h_gen(frequency, num_harmonics, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def pulse(self, frequency: int, duration: float, amplitude: float = 0.75,
              phase: float = 0.0, bias: float = 0.0, pulsewidth: float = 0.1) -> sample.Sample:
        return self.synth.pulse(frequency, duration, amplitude, phase, bias, pulsewidth)

    def pulse_gen(self, frequency: int, amplitude: float = 0.75,
                  phase: float = 0.0, bias: float = 0.0, pulsewidth: float = 0.1) -> Generator[sample.Sample, None, None]:
        gen = self.synth.pulse_gen(frequency, amplitude, phase, bias, pulsewidth)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def harmonics(self, frequency: int, duration: float, harmonics: List[Tuple[int, float]], amplitude: float = 0.5,
                  phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.harmonics(frequency, duration, harmonics, amplitude, phase, bias)

    def harmonics_gen(self, frequency: int, harmonics: List[Tuple[int, float]], amplitude: float = 0.5,
                      phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.harmonics_gen(frequency, harmonics, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def white_noise(self, frequency: int, duration: float, amplitude: float = 0.9999, bias: float = 0.0) -> sample.Sample:
        return self.synth.white_noise(frequency, duration, amplitude, bias)

    def white_noise_gen(self, frequency: int, amplitude: float = 0.9999, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.white_noise_gen(frequency, amplitude, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def semicircle(self, frequency: int, duration: float, amplitude: float = 0.9999,
                   phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.semicircle(frequency, duration, amplitude, phase, bias)

    def semicircle_gen(self, frequency: int, amplitude: float = 0.9999,
                       phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.semicircle_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)

    def pointy(self, frequency: int, duration: float, amplitude: float = 0.9999,
               phase: float = 0.0, bias: float = 0.0) -> sample.Sample:
        return self.synth.pointy(frequency, duration, amplitude, phase, bias)

    def pointy_gen(self, frequency: int, amplitude: float = 0.9999,
                   phase: float = 0.0, bias: float = 0.0) -> Generator[sample.Sample, None, None]:
        gen = self.synth.pointy_gen(frequency, amplitude, phase, bias)
        while True:
            chunk = next(gen)
            yield sample.Sample.from_array(chunk, self.synth.samplerate, 1)


if __name__ == "__main__":
    Pyro4.config.SERIALIZER = "marshal"
    Pyro4.config.SERIALIZERS_ACCEPTED = {"marshal"}
    SerializerBase.register_class_to_dict(sample.Sample, sample_serializer)
    Pyro4.Daemon.serveSimple({
        WaveSynthServer: "synth.wavesynth"
    })
