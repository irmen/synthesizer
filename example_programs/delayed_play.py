"""
Plays a couple of samples each at a certain delayed time.
Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import os
import time
from synthesizer.sample import Sample
from synthesizer.playback import Output


def play_console():
    s1 = Sample("samples/909_clap.wav").normalize()
    s2 = Sample("samples/909_hi_tom.wav").normalize()
    s3 = Sample("samples/909_ride.wav").normalize()
    s4 = Sample("samples/Drop the bass now.wav").normalize()
    s5 = Sample("samples/909_snare_drum.wav").normalize()

    with Output.for_sample(s1) as out:
        print("Audio API used:", out.audio_api)
        if not out.supports_streaming:
            raise RuntimeError("need api that supports streaming")

        print("\nUsing time.sleep to time sounds.")
        out.play_sample(s1)
        time.sleep(0.5)
        out.play_sample(s2)
        time.sleep(0.5)
        out.play_sample(s3)
        time.sleep(0.5)
        out.play_sample(s4)
        time.sleep(0.3)
        out.play_sample(s5)
        time.sleep(0.3)
        out.play_sample(s5)
        time.sleep(0.3)
        out.play_sample(s5)
        print("(waiting until all sounds have been played)")
        out.wait_all_played()

        print("\nNow using mixer delay to time sounds.")
        print("The program continues while playback is handled in the background!")
        out.play_sample(s1, delay=0.0)
        out.play_sample(s2, delay=0.5)
        out.play_sample(s3, delay=1.0)
        out.play_sample(s4, delay=1.5)
        out.play_sample(s5, delay=1.8)
        out.play_sample(s5, delay=2.1)
        out.play_sample(s5, delay=2.4)
        print("(Samples queued. Now waiting until all sounds have been played)")
        out.wait_all_played()

    print("\nDone. Enter to exit:")
    input()


if __name__ == "__main__":
    play_console()
    try:
        import tty
        os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
    except ImportError:
        pass
