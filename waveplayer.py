import sys
import wave
from rhythmbox import Sample, Output, LevelMeter


def play(filename):
    with wave.open(filename, 'r') as wav:
        samplewidth = wav.getsampwidth()
        samplerate = wav.getframerate()
        nchannels = wav.getnchannels()
        bar_width = 60
        lowest_level = -50.0
        update_rate = 20
        levelmeter = LevelMeter(rms_mode=False, lowest=lowest_level)
        with Output(samplerate, samplewidth, nchannels, int(update_rate/4)) as out:
            while True:
                frames = wav.readframes(samplerate//update_rate)
                if not frames:
                    break
                sample = Sample.from_raw_frames(frames, wav.getsampwidth(), wav.getframerate(), wav.getnchannels())
                level_l, peak_l, level_r, peak_r = levelmeter.process(sample)
                db_mixed = (level_l+level_r)/2
                peak_mixed = (peak_l+peak_r)/2
                db_level = int((db_mixed-lowest_level)/(0.0-lowest_level)*bar_width)
                peak_indicator = int((peak_mixed-lowest_level)/(0.0-lowest_level)*bar_width)
                db_meter = ("#"*db_level).ljust(bar_width)
                db_meter = db_meter[:peak_indicator]+'!'+db_meter[peak_indicator:]
                print("{:d} dB |{:s}| 0 dB".format(int(lowest_level), db_meter), end="\r")
                out.play_sample(sample, async=True)
    print("\ndone")
    input("Enter to exit:")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("give wave file to play as an argument.")
    play(sys.argv[1])
