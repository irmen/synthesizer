import threading
import re
import subprocess
import tkinter
from tkinter import ttk
from collections import namedtuple
from PIL import Image, ImageTk
import requests
from synthplayer.playback import Output
from synthplayer.sample import Sample, LevelMeter


class IceCastClient:
    """
    A simple client for IceCast audio streams.
    The stream method yields blocks of encoded audio data from the stream.
    If the stream has Icy Meta Data, the stream_title attribute will be updated
    with the actual title taken from the meta data.
    """
    def __init__(self, url, block_size=16384):
        self.url = url
        self.stream_format = "???"
        self.stream_title = "???"
        self.station_genre = "???"
        self.station_name = "???"
        self.block_size = block_size

    def stream(self):
        with requests.get(self. url, stream=True, headers={"icy-metadata": "1"}) as result:
            self.station_genre = result.headers["icy-genre"]
            self.station_name = result.headers["icy-name"]
            self.stream_format = result.headers["Content-Type"]
            if "icy-metaint" in result.headers:
                meta_interval = int(result.headers["icy-metaint"])
            else:
                meta_interval = 0
            if meta_interval:
                audiodata = b""
                for chunk in result.iter_content(self.block_size):
                    audiodata += chunk
                    if len(audiodata) < meta_interval + 1:
                        continue
                    meta_size = 16 * audiodata[meta_interval]
                    if len(audiodata) < meta_interval + 1 + meta_size:
                        continue
                    metadata = str(audiodata[meta_interval + 1: meta_interval + 1 + meta_size].strip(b"\0"), "utf-8")
                    if metadata:
                        self.stream_title = re.search("StreamTitle='(.*?)'", metadata).group(1)
                    yield audiodata[:meta_interval]
                    audiodata = audiodata[meta_interval + 1 + meta_size:]
            else:
                yield from result.iter_content(self.block_size)


