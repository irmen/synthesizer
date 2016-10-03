import sys
from synthesizer.tools import AudiofileToWavStream, StreamMixer
from synthesizer.sample import Output, Sample


def get_wav_stream(filename):
    stream = AudiofileToWavStream(filename, samplerate=Sample.norm_samplerate,
                                channels=Sample.norm_nchannels,
                                sampleformat=str(8*Sample.norm_samplewidth))
    print(stream.filename)
    return stream.convert()


def main(args):
    if len(args) < 1:
        raise SystemExit("Mixes one or more audio files. Arguments: inputfile...")
    wav_streams = [get_wav_stream(filename) for filename in args]
    with StreamMixer(wav_streams, endless=True) as mixer:
        mixed_samples = iter(mixer)
        with Output(mixer.samplerate, mixer.samplewidth, mixer.nchannels) as output:
            for timestamp, sample in mixed_samples:
                if 10.0 <= timestamp <= 10.1:
                    stream = get_wav_stream("samples/909_crash.wav")
                    mixer.add_stream(stream, close_when_done=True)
                output.play_sample(sample)
    print("done.")


if __name__ == "__main__":
    main(sys.argv[1:])
