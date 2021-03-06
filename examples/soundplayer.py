"""
Sound file player that shows how you could stream an audio file to the sound
output device. It also shows you the sound Level Meter.

It plays .wav files without needing extra tools, if you want to play .mp3 or
other audio formats it uses the ffmpeg tool to convert the file.

By default a nice GUI with graphical level meters is shown but there's also
example code that plays the file and shows the level meter on the console.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import os
import sys
import wave
import time
import tkinter as tk
import tkinter.ttk as ttk
from synthplayer.sample import Sample, LevelMeter
from synthplayer.streaming import AudiofileToWavStream, SampleStream
from synthplayer.playback import Output


update_rate = 30


def play_console(filename_or_stream):
    with wave.open(filename_or_stream, 'r') as wav:
        samplewidth = wav.getsampwidth()
        samplerate = wav.getframerate()
        nchannels = wav.getnchannels()
        bar_width = 60
        levelmeter = LevelMeter(rms_mode=False, lowest=-50.0)
        with Output(samplerate, samplewidth, nchannels, mixing="sequential") as out:
            print("Audio API used:", out.audio_api)
            if not out.supports_streaming:
                raise RuntimeError("need api that supports streaming")
            out.register_notify_played(levelmeter.update)
            while True:
                frames = wav.readframes(samplerate//update_rate)
                if not frames:
                    break
                sample = Sample.from_raw_frames(frames, wav.getsampwidth(), wav.getframerate(), wav.getnchannels())
                out.play_sample(sample)
                levelmeter.print(bar_width)
            while out.still_playing():
                time.sleep(1/update_rate)
                levelmeter.print(bar_width)
            out.wait_all_played()
    print("\nDone. Enter to exit:")
    input()


class LevelGUI(tk.Frame):
    def __init__(self, audio_source, master=None):
        self.lowest_level = -50
        self.have_started_playing = False
        super().__init__(master)
        self.master.title("Levels")

        self.pbvar_left = tk.IntVar()
        self.pbvar_right = tk.IntVar()
        pbstyle = ttk.Style()
        pbstyle.theme_use("classic")
        pbstyle.configure("green.Vertical.TProgressbar", troughcolor="gray", background="light green")
        pbstyle.configure("yellow.Vertical.TProgressbar", troughcolor="gray", background="yellow")
        pbstyle.configure("red.Vertical.TProgressbar", troughcolor="gray", background="orange")

        frame = tk.LabelFrame(self, text="Left")
        frame.pack(side=tk.LEFT)
        tk.Label(frame, text="dB").pack()
        self.pb_left = ttk.Progressbar(frame, orient=tk.VERTICAL, length=300,
                                       maximum=-self.lowest_level, variable=self.pbvar_left,
                                       mode='determinate', style='yellow.Vertical.TProgressbar')
        self.pb_left.pack()

        frame = tk.LabelFrame(self, text="Right")
        frame.pack(side=tk.LEFT)
        tk.Label(frame, text="dB").pack()
        self.pb_right = ttk.Progressbar(frame, orient=tk.VERTICAL, length=300,
                                        maximum=-self.lowest_level, variable=self.pbvar_right,
                                        mode='determinate', style='yellow.Vertical.TProgressbar')
        self.pb_right.pack()

        frame = tk.LabelFrame(self, text="Info")
        self.info = tk.Label(frame, text="", justify=tk.LEFT)
        frame.pack()
        self.info.pack(side=tk.TOP)
        self.pack()
        self.open_audio_file(audio_source)
        self.after_idle(self.update)
        self.after_idle(self.stream_audio)

    def open_audio_file(self, filename_or_stream):
        wav = wave.open(filename_or_stream, 'r')
        self.samplewidth = wav.getsampwidth()
        self.samplerate = wav.getframerate()
        self.nchannels = wav.getnchannels()
        self.samplestream = iter(SampleStream(wav, self.samplerate // 10))
        self.levelmeter = LevelMeter(rms_mode=False, lowest=self.lowest_level)
        self.audio_out = Output(self.samplerate, self.samplewidth, self.nchannels, mixing="sequential", queue_size=3)
        print("Audio API used:", self.audio_out.audio_api)
        if not self.audio_out.supports_streaming:
            raise RuntimeError("need api that supports streaming")
        self.audio_out.register_notify_played(self.levelmeter.update)
        filename = filename_or_stream if isinstance(filename_or_stream, str) else "<stream>"
        info = "Source:\n{}\n\nRate: {:g} Khz\nBits: {}\nChannels: {}"\
            .format(filename, self.samplerate/1000, 8*self.samplewidth, self.nchannels)
        self.info.configure(text=info)

    def stream_audio(self):
        try:
            sample = next(self.samplestream)
            self.audio_out.play_sample(sample)
            self.have_started_playing = True
            self.after(20, self.stream_audio)
        except StopIteration:
            self.audio_out.close()

    def update(self):
        if not self.audio_out.still_playing() and self.have_started_playing:
            self.pbvar_left.set(0)
            self.pbvar_right.set(0)
            print("done!")
            return
        left, peak_l = self.levelmeter.level_left, self.levelmeter.peak_left
        right, peak_r = self.levelmeter.level_right, self.levelmeter.peak_right
        self.pbvar_left.set(left-self.lowest_level)
        self.pbvar_right.set(right-self.lowest_level)
        if left > -3:
            self.pb_left.configure(style="red.Vertical.TProgressbar")
        elif left > -6:
            self.pb_left.configure(style="yellow.Vertical.TProgressbar")
        else:
            self.pb_left.configure(style="green.Vertical.TProgressbar")
        if right > -3:
            self.pb_right.configure(style="red.Vertical.TProgressbar")
        elif right > -6:
            self.pb_right.configure(style="yellow.Vertical.TProgressbar")
        else:
            self.pb_right.configure(style="green.Vertical.TProgressbar")
        self.after(1000//update_rate, self.update)


def play_gui(file_or_stream):
    root = tk.Tk()
    app = LevelGUI(file_or_stream, master=root)
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("give audio file to play as an argument.")
    hqresample = AudiofileToWavStream.supports_hq_resample()
    with AudiofileToWavStream(sys.argv[1], hqresample=hqresample) as stream:
        print("Format probed: ", stream.format_probe)
        if stream.conversion_required and not hqresample:
            print("WARNING: ffmpeg isn't compiled with libsoxr, so hq resampling is not supported.")
        try:
            # play_console(stream)
            play_gui(stream)
        finally:
            try:
                import tty
                os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
            except ImportError:
                pass
