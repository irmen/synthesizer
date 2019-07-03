from typing import Any, Dict
from synthplayer import sample
from synthplayer.playback import Output
from Pyro4.util import SerializerBase
import Pyro4


def sample_deserializer(classname: str, data: Dict[str, Any]) -> sample.Sample:
    return sample.Sample.from_raw_frames(data["frames"], data["samplewidth"],
                                         data["samplerate"], data["nchannels"], data["name"])


Pyro4.config.SERIALIZER = "marshal"
SerializerBase.register_dict_to_class("synthplayer.sample.Sample", sample_deserializer)
synth = Pyro4.Proxy("PYRONAME:synth.wavesynth")
synth.setup(44100)


with Output(44100, nchannels=1, samplewidth=2, mixing="sequential") as output:
    silence = sample.Sample.from_raw_frames(b"", samplewidth=2, samplerate=44100, numchannels=1)
    silence.add_silence(0.1)
    output.play_sample(synth.sine(220, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(330, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(440, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(550, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(660, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(770, .5))
    output.play_sample(silence)
    output.play_sample(synth.sine(880, .5))
    output.play_sample(silence)
    print("waiting until all tones have played...")
    output.wait_all_played()

    gen = synth.harmonics_gen(220, harmonics=[
        [1, 1],
        [3, 1/3],
        [5, 1/5],
        [7, 1/7],
        [9, 1/9]
    ])
    print("endless waveform stream. press ctrl-c to stop.")
    for s in gen:
        output.play_sample(s)
