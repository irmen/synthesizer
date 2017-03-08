"""
Sample mixer and sequencer meant to create rhythms. Inspired by the Roland TR-909.
Sample mix rate is configured at 44.1 khz. You may want to change this if most of
the samples you're using are of a different sample rate (such as 48Khz), to avoid
the slight loss of quality due to resampling.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import sys
import os
from synthesizer.mixer import Song, Repl
from synthesizer.sample import Sample
from synthesizer.playback import Output


def main(track_file, outputfile=None, interactive=False):
    discard_unused = not interactive
    if interactive:
        repl = Repl(discard_unused_instruments=discard_unused)
        repl.do_load(track_file)
        repl.cmdloop("Interactive Samplebox session. Type 'help' for help on commands.")
    else:
        song = Song()
        song.read(track_file, discard_unused_instruments=discard_unused)
        with Output(queuesize=3) as out:
            if out.supports_streaming:
                # mix and stream output in real time
                print("Mixing and streaming to speakers...")
                out.play_samples(song.mix_generator())
                print("\r                          ")
                out.wait_all_played()
            else:
                # output can't stream, fallback on mixing everything to a wav
                print("(Sorry, streaming audio is not possible, perhaps because you don't have sounddevice or pyaudio installed?)")
                song.mix(outputfile)
                mix = Sample(wave_file=outputfile)
                print("Playing sound...")
                out.play_sample(mix)
                out.wait_all_played()


def usage():
    print("Arguments:  [-i] trackfile.ini")
    print("   -i = start interactive editing mode")
    raise SystemExit(1)

if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        usage()
    track_file = None
    interactive = False
    if len(sys.argv) == 2:
        if sys.argv[1] == "-i":
            usage()  # need a trackfile as well to at least initialize the samples
        else:
            track_file = sys.argv[1]
    elif len(sys.argv) == 3:
        if sys.argv[1] != "-i":
            usage()
        interactive = True
        track_file = sys.argv[2]
    if interactive:
        main(track_file, interactive=True)
    else:
        output_file = os.path.splitext(track_file)[0]+".wav"
        main(track_file, output_file)
