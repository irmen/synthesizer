from synthplayer.playback import Output
from synthplayer import params
from .drumkit import Instrument
from .gui import Gui


params.norm_samplerate = 48000
params.norm_samplewidth = 2


with Output(mixing="mix", queue_size=2) as output:
    print(output)

    currently_playing = {}

    def audio(key: str, name: str, instr: Instrument, velocity: int):
        if key in currently_playing:
            # stop the previous playing sample for that button
            output.stop_sample(currently_playing[key])
        volume, sample = instr.get_group(velocity).get_sample()
        sid = output.play_sample(sample)
        currently_playing[key] = sid

    gui = Gui(audio)
    gui.start("/mnt/nfs/media/SoundEffecs/salamander_drumkit_v1/")
