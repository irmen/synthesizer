"""
Various audio output options.
- pyaudio
- sounddevice (@todo)
- winsound (@todo)
- file? (@todo)

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""
import threading
import queue
from abc import ABC, abstractmethod, abstractproperty


class AudioApiNotAvailableError(Exception):
    pass


norm_samplerate = 44100
norm_nchannels = 2
norm_samplewidth = 2


class AudioApi(ABC):
    supports_streaming = True

    def __init__(self, queue_size=100):
        self.queue_size = queue_size
        self.samplerate = norm_samplerate
        self.samplewidth = norm_samplewidth
        self.nchannels = norm_nchannels

    def set_params(self, samplerate, samplewidth, nchannels, queue_size=100):
        self.samplerate = samplerate
        self.samplewidth = samplewidth
        self.nchannels = nchannels
        self.queue_size = queue_size

    def query_devices(self):
        raise NotImplementedError

    def query_apis(self):
        raise NotImplementedError

    @abstractmethod
    def get_outputter(self):
        pass


def best():
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


class PyAudio(AudioApi):
    supports_streaming = True

    def __init__(self, queue_size=100):
        super().__init__(queue_size)
        import pyaudio
        self.pyaudio = pyaudio

    def __del__(self):
        pass

    class SoundOutputter(threading.Thread):
        """Sound outputter running in its own thread. Requires PyAudio."""
        def __init__(self, pyaudio, samplerate, samplewidth, nchannels, queue_size=100):
            super().__init__(name="soundoutputter-pyaudio", daemon=True)
            self.audio = pyaudio.PyAudio()
            pyaudio_format = self.audio.get_format_from_width(samplewidth) if samplewidth != 4 else api.pyaudio.paInt32
            self.stream = self.audio.open(format=pyaudio_format, channels=nchannels, rate=samplerate, output=True)
            self.queue = queue.Queue(maxsize=queue_size)

        def run(self):
            while True:
                sample = self.queue.get()
                if not sample:
                    break
                sample.write_frames(self.stream)

        def play_immediately(self, sample):
            sample.write_frames(self.stream)

        def add_to_queue(self, sample):
            self.queue.put(sample)

        _wipe_lock = threading.Lock()

        def wipe_queue(self):
            with self._wipe_lock:
                try:
                    while True:
                        self.queue.get(block=False)
                except queue.Empty:
                    pass

        def queue_size(self):
            return self.queue.qsize()

        def close(self):
            if self.stream:
                self.stream.close()
                self.stream = None
            if self.audio:
                self.audio.terminate()
                self.audio = None

    def get_outputter(self):  # @todo don't expose the outputter object ...
        outputter = PyAudio.SoundOutputter(self.pyaudio, self.samplerate, self.samplewidth, self.nchannels, self.queue_size)
        outputter.start()
        return outputter

    def query_devices(self):
        audio = self.pyaudio.PyAudio()
        num_devices = audio.get_device_count()
        info = [audio.get_device_info_by_index(i) for i in range(num_devices)]
        audio.terminate()
        return info

    def query_apis(self):
        audio = self.pyaudio.PyAudio()
        num_apis = audio.get_host_api_count()
        info = [audio.get_host_api_info_by_index(i) for i in range(num_apis)]
        audio.terminate()
        return info


class Sounddevice(AudioApi):
    supports_streaming = True

    def __init__(self, queue_size=100):
        super().__init__(queue_size)
        import sounddevice
        self.sounddevice = sounddevice

    def __del__(self):
        self.sounddevice.stop()

    def query_devices(self):
        return list(self.sounddevice.query_devices())

    def query_devices_sd(self, device=None, kind=None):
        return self.sounddevice.query_devices(device, kind)

    def query_apis(self):
        return list(self.sounddevice.query_hostapis())


class Winsound(AudioApi):
    supports_streaming = False

    def __init__(self):
        super().__init__()
        import winsound
        self.winsound = winsound

