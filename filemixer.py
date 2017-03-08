import os
import sys
from synthesizer.streaming import AudiofileToWavStream, StreamMixer
from synthesizer.sample import LevelMeter
from synthesizer.playback import Output


def main(args):
    if len(args) < 1:
        raise SystemExit("Mixes one or more audio files. Arguments: inputfile...")
    hqresample = AudiofileToWavStream.supports_hq_resample()
    if not hqresample:
        print("WARNING: ffmpeg isn't compiled with libsoxr, so hq resampling is not supported.")
    wav_streams = [AudiofileToWavStream(filename, hqresample=hqresample) for filename in args]
    with StreamMixer(wav_streams, endless=True) as mixer:
        mixed_samples = iter(mixer)
        with Output(mixer.samplerate, mixer.samplewidth, mixer.nchannels) as output:
            if not output.supports_streaming:
                raise RuntimeError("need api that supports streaming")
            levelmeter = LevelMeter(rms_mode=False, lowest=-50)
            output.register_notify_played(levelmeter.update)
            for timestamp, sample in mixed_samples:
                output.play_sample(sample)
                levelmeter.print(bar_width=60)
    print("done.")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    finally:
        try:
            import tty
            os.system("stty sane")   # needed because spawning ffmpeg sometimes breaks the terminal...
        except ImportError:
            pass
