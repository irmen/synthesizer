"""
This example uses ffmpeg as an external tool to decode an audio file in a format
that miniaudio itself can't decode (m4a/aac in this case)
"""
import os
import subprocess
import miniaudio

channels = 2
sample_rate = 44100
sample_width = 2  # 16 bit pcm


def samples_path(filename):
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), 'samples', filename)


def stream_pcm(source):
    required_frames = yield b""  # generator initialization
    while True:
        required_bytes = required_frames * channels * sample_width
        sample_data = source.read(required_bytes)
        if not sample_data:
            break
        print(".", end="", flush=True)
        required_frames = yield sample_data


filename = samples_path("music.m4a")   # AAC encoded file
device = miniaudio.PlaybackDevice(ma_output_format=miniaudio.ma_format_s16,
                                  nchannels=channels, sample_rate=sample_rate)
ffmpeg = subprocess.Popen(["ffmpeg", "-v", "fatal", "-hide_banner", "-nostdin",
                           "-i", filename, "-f", "s16le", "-acodec", "pcm_s16le",
                           "-ac", str(channels), "-ar", str(sample_rate), "-"],
                          stdin=None, stdout=subprocess.PIPE)
stream = stream_pcm(ffmpeg.stdout)
next(stream)  # start the generator
device.start(stream)
input("Audio file playing in the background. Enter to stop playback: ")
device.close()
ffmpeg.terminate()
