"""
Play a large file by using sequential play of small chunks,
and as another solution, a single sample that streams chunks itself on demand.
Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import os
from synthplayer.playback import Output
from synthplayer.streaming import AudiofileToWavStream, SampleStream, StreamingSample
from synthplayer.sample import Sample


if __name__ == "__main__":
    afmt = AudiofileToWavStream.probe_format("example_mixes/track3.mp3")

    # ** Streaming a large mp3 file using the realtime mixer output **
    # This output mixing mode is meant to play small samples at specific
    # points in time, possibly overlapping others (mixing them together).
    # Playing a long sample or music file doesn't map nicely to this pattern.
    # Instead, just play it _as a single huge sample_ where the sample itself
    # takes care of dynamically producing its audio data chunks.
    print("Streaming mp3 using realtime mixer...")
    counter = 1

    def played_callback(sample):
        global counter
        print(" played sound chunk", counter, end="\r")
        counter += 1

    with AudiofileToWavStream("example_mixes/track3.mp3") as wavstream:
        sample = StreamingSample(wavstream, wavstream.name)
        hihat = Sample("samples/909_hihat_closed.wav").normalize()
        with Output(mixing="mix", frames_per_chunk=afmt.rate//10) as out:
            out.register_notify_played(played_callback)
            # as an example, we show the capability of real time mixing by adding some other samples in the timeline
            out.play_sample(hihat, delay=0.0)
            out.play_sample(hihat, delay=0.5)
            out.play_sample(hihat, delay=1.0)
            out.play_sample(hihat, delay=1.5)
            out.play_sample(sample, delay=2.0)
            out.wait_all_played()    # the mixer itself takes care of grabbing new data as needed

    # ** Streaming a large mp3 file using the sequential mixing output **
    # This is more efficient for just playing large music files,
    # and can be done by simply playing sample chunks one after another.
    print("Streaming mp3 using sequential mixer...")
    with AudiofileToWavStream("example_mixes/track3.mp3") as wavstream:
        with SampleStream(wavstream, afmt.rate//10) as samples:
            with Output(mixing="sequential", queue_size=3) as out:
                for n, sample in enumerate(samples):
                    print(" playing next sample...", n, end="\r")
                    out.play_sample(sample)
                out.wait_all_played()
    try:
        import tty
        os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
    except ImportError:
        pass
    print("\n\nEnter to exit:")
    input()
