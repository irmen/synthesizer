"""
Various audio output options. Here the specific audio library code is located.
Supported audio output libraries:
- pyaudio
- sounddevice (both thread+blocking stream, and nonblocking callback stream variants)
- winsound

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import threading
import queue
import os
import tempfile
import time
from .sample import Sample

__all__ = ["AudioApiNotAvailableError", "PyAudio", "Sounddevice", "SounddeviceThread", "Winsound", "best_api", "Output"]


# stubs for optional audio library modules:
sounddevice = None
pyaudio = None
winsound = None


class AudioApiNotAvailableError(Exception):
    pass


def best_api():
    try:
        return Sounddevice()
    except ImportError:
        try:
            return SounddeviceThread()
        except ImportError:
            try:
                return PyAudio()
            except ImportError:
                try:
                    return Winsound()
                except ImportError:
                    raise AudioApiNotAvailableError("no suitable audio output api available") from None


class AudioApi:
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

    def _recreate_outputter(self):
        pass

    def play(self, sample):
        raise NotImplementedError

    def wipe_queue(self):
        pass

    def wait_all_played(self):
        raise NotImplementedError

    def register_notify_played(self, callback):
        raise NotImplementedError


class PyAudio(AudioApi):
    """Api to the somewhat older pyaudio library (that uses portaudio)"""
    supports_streaming = True

    def __init__(self):
        super().__init__()
        self.samp_queue = None
        self.stream = None
        self.all_played = threading.Event()
        self.played_callback = None
        global pyaudio
        import pyaudio

    def __del__(self):
        if self.samp_queue:
            self.play(None)

    def close(self):
        if self.samp_queue:
            self.play(None)

    def _recreate_outputter(self):
        if self.samp_queue:
            self.play(None)
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
                        if self.played_callback:
                            self.played_callback(sample)
                        if q.empty():
                            time.sleep(sample.duration)
                            self.all_played.set()
                finally:
                    self.stream.close()
                    self.all_played.set()
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

    def play(self, sample):
        self.all_played.clear()
        self.samp_queue.put(sample)

    def wipe_queue(self):
        try:
            while True:
                self.samp_queue.get(block=False)
            self.all_played.set()
        except queue.Empty:
            pass

    def wait_all_played(self):
        self.all_played.wait()

    def register_notify_played(self, callback):
        self.played_callback = callback


class SounddeviceThread(AudioApi):
    """Api to the more featureful sounddevice library (that uses portaudio) -
    using blocking streams with an audio output thread"""
    supports_streaming = True

    def __init__(self):
        super().__init__()
        self.samp_queue = None
        self.stream = None
        self.output_thread = None
        self.all_played = threading.Event()
        self.played_callback = None
        global sounddevice
        import sounddevice

    def close(self):
        if self.samp_queue:
            self.play(None)
        if self.output_thread:
            self.output_thread.join()
        sounddevice.stop()

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_devices_sd(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def query_api_version(self):
        return sounddevice.get_portaudio_version()[1]

    def play(self, sample):
        self.all_played.clear()
        self.samp_queue.put(sample)

    def wipe_queue(self):
        try:
            while True:
                self.samp_queue.get(block=False)
            self.all_played.set()
        except queue.Empty:
            pass

    def _recreate_outputter(self):
        if self.samp_queue:
            self.play(None)
        self.samp_queue = queue.Queue(maxsize=self.queue_size)
        stream_ready = threading.Event()

        def audio_thread():
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
                        if self.played_callback:
                            self.played_callback(sample)
                        if q.empty():
                            time.sleep(sample.duration)
                            self.all_played.set()
                finally:
                    # self.stream.stop()  causes pop
                    self.stream.close()
                    self.all_played.set()
            finally:
                pass

        self.output_thread = threading.Thread(target=audio_thread, name="audio-sounddevice", daemon=True)
        self.output_thread.start()
        stream_ready.wait()

    def wait_all_played(self):
        self.all_played.wait()

    def register_notify_played(self, callback):
        self.played_callback = callback


class Sounddevice(AudioApi):
    """Api to the more featureful sounddevice library (that uses portaudio) -
    using callback stream, without a separate audio output thread"""
    supports_streaming = True

    class BufferQueueReader:
        def __init__(self, bufferqueue):
            self.queue_items = self.iter_queue(bufferqueue)
            self.current_item = None
            self.i = 0
            self.queue_empty_event = threading.Event()
        def iter_queue(self, bufferqueue):
            while True:
                try:
                    yield bufferqueue.get_nowait()
                except queue.Empty:
                    self.queue_empty_event.set()
                    yield None
        def next_chunk(self, size):
            if not self.current_item:
                data = next(self.queue_items)
                if not data:
                    return None
                self.current_item = memoryview(data)
                self.i = 0
            rest_current = len(self.current_item) - self.i
            if size <= rest_current:
                # current item still contains enough data
                result = self.current_item[self.i:self.i+size]
                self.i += size
                return result
            # current item is too small, get more data from the queue
            # we assume the size of the chunks in the queue is >= required block size
            data = next(self.queue_items)
            if data:
                result = self.current_item[self.i:].tobytes()
                self.i = size - len(result)
                result += data[0:self.i]
                self.current_item = memoryview(data)
                assert len(result)==size, "queue blocks need to be >= buffersize"
                return result
            else:
                # no new data available, just return the last remaining data from current block
                result = self.current_item[self.i:]
                self.current_item = None
                return result or None

    def __init__(self):
        super().__init__()
        self.buffer_queue = None
        self.stream = None
        self.buffer_queue_reader = None
        self.all_played = threading.Event()
        self.played_callback = None
        global sounddevice
        import sounddevice

    def __del__(self):
        if sounddevice:
            sounddevice.stop()

    def close(self):
        if self.stream:
            # self.stream.stop()   causes pop
            self.stream.close()
            self.stream = None
        self.buffer_queue = None
        sounddevice.stop()

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_devices_sd(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def query_api_version(self):
        return sounddevice.get_portaudio_version()[1]

    def play(self, sample):
        class SampleBufferGrabber:
            def __init__(self):
                self.buffer = None
            def write(self, buffer):
                assert self.buffer is None
                self.buffer = buffer
        self.all_played.clear()
        grabber = SampleBufferGrabber()
        sample.write_frames(grabber)
        self.buffer_queue.put(grabber.buffer)

    def wipe_queue(self):
        try:
            while True:
                self.buffer_queue.get(block=False)
            self.all_played.set()
        except queue.Empty:
            pass

    def _recreate_outputter(self):
        if self.stream:
            # self.stream.stop()   causes pop
            self.stream.close()
        self.buffer_queue = queue.Queue(maxsize=self.queue_size)
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
        frames_per_chunk = self.samplerate // 20
        self.buffer_queue_reader = Sounddevice.BufferQueueReader(self.buffer_queue)
        self.stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype,
            blocksize=frames_per_chunk, callback=self.streamcallback)
        self.stream.start()

    def streamcallback(self, outdata, frames, time, status):
        data = self.buffer_queue_reader.next_chunk(len(outdata))
        if not data:
            # no frames available, use silence
            data = b"\0" * len(outdata)
            self.all_played.set()
            # raise sounddevice.CallbackAbort   this will abort the stream
        if len(data) < len(outdata):
            # underflow, pad with silence
            outdata[:len(data)] = data
            outdata[len(data):] = b"\0"*(len(outdata)-len(data))
            # raise sounddevice.CallbackStop    this will play the remaining samples and then stop the stream
        else:
            outdata[:] = data
        if self.played_callback:
            from .sample import Sample
            sample = Sample.from_raw_frames(outdata, self.samplewidth, self.samplerate, self.nchannels)
            self.played_callback(sample)

    def wait_all_played(self):
        self.all_played.wait()

    def register_notify_played(self, callback):
        self.played_callback = callback


class Winsound(AudioApi):
    """Minimally featured api for the winsound library that comes with Python"""
    supports_streaming = False

    def __init__(self):
        super().__init__()
        import winsound as _winsound
        global winsound
        winsound = _winsound
        self.threads = []
        self.played_callback = None

    def play(self, sample):
        # plays the sample in a background thread so that we can continue while the sound plays.
        # we don't use SND_ASYNC because that complicates cleaning up the temp files a lot.
        self.wait_all_played()
        t = threading.Thread(target=self._play, args=(sample,), daemon=True)
        self.threads.append(t)
        t.start()
        time.sleep(0.0005)

    def _play(self, sample):
        with tempfile.NamedTemporaryFile(delete=False) as sample_file:
            sample.write_wav(sample_file)
            sample_file.flush()
            winsound.PlaySound(sample_file.name, winsound.SND_FILENAME)
            if self.played_callback:
                self.played_callback(sample)
        os.unlink(sample_file.name)

    def wait_all_played(self):
        while self.threads:
            t = self.threads.pop()
            t.join()

    def register_notify_played(self, callback):
        self.played_callback = callback


class Output:
    """Plays samples to audio output device or streams them to a file."""
    def __init__(self, samplerate=Sample.norm_samplerate, samplewidth=Sample.norm_samplewidth, nchannels=Sample.norm_nchannels, queuesize=10):
        self.samplerate = samplerate
        self.samplewidth = samplewidth
        self.nchannels = nchannels
        self.audio_api = best_api()
        self.audio_api.reset_params(samplerate, samplewidth, nchannels, queuesize)
        self.supports_streaming = self.audio_api.supports_streaming

    def __repr__(self):
        return "<Output at 0x{0:x}, {1:d} channels, {2:d} bits, rate {3:d}>"\
            .format(id(self), self.nchannels, 8*self.samplewidth, self.samplerate)

    @classmethod
    def for_sample(cls, sample):
        return cls(sample.samplerate, sample.samplewidth, sample.nchannels)

    def __enter__(self):
        return self

    def __exit__(self, xtype, value, traceback):
        self.close()

    def close(self):
        self.audio_api.close()

    def play_sample(self, sample):
        """Play a single sample (asynchronously)."""
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        self.audio_api.play(sample)

    def play_samples(self, samples):
        """Plays all the given samples immediately after each other, with no pauses.
        Normalizes all the sample's volume to a common value."""
        if self.audio_api.supports_streaming:
            for s in self.normalized_samples(samples, 26000):
                self.audio_api.play(s)
        else:
            raise RuntimeError("You need an audio api that supports streaming, to play many samples in sequence.")

    def wait_all_played(self):
        self.audio_api.wait_all_played()

    def normalized_samples(self, samples, global_amplification=26000):
        """Generator that produces samples normalized to 16 bit using a single amplification value for all."""
        for sample in samples:
            if sample.samplewidth != 2:
                # We can't use automatic global max amplitude because we're streaming
                # the samples individually. So use a fixed amplification value instead
                # that will be used to amplify all samples in stream by the same amount.
                sample = sample.amplify(global_amplification).make_16bit(False)
            if sample.nchannels == 1:
                sample.stereo()
            assert sample.nchannels == 2
            assert sample.samplerate == 44100
            assert sample.samplewidth == 2
            yield sample

    def stream_to_file(self, filename, samples):
        """Saves the samples after each other into one single output wav file."""
        samples = self.normalized_samples(samples, 26000)
        sample = next(samples)
        with Sample.wave_write_begin(filename, sample) as out:
            for sample in samples:
                Sample.wave_write_append(out, sample)
            Sample.wave_write_end(out)

    def wipe_queue(self):
        """Remove all pending samples to be played from the queue"""
        self.audio_api.wipe_queue()

    def register_notify_played(self, callback):
        self.audio_api.register_notify_played(callback)
