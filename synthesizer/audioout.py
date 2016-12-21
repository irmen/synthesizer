"""
Various audio output options. Here the specific audio library code is located.
Supported audio output libraries:
- pyaudio
- sounddevice (@todo)
- winsound (@todo)
- file? (@todo)

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import threading
import queue
from abc import ABC, abstractmethod


__all__ = ["AudioApiNotAvailableError", "PyAudio", "Sounddevice", "Winsound", "best_api"]


class AudioApiNotAvailableError(Exception):
    pass


def best_api():
    try:
        return Sounddevice()
    except ImportError:
        try:
            return PyAudio()
        except ImportError:
            try:
                return Winsound()
            except ImportError:
                raise AudioApiNotAvailableError("no suitable audio output api available") from None


class AudioApi(ABC):
    supports_streaming = True

    def __init__(self):
        self.queue_size = None
        self.samplerate = None
        self.samplewidth = None
        self.nchannels = None

    def reset_params(self, samplerate, samplewidth, nchannels, queue_size=100):
        self.samplerate = samplerate
        self.samplewidth = samplewidth
        self.nchannels = nchannels
        self.queue_size = queue_size
        self._recreate_outputter()

    def __str__(self):
        api_ver = self.query_api_version()
        if api_ver and api_ver != "unknown":
            return self.__class__.__name__ + ", " + self.query_api_version()
        else:
            return self.__class__.__name__

    def close(self):
        pass

    def query_devices(self):
        return []

    def query_apis(self):
        return []

    def query_api_version(self):
        return "unknown"

    @abstractmethod
    def _recreate_outputter(self):
        pass

    @abstractmethod
    def play_queue(self, sample):
        pass

    @abstractmethod
    def play_immediately(self, sample):
        pass

    @abstractmethod
    def wipe_queue(self):
        pass


class PyAudio(AudioApi):
    supports_streaming = True

    def __init__(self):
        super().__init__()
        global pyaudio
        import pyaudio
        self.samp_queue = None
        self.stream = None

    def __del__(self):
        if self.samp_queue:
            self.play_queue(None)

    def close(self):
        if self.samp_queue:
            self.play_queue(None)

    def _recreate_outputter(self):
        if self.samp_queue:
            self.play_queue(None)
        self.samp_queue = queue.Queue(maxsize=self.queue_size)
        stream_ready = threading.Event()

        def audio_thread():
            audio = pyaudio.PyAudio()
            try:
                audio_format = audio.get_format_from_width(self.samplewidth) if self.samplewidth != 4 else pyaudio.paInt32
                self.stream = audio.open(format=audio_format, channels=self.nchannels, rate=self.samplerate, output=True)
                stream_ready.set()
                q = self.samp_queue
                try:
                    while True:
                        sample = q.get()
                        if not sample:
                            break
                        sample.write_frames(self.stream)
                finally:
                    self.stream.close()
            finally:
                audio.terminate()

        outputter = threading.Thread(target=audio_thread, name="audio-pyaudio", daemon=True)
        outputter.start()
        stream_ready.wait()

    def query_devices(self):
        audio = pyaudio.PyAudio()
        try:
            num_devices = audio.get_device_count()
            info = [audio.get_device_info_by_index(i) for i in range(num_devices)]
            return info
        finally:
            audio.terminate()

    def query_apis(self):
        audio = pyaudio.PyAudio()
        try:
            num_apis = audio.get_host_api_count()
            info = [audio.get_host_api_info_by_index(i) for i in range(num_apis)]
            return info
        finally:
            audio.terminate()

    def query_api_version(self):
        return pyaudio.get_portaudio_version_text()

    def play_immediately(self, sample):
        sample.write_frames(self.stream)

    def play_queue(self, sample):
        self.samp_queue.put(sample)

    def wipe_queue(self):
        try:
            while True:
                self.samp_queue.get(block=False)
        except queue.Empty:
            pass


class Sounddevice(AudioApi):
    supports_streaming = True

    def __init__(self):
        super().__init__()
        global sounddevice
        import sounddevice
        self.samp_queue = None
        self.stream = None

    def __del__(self):
        if self.samp_queue:
            self.play_queue(None)
        sounddevice.stop()

    def close(self):
        if self.samp_queue:
            self.play_queue(None)
        sounddevice.stop()

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_devices_sd(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def query_api_version(self):
        return sounddevice.get_portaudio_version()[1]

    def play_immediately(self, sample):
        sample.write_frames(self.stream)

    def play_queue(self, sample):
        self.samp_queue.put(sample)

    def wipe_queue(self):
        try:
            while True:
                self.samp_queue.get(block=False)
        except queue.Empty:
            pass

    def _recreate_outputter(self):
        if self.samp_queue:
            self.play_queue(None)
        self.samp_queue = queue.Queue(maxsize=self.queue_size)
        stream_ready = threading.Event()

        def audio_thread():   # @todo use callback stream instead?
            try:
                if self.samplewidth == 1:
                    dtype = "int8"
                elif self.samplewidth == 2:
                    dtype = "int16"
                elif self.samplewidth == 3:
                    dtype = "int24"
                elif self.samplewidth == 4:
                    dtype = "int32"
                else:
                    raise ValueError("invalid sample width")
                self.stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype)
                self.stream.start()
                stream_ready.set()
                q = self.samp_queue
                try:
                    while True:
                        sample = q.get()
                        if not sample:
                            break
                        sample.write_frames(self.stream)
                finally:
                    self.stream.stop()
                    self.stream.close()
            finally:
                pass

        outputter = threading.Thread(target=audio_thread, name="audio-sounddevice", daemon=True)
        outputter.start()
        stream_ready.wait()


class Winsound(AudioApi):
    supports_streaming = False

    def __init__(self):
        super().__init__()
        import winsound as _winsound
        global winsound
        winsound = _winsound

    """
                # try to fallback to winsound (only works on windows)
            sample_file = "__temp_sample.wav"
            sample.write_wav(sample_file)
            winsound.PlaySound(sample_file, winsound.SND_FILENAME)
            os.remove(sample_file)
"""

