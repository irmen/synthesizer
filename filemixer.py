import os
import sys
import time
from synthesizer.streaming import AudiofileToWavStream, StreamMixer
from synthesizer.sample import Output, Sample, LevelMeter


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
            levelmeter = LevelMeter(rms_mode=False, lowest=-50)
            for timestamp, sample in mixed_samples:
                levelmeter.update(sample)
                output.play_sample(sample)
                time.sleep(sample.duration*0.4)
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
    
