import os
import sys
from synthesizer.streaming import AudiofileToWavStream, StreamMixer
from synthesizer.sample import Output, LevelMeter


def main(args):
    if len(args) < 1:
        raise SystemExit("Mixes one or more audio files. Arguments: inputfile...")
    hqresample = AudiofileToWavStream.supports_hq_resample()
    if not hqresample:
        print("WARNING: ffmpeg isn't compiled with libsoxr, so hq resampling is not supported.")
    wav_streams = [AudiofileToWavStream(filename, hqresample=hqresample) for filename in args]
    with StreamMixer(wav_streams, endless=True) as mixer:
        mixed_samples = iter(mixer)
        with Output(mixer.samplerate, mixer.samplewidth, mixer.nchannels, queuesize=200) as output:
            levelmeter = LevelMeter(rms_mode=False, lowest=-50)
            for timestamp, sample in mixed_samples:
                levelmeter.update(sample)    # @todo update it from the actual sample that is currently played rather than put into the queue
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
