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


__all__ = ["AudioApiNotAvailableError", "PyAudio", "Sounddevice", "Winsound"]

pyaudio = None
sounddevice = None
winsound = None


class AudioApiNotAvailableError(Exception):
    pass


class AudioApi(ABC):
    supports_streaming = True

    def __init__(self, queue_size=100):
        self.queue_size = queue_size
        self.samplerate = None
        self.samplewidth = None
        self.nchannels = None

    def reset_params(self, samplerate, samplewidth, nchannels, queue_size=100):
        self.samplerate = samplerate
        self.samplewidth = samplewidth
        self.nchannels = nchannels
        self.queue_size = queue_size
        self._recreate_outputter()

    def close(self):
        pass

    def query_devices(self):
        raise NotImplementedError

    def query_apis(self):
        raise NotImplementedError

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
        import pyaudio as _pyaudio
        global pyaudio
        pyaudio = _pyaudio
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

    def __init__(self, queue_size=100):
        super().__init__(queue_size)
        import sounddevice as _sounddevice
        global sounddevice
        sounddevice = _sounddevice

    def __del__(self):
        sounddevice.stop()

    def close(self):
        sounddevice.stop()

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_devices_sd(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def play_immediately(self, sample):
        raise NotImplementedError       # @todo

    def play_queue(self, sample):
        raise NotImplementedError

    def wipe_queue(self):
        raise NotImplementedError

    def _recreate_outputter(self):
        raise NotImplementedError


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

