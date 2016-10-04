"""
Some audiostream related tools

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import subprocess
import shutil
import json
import wave
import os
import io
from .sample import Sample


__all__ = ["AudiofileToWavStream", "EndlessWavStream", "StreamMixer"]


class AudiofileToWavStream:
    """
    Streams WAV PCM audio data from the given sound source file.
    If the file is not already a .wav, and/or you want to resample it,
    ffmpeg/ffprobe are used to convert it in the background.
    For HQ resampling, ffmpeg has to be built with libsoxr support.
    """
    ffmpeg_executable = "ffmpeg"
    ffprobe_executable = "ffprobe"

    def __init__(self, filename, outputfilename=None, samplerate=None, channels=None, sampleformat=None, hqresample=True):
        self.filename = filename
        if not os.path.isfile(filename):
            raise FileNotFoundError(filename)
        self.outputfilename = outputfilename
        self.stream = None
        self.resample_options = []
        self.downmix_options = []
        self.sampleformat_options = []
        self.conversion_required = True
        if self.ffprobe_executable:
            try:
                # probe the existing file format, to see if we can avoid needless conversion
                probe_samplerate, probe_channels, probe_sampleformat = self.probe_format()
                self.conversion_required = probe_samplerate!=samplerate or probe_channels!=channels or probe_sampleformat!=sampleformat
            except (subprocess.CalledProcessError, IOError, OSError) as x:
                pass
        if self.conversion_required:
            if samplerate:
                samplerate = int(samplerate)
                assert 2000 <= samplerate <= 200000
                if hqresample:
                    self.resample_options = ["-af", "aresample=resampler=soxr", "-ar", str(samplerate)]
                else:
                    self.resample_options = ["-ar", str(samplerate)]
            if channels:
                channels = int(channels)
                assert 1 <= channels <= 9
                self.downmix_options = ["-ac", str(channels)]
            if sampleformat:
                codec = {
                        "8": "pcm_u8",
                        "16": "pcm_s16le",
                        "24": "pcm_s24le",
                        "32": "pcm_s32le",
                        "float": "pcm_f32le",
                        "alaw": "pcm_alaw",
                        "ulaw": "pcm_mulaw"
                    }[sampleformat]
                self.sampleformat_options = ["-acodec", codec]

    def probe_format(self):
        command = [self.ffprobe_executable, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-i", self.filename]
        probe = subprocess.check_output(command)
        probe = json.loads(probe.decode())
        if len(probe["streams"]) > 1:
            raise IOError("audio file contains more than one stream, not supported")
        stream = probe["streams"][0]
        samplerate = int(stream["sample_rate"])
        nchannels = int(stream["channels"])
        sampleformat = {
            "u8": "8",
            "s16": "16",
            "s32": "32",
            "fltp": "float",
            }.get(stream["sample_fmt"], "<unknown>")
        return samplerate, nchannels, sampleformat

    def convert(self):
        if not self.conversion_required:
            if self.outputfilename:
                with open(self.filename, "rb") as source:
                    with open(self.outputfilename, "wb") as dest:
                        shutil.copyfileobj(source, dest)
                return
            self.stream = open(self.filename, "rb")
        else:
            command = [self.ffmpeg_executable, "-v", "error", "-hide_banner", "-loglevel", "error", "-i", self.filename, "-f", "wav"]
            command.extend(self.resample_options)
            command.extend(self.downmix_options)
            command.extend(self.sampleformat_options)
            if self.outputfilename:
                command.extend(["-y", self.outputfilename])
                subprocess.check_call(command)
                return
            command.append("-")
            converter = subprocess.Popen(command, stdout=subprocess.PIPE)
            self.stream = converter.stdout
        return self.stream

    def __enter__(self):
        if self.outputfilename:
            raise RuntimeError("convert to file cannot be used as a contextmanager")
        return self.convert()

    def __exit__(self, *args):
        self.stream.close()


class EndlessWavStream:
    """
    Stream of wav audio data that can be endless (silence until stopped)
    Takes ownership of the source stream that is wrapped.
    """
    def __init__(self, source, silence_frames):
        self.source = source
        self.silence_frames = silence_frames
        self.source_exhausted = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.source.close()

    def readframes(self, nframes):
        if not self.source_exhausted:
            frames = self.source.readframes(nframes)
            if frames:
                return frames
            self.source_exhausted = True
        return self.silence_frames

    def close(self):
        self.source.close()


class StreamMixer:
    """
    Mixes one or more wav audio streams into one output.
    Takes ownership of the source streams that are being mixed, and will close them for you as needed.
    """
    buffer_size = 4096   # number of frames in a buffer
    def __init__(self, streams, endless=False):
        self.wave_streams = {}   # wavestream -> source stream
        for stream in streams:
            self.add_stream(stream, False)
        if len(self.wave_streams) < 1:
            raise ValueError("must have at least one stream")
        # assume all wave streams are the same parameters
        ws = list(self.wave_streams)[0]
        self.samplewidth = ws.getsampwidth()
        self.samplerate = ws.getframerate()
        self.nchannels = ws.getnchannels()
        self.temporary_streams = set()
        self.timestamp = 0.0
        if endless:
            self.endless()

    def add_stream(self, stream, close_when_done=True):
        wave_stream = wave.open(stream, 'r')
        self.wave_streams[wave_stream] = stream
        if close_when_done:
            self.temporary_streams.add(wave_stream)
        return stream

    def remove_stream(self, stream):
        self.temporary_streams.remove(stream)
        stream.close()
        original_stream = self.wave_streams.pop(stream)
        original_stream.close()

    def add_sample(self, sample):
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        stream = io.BytesIO()
        sample.write_wav(stream)
        stream.seek(0, io.SEEK_SET)
        self.add_stream(stream, True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def endless(self):
        """Activate endless streams. This mode cannot be undone."""
        silence_frames = b"\0"*Sample.get_frame_idx(self.buffer_size/self.samplerate, self.samplewidth, self.samplerate, self.nchannels)
        wrapped_streams = {}
        for ws, original in self.wave_streams.items():
            wrapped_streams[EndlessWavStream(ws, silence_frames)] = original
        self.wave_streams = wrapped_streams

    def close(self):
        for stream, original_stream in self.wave_streams.items():
            stream.close()
            original_stream.close()
        del self.wave_streams
        del self.temporary_streams

    def __iter__(self):
        while True:
            stream_frames = {ws: ws.readframes(self.buffer_size) for ws in self.wave_streams}
            mixed_sample = None
            for ws, frames in stream_frames.items():
                if len(frames)==0 and ws in self.temporary_streams:
                    self.remove_stream(ws)
                else:
                    sample = Sample.from_raw_frames(frames, self.samplewidth, self.samplerate, self.nchannels)
                    if mixed_sample:
                        mixed_sample.mix(sample)
                    else:
                        mixed_sample = sample
            if not mixed_sample:
                break
            self.timestamp += mixed_sample.duration
            yield self.timestamp, mixed_sample
