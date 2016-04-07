import sys
import wave
import time
from rhythmbox import Sample, Output, LevelMeter


def play(filename_or_stream):
    with wave.open(filename_or_stream, 'r') as wav:
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
                out.play_sample(sample, async=True)
                time.sleep(sample.duration/3)   # print the peak meter more or less halfway during the sample
                level_l, peak_l, level_r, peak_r = levelmeter.process(sample)
                db_mixed = (level_l+level_r)/2
                peak_mixed = (peak_l+peak_r)/2
                db_level = int(bar_width-bar_width*db_mixed/lowest_level)
                peak_indicator = int(bar_width-bar_width*peak_mixed/lowest_level)
                db_meter = ("#"*db_level).ljust(bar_width)
                db_meter = db_meter[:peak_indicator]+'!'+db_meter[peak_indicator:]
                print("{:d} dB |{:s}| 0 dB".format(int(lowest_level), db_meter), end="\r")
    print("\ndone")
    input("Enter to exit:")


def convert_to_wav(filename):
    print("Using ffmpeg to convert input file to .wav stream...")
    import subprocess
    command = ["ffmpeg", "-hide_banner", "-loglevel", "panic", "-i", filename, "-f", "wav", "-"]
    converter = subprocess.Popen(command, stdout=subprocess.PIPE)
    return converter.stdout


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("give audio file to play as an argument.")
    filename = sys.argv[1]
    if not filename.endswith(".wav"):
        play(convert_to_wav(filename))
    else:
        play(filename)
