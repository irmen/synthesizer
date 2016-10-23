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
            temp_stream = AudiofileToWavStream("samples/909_crash.wav", hqresample=hqresample)
            for timestamp, sample in mixed_samples:
                levelmeter.update(sample)
                output.play_sample(sample)
                time.sleep(sample.duration*0.4)
                levelmeter.print(bar_width=60)
                if 5.0 <= timestamp <= 5.1:
                    mixer.add_stream(temp_stream)
                if 10.0 <= timestamp <= 10.1:
                    sample = Sample("samples/909_crash.wav").normalize()
                    mixer.add_sample(sample)
    print("done.")


if __name__ == "__main__":
    main(sys.argv[1:])
