"""
Play a large file by using sequential play of small chunks.
Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import os
from synthesizer.playback import Output
from synthesizer.streaming import AudiofileToWavStream, SampleStream, EndlessFramesFilter


if __name__ == "__main__":
    afmt = AudiofileToWavStream.probe_format("example_mixes/track3.mp3")
    frame_size = (afmt.bitspersample // 8) * afmt.channels * afmt.rate
    with AudiofileToWavStream("example_mixes/track3.mp3") as wavstream:
        with SampleStream(wavstream, frame_size//10) as samples:
            with Output(mixing="sequential", queue_size=3) as out:
                for n, sample in enumerate(samples):
                    print("playing next chunk...", n)
                    out.play_sample(sample)
                out.wait_all_played()
    try:
        import tty
        os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
    except ImportError:
        pass
    print("\nEnter to exit:")
    input()