class AudioDecoder:
    """
    Reads streaming audio from an IceCast stream,
    decodes it using ffmpeg, and plays it on the output sound device.

    We need two threads:
     1) main thread that spawns ffmpeg, reads radio stream data, and writes that to ffmpeg
     2) background thread that reads decoded audio data from ffmpeg and plays it
    """
    def __init__(self, icecast_client, song_title_callback=None, levelmeter_callback=None):
        self.client = icecast_client
        self.stream_title = "???"
        self.song_title_callback = song_title_callback
        self.levelmeter_callback = levelmeter_callback
        self.ffmpeg_process = None

    def stop_playback(self):
        if self.ffmpeg_process:
            self.ffmpeg_process.kill()
            self.ffmpeg_process = None

    def _audio_playback(self, ffmpeg_stream):
        # thread 3: audio playback
        levelmeter = LevelMeter()

        def played(sample):
            if self.client.stream_title != self.stream_title:
                self.stream_title = self.client.stream_title
                if self.song_title_callback:
                    self.song_title_callback(self.stream_title)
                else:
                    print("\n\nNew Song:", self.stream_title, "\n")
            levelmeter.update(sample)
            if self.levelmeter_callback:
                self.levelmeter_callback(levelmeter)
            else:
                levelmeter.print(60, True)

        with Output(mixing="sequential", frames_per_chunk=44100//4) as output:
            output.register_notify_played(played)
            while True:
                audio = ffmpeg_stream.read(44100 * 2 * 2 // 10)
                if audio:
                    sample = Sample.from_raw_frames(audio, 2, 44100, 2)
                    output.play_sample(sample)
                else:
                    break

    def stream_radio(self):
        stream = self.client.stream()
        first_chunk = next(stream)
        format = ""
        if self.client.stream_format == "audio/mpeg":
            format = "mp3"
        elif self.client.stream_format.startswith("audio/aac"):
            format = "aac"
        if not self.song_title_callback:
            print("\nStreaming Radio Station: ", self.client.station_name)
        cmd = ["ffmpeg"]
        if format:
            cmd.extend(["-f", format])
        cmd.extend(["-i", "-", "-v", "fatal"])
        # cmd.extend(["-af", "aresample=resampler=soxr"])     # enable this if your ffmpeg has sox hq resample
        cmd.extend(["-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-f", "s16le", "-"])
        self.ffmpeg_process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.ffmpeg_process.stdin.write(first_chunk)
        audio_playback_thread = threading.Thread(target=self._audio_playback, args=[self.ffmpeg_process.stdout], daemon=True)
        audio_playback_thread.start()

        try:
            for chunk in stream:
                if self.ffmpeg_process:
                    self.ffmpeg_process.stdin.write(chunk)
                else:
                    break
        except BrokenPipeError:
            pass
        except KeyboardInterrupt:
            pass
        finally:
            audio_playback_thread.join()
            if not self.song_title_callback:
                print("\n")


class Internetradio(tkinter.Tk):
    StationDef = namedtuple("StationDef", ["station_name", "stream_name", "icon_url", "stream_url"])
    stations = [
        StationDef("Soma FM", "Groove Salad",
                   "http://somafm.com/img/groovesalad120.png",
                   "http://ice3.somafm.com/groovesalad-64-aac"),
        StationDef("Soma FM", "Secret Agent",
                   "http://somafm.com/img/secretagent120.jpg",
                   "http://ice3.somafm.com/secretagent-64-aac"),
        StationDef("University of Calgary", "CJSW-FM",
                   "https://upload.wikimedia.org/wikipedia/en/thumb/0/0e/CJSW-FM.svg/220px-CJSW-FM.svg.png",
                   "http://stream.cjsw.com:80/cjsw.ogg"),
        StationDef("Playtrance.com", "Trance",
                   "http://facilmediamundial.com/wp-content/uploads/2017/09/trance-200.png",
                   "http://live.playtrance.com:8000/playtrance-livetech.aac")
    ]

    def __init__(self):
        super().__init__()
        self.wm_title("Internet radio")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.geometry("+200+80")
        self.station_buttons = []
        for station in self.stations:
            button = tkinter.Button(self, text="\n"+station.station_name + "\n" + station.stream_name+"\n", width=14, height=8)
            button.pack()
            self.station_buttons.append(button)
        self.quit_button = tkinter.Button(self, text="quit", command=lambda: self.destroy())
        self.quit_button.pack()
        self.stream_name_label = tkinter.Label(self, text="Choose a station")
        self.stream_name_label.pack()
        self.song_title_label = tkinter.Label(self, text="...")
        self.song_title_label.pack()
        s = ttk.Style()
        s.theme_use("default")
        s.configure("TProgressbar", thickness=8)
        self.level_left = ttk.Progressbar(self, orient=tkinter.HORIZONTAL, length=200, maximum=61, mode="determinate")
        self.level_left.pack()
        self.level_right = ttk.Progressbar(self, orient=tkinter.HORIZONTAL, length=200, maximum=61, mode="determinate")
        self.level_right.pack()
        self.icyclient = None
        self.decoder = None
        self.play_thread = None
        self.after(100, self.load_button_icons)

    def load_button_icons(self):
        with requests.session() as session:
            for index, station in enumerate(self.stations):
                image = Image.open(session.get(station.icon_url, stream=True).raw)
                image.thumbnail((128, 128))
                tkimage = ImageTk.PhotoImage(image)
                button = self.station_buttons[index]
                button.configure(image=tkimage, command=lambda s=station: self.station_select(s), width=160, height=140)
                button._tkimage = tkimage

    def station_select(self, station):
        for button in self.station_buttons:
            button.configure(background=self.quit_button.cget("bg"))
        self.station_buttons[self.stations.index(station)].configure(background="lime green")
        if self.play_thread:
            self.set_song_title("(switching streams...)")
            self.decoder.stop_playback()
            self.decoder = None
            self.play_thread.join()
        self.stream_name_label.configure(text="{} | {}".format(station.station_name, station.stream_name))
        self.icyclient = IceCastClient(station.stream_url, 8192)
        self.decoder = AudioDecoder(self.icyclient, self.set_song_title, self.update_levelmeter)
        self.play_thread = threading.Thread(target=self.decoder.stream_radio, daemon=True)
        self.play_thread.start()

    def set_song_title(self, title):
        self.song_title_label.configure(text=title)

    def update_levelmeter(self, levelmeter):
        if self.decoder:
            self.level_left.configure(value=60+levelmeter.level_left)
            self.level_right.configure(value=60+levelmeter.level_right)


radio = Internetradio()
radio.mainloop()
