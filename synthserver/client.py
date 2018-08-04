from typing import Sequence
from synthplayer import sample
from synthplayer.playback import Output
import Pyro4
from Pyro4.util import SerializerBase


Pyro4.config.SERIALIZER = "marshal"


def sample_deserializer(classname, data):
    return sample.Sample.from_raw_frames(data["frames"], data["samplewidth"],
                                         data["samplerate"], data["nchannels"], data["name"])


SerializerBase.register_dict_to_class("synthplayer.sample.Sample", sample_deserializer)


synth = Pyro4.Proxy("PYRONAME:synth.wavesynth")
synth.setup(22050)
with Output(22050, nchannels=1, mixing="sequential") as output:
    silence = sample.Sample.from_raw_frames(b"", samplewidth=2, samplerate=22050, numchannels=1)
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
    print("waiting")
    output.wait_all_played()
# gen = synth.sine_gen(100, 220)
# print(gen)
# for i in gen:
#     print(i)
