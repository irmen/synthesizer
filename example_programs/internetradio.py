import threading
import re
import subprocess
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
    def __init__(self, url):
        self.url = url
        self.stream_format = "???"
        self.stream_title = "???"
        self.station_genre = "???"
        self.station_name = "???"
        self.block_size = 16384

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
    def __init__(self, icecast_client):
        self.client = icecast_client
        self.stream_title = "???"
        self.audio_threads_must_stop = False

    def _audio_playback(self, ffmpeg_stream):
        # thread 3: audio playback
        levelmeter = LevelMeter()

        def played(sample):
            if self.client.stream_title != self.stream_title:
                self.stream_title = self.client.stream_title
                print("\n\nNew Song:", self.stream_title, "\n")
            levelmeter.update(sample)
            levelmeter.print(60, True)

        with Output(mixing="sequential", frames_per_chunk=44100//4) as output:
            output.register_notify_played(played)
            while not self.audio_threads_must_stop:
                audio = ffmpeg_stream.read(44100 * 2 * 2 // 20)
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
        print("\nStreaming Radio Station: ", self.client.station_name)
        cmd = ["ffmpeg"]
        if format:
            cmd.extend(["-f", format])
        cmd.extend(["-i", "-", "-v", "fatal"])
        # cmd.extend(["-af", "aresample=resampler=soxr"])     # enable this if your ffmpeg has sox hq resample
        cmd.extend(["-ar", "44100", "-ac", "2", "-acodec", "pcm_s16le", "-f", "s16le", "-"])
        ffmpeg = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        ffmpeg.stdin.write(first_chunk)
        audio_playback_thread = threading.Thread(target=self._audio_playback, args=[ffmpeg.stdout], daemon=True)
        audio_playback_thread.start()

        try:
            for chunk in stream:
                ffmpeg.stdin.write(chunk)
        except KeyboardInterrupt:
            pass
        finally:
            ffmpeg.kill()
            self.audio_threads_must_stop = True
            audio_playback_thread.join()
            print("\n")


print("\nStreaming internet radio.  (ffmpeg required for decoding)\n")
print("1 = CJSW University of Calgary Radio")
print("2 = Soma FM Groove Salad")
print("3 = PlayTrance live")
print("4 = <enter your own direct audio stream url (no .pls or.m3u)>")
choice = input("\nWhat do you want to listen to? ").strip()
url = {
    "1": "http://stream.cjsw.com:80/cjsw.ogg",
    "2": "http://ice3.somafm.com/groovesalad-64-aac",
    "3": "http://live.playtrance.com:8000/playtrance-livetech.aac",
    "4": None
}[choice]
if not url:
    url = input("Enter direct stream url:").strip()
client = IceCastClient(url)
decoder = AudioDecoder(client)
decoder.stream_radio()
