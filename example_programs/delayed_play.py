"""
Plays a couple of samples each at a certain delayed time.
Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import os
import time
from synthplayer.sample import Sample
from synthplayer.playback import Output


s1 = Sample("samples/909_clap.wav").normalize()
s2 = Sample("samples/909_hi_tom.wav").normalize()
s3 = Sample("samples/909_ride.wav").normalize()
s4 = Sample("samples/Drop the bass now.wav").normalize()
s5 = Sample("samples/909_snare_drum.wav").normalize()
s6 = Sample("samples/909_hihat_closed.wav").normalize()
s6_soft = s6.copy().amplify(0.2)

with Output(mixing="sequential", queue_size=3) as out:
    if not out.supports_streaming:
        raise RuntimeError("need api that supports streaming")
    print("\nPlaying samples with sequential mixing mode.")
    print("This takes care of playing samples only if the previous one finished,")
    print("but you cannot mix any sounds. It's ideal for playback of a single sound source,")
    print("such as an audio clip or audio stream that comes in chunks.")
    out.play_sample(s1)
    out.play_sample(s2)
    out.play_sample(s3)
    out.play_sample(s4)
    out.play_sample(s5)
    out.play_sample(s5)
    out.play_sample(s5)
    out.play_sample(s6)
    out.wait_all_played()
print("\nEnter to continue:")
input()

with Output.for_sample(s1, mixing="mix") as out:
    if not out.supports_streaming:
        raise RuntimeError("need api that supports streaming")

    print("\nUsing time.sleep to time sounds.")
    sid6 = out.play_sample(s6_soft, repeat=True)
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
    time.sleep(0.3)
    out.play_sample(s6)
    time.sleep(1)
    out.stop_sample(sid6)
    print("(waiting until all sounds have been played)")
    out.wait_all_played()

    print("\nEnter to continue:")
    input()
    print("\nNow using mixer delay to time sounds.")
    print("The program continues while playback is handled in the background!")
    out.play_sample(s6_soft, repeat=True, delay=0.0)
    out.play_sample(s1, delay=0.0)
    out.play_sample(s2, delay=0.5)
    out.play_sample(s3, delay=1.0)
    out.play_sample(s4, delay=1.5)
    out.play_sample(s5, delay=1.8)
    out.play_sample(s5, delay=2.1)
    out.play_sample(s5, delay=2.4)
    out.play_sample(s6, delay=2.7)
    print("\nSamples queued and playing. Enter to exit:")
    input()

    try:
        import tty
        os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
    except ImportError:
        pass
