from __future__ import division, print_function
import os
from samplebox import Mixer, Sample

samples = {
    "drop": "Drop the bass now.wav",
    "go": "Go.wav",
    "sos": "SOS 020.wav",
    "hardsnare1": "biab_hardsn_1.wav",
    "hardsnare2": "biab_hardsn_2.wav",
    "hardsnare3": "biab_hardsn_3.wav",
    "hardsnare4": "biab_hardsn_4.wav",
    "hardsnare5": "biab_hardsn_5.wav",
    "hihat1": "biab_hat_1.wav",
    "hihat2": "biab_hat_2.wav",
    "hihat3": "biab_hat_3.wav",
    "hihat4": "biab_hat_4.wav",
    "hihat5": "biab_hat_5.wav",
    "kick1": "biab_kick_1.wav",
    "kick2": "biab_kick_2.wav",
    "kick3": "biab_kick_3.wav",
    "kick4": "biab_kick_4.wav",
    "kick5": "biab_kick_5.wav",
    "kick6": "biab_kick_6.wav",
    "kick7": "biab_kick_7.wav",
    "kick8": "biab_kick_8.wav",
    "kick9": "biab_kick_9.wav",
    "kick10": "biab_kick_10.wav",
    "snare1": "biab_sn_1.wav",
    "snare2": "biab_sn_2.wav",
    "snare3": "biab_sn_3.wav",
    "snare4": "biab_sn_4.wav",
    "snare5": "biab_sn_5.wav",
    "snare6": "biab_sn_6.wav",
    "snare7": "biab_sn_7.wav",
    "snare8": "biab_sn_8.wav",
    "snare9": "biab_sn_9.wav",
    "snare10": "biab_sn_10.wav"
}


def main(samples_path="samples"):
    print("Loading samples...")
    for name, file in sorted(samples.items()):
        print("   ", name, end="")
        sample = Sample(wave_file=os.path.join(samples_path, file)).normalize().make_32bit(scale_amplitude=False).lock()
        samples[name] = sample
    print()
    instruments = {
        "q": samples["hihat1"],
        "w": samples["hihat2"],
        "e": samples["hihat4"],
        "a": samples["kick7"],
        "s": samples["kick9"],
        "z": samples["snare2"],
        "x": samples["snare10"],
        "A": samples["sos"].dup().amplify(0.3),
        "G": samples["go"],
        "D": samples["drop"]
    }
    tracks = [
        "A....... ........ ........ ........ ........ ........ ........ ........ ........ ........",
        "........ ........ ........ ........ D....... ........ G....... ........ ........ ........",
        "w...w... w...w... q...q... q...q... w...w... w...w... q...q... q...q... w.w.w.w. ........",
        "........ ........ ..e.e... ........ ........ ........ ..e.e... ........ ....e... ........",
        "a....... s....... ....a... s....... a....... s....... ....a... s....... ........ ........",
        "........ z....... ........ z....... ........ z....... x.....x. x.x.x... ........ ........",
    ]
    mixer = Mixer(tracks, 174, 8, instruments)   # 174 bpm ftw
    s = mixer.mix()
    s.make_16bit().write_wav("endmix.wav")
    print("done, result written to endmix.wav")


def test_mixing():
    # mix some
    print("mix one...")
    s = samples["bell"].dup()
    s.mix(samples["doing"]).make_16bit().write_wav("mixed1.wav")
    s = samples["bell"].dup()
    b = samples["doing"].dup().cut(0.3, 0.9)
    s.mix(b).make_16bit().write_wav("mixed1b.wav")
    # winsound.PlaySound("mixed1.wav", winsound.SND_FILENAME)
    print("mix two...")
    s = samples["drop"].dup()
    b = samples["bell"].dup().cut(1, 2)
    s.mix_at(1.8, b).make_16bit().write_wav("mixed2.wav")
    s = samples["drop"].dup()
    s.mix_at(1.0, samples["bell"]).make_16bit().write_wav("mixed2b.wav")
    # winsound.PlaySound("mixed2.wav", winsound.SND_FILENAME | winsound.SND_ASYNC)
    print("mix three...")
    s = Sample(duration=4).make_32bit()
    d = samples["drop"].dup()
    s.mix(d)
    s.mix_at(0.2, d.amplify(0.6))
    s.mix_at(0.4, d.amplify(0.4))
    s.make_16bit().write_wav("mixed3.wav")
    print("done.")

if __name__ == "__main__":
    main()
