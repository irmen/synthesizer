"""
Various audio output options. Here the specific audio library code is located.
Supported audio output libraries:
- pyaudio
- sounddevice (both thread+blocking stream, and nonblocking callback stream variants)
- winsound (limited capabilities)

It can play multiple samples at the same time via real-time mixing, and you can
loop samples as well without noticable overhead (great for continous effects or music)

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import audioop      # type: ignore
import queue
import threading
import tempfile
import time
import os
from collections import defaultdict
from typing import Generator, Union, Dict, Tuple, Any, List, Callable
from .import params
from .sample import Sample


__all__ = ["Output", "best_api"]


# stubs for optional audio library modules:
sounddevice = None
pyaudio = None
winsound = None


def best_api(samplerate=0, samplewidth=0, nchannels=0, chunkduration=0):
    try:
        return Sounddevice(samplerate, samplewidth, nchannels, chunkduration)
    except ImportError:
        try:
            return SounddeviceThread(samplerate, samplewidth, nchannels, chunkduration)
        except ImportError:
            try:
                return PyAudio(samplerate, samplewidth, nchannels, chunkduration)
            except ImportError:
                try:
                    return Winsound(samplerate, samplewidth, nchannels, chunkduration)
                except ImportError:
                    raise Exception("no supported audio output api available") from None


class SampleMixer:
    """
    Real-time audio sample mixer. Samples are played as soon as they're added into the mix.
    Simply adds a number of samples, clipping if values become too large.
    Produces (via a generator method) chunks of audio stream data to be fed to the sound output stream.
    """
    def __init__(self, chunksize: int, all_played_callback: Callable=None) -> None:
        self.active_samples = {}   # type: Dict[int, Tuple[str, int, Generator[memoryview, None, None]]]
        self.sample_counts = defaultdict(int)  # type: Dict[str, int]
        self.chunksize = chunksize
        self.mixed_chunks = self.chunks()
        self.add_lock = threading.Lock()
        self._sid = 0
        self.sample_limits = defaultdict(int)  # type: Dict[str, int]
        self.all_played_callback = all_played_callback or (lambda: None)
        self.chunks_mixed = 0

    def add_sample(self, sample: Sample, repeat: bool=False, sid: int=None, chunks_delay: int=0) -> Union[int, None]:
        if not self.allow_sample(sample, repeat):
            return None
        with self.add_lock:
            sample_chunks = sample.chunked_frame_data(chunksize=self.chunksize, repeat=repeat)
            self._sid += 1
            sid = sid or self._sid
            self.active_samples[sid] = (sample.name, self.chunks_mixed+chunks_delay, sample_chunks)
            self.sample_counts[sample.name] += 1
            return sid

    def allow_sample(self, sample: Sample, repeat: bool=False) -> bool:
        if repeat and self.sample_counts[sample.name] >= 1:  # don't allow more than one repeating sample
            return False
        max_samples = self.sample_limits[sample.name] or 4
        if self.sample_counts[sample.name] >= max_samples:  # same sample max 4 times simultaneously
            return False
        if sum(self.sample_counts.values()) >= 8:  # mixing max 8 samples simultaneously
            return False
        return True

    def _determine_samples_to_mix(self) -> List[Tuple[int, Tuple[str, Generator[memoryview, None, None]]]]:
        active = []
        with self.add_lock:
            for sid, (name, mix_after_chunk, sample) in self.active_samples.items():
                if mix_after_chunk <= self.chunks_mixed:
                    active.append((sid, (name, sample)))
        return active

    def clear_sources(self) -> None:
        # clears all sources
        with self.add_lock:
            self.active_samples.clear()
            self.sample_counts.clear()

    def clear_source(self, sid_or_name: Union[int, str]) -> None:
        # clear a single sample source by its sid or all sources with the sample name
        if isinstance(sid_or_name, int):
            self.remove_sample(sid_or_name)
        else:
            active_samples = self._determine_samples_to_mix()
            for sid, (name, _) in active_samples:
                if name == sid_or_name:
                    self.remove_sample(sid)

    def chunks(self) -> Generator[memoryview, None, None]:
        silence = b"\0" * self.chunksize
        while True:
            chunks_to_mix = []
            active_samples = self._determine_samples_to_mix()
            for i, (name, s) in active_samples:
                try:
                    chunk = next(s)
                    if len(chunk) > self.chunksize:
                        raise ValueError("chunk from sample is larger than chunksize from mixer")
                    if len(chunk) < self.chunksize:
                        # pad the chunk with some silence
                        chunk = memoryview(chunk.tobytes() + silence[:self.chunksize - len(chunk)])
                    chunks_to_mix.append(chunk)
                except StopIteration:
                    self.remove_sample(i)
            chunks_to_mix = chunks_to_mix or [silence]      # type: ignore
            assert all(len(c) == self.chunksize for c in chunks_to_mix)
            mixed = chunks_to_mix[0]
            if len(chunks_to_mix) > 1:
                for to_mix in chunks_to_mix[1:]:
                    mixed = audioop.add(mixed, to_mix, params.norm_nchannels)
                mixed = memoryview(mixed)
            self.chunks_mixed += 1
            yield mixed

    def remove_sample(self, sid: int) -> None:
        with self.add_lock:
            name = self.active_samples[sid][0]
            del self.active_samples[sid]
            self.sample_counts[name] -= 1
            if not self.active_samples:
                self.all_played_callback()

    def set_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.sample_limits[samplename] = max_simultaneously


class AudioApi:
    """Base class for the various audio APIs."""
    def __init__(self, samplerate: int=0, samplewidth: int=0, nchannels: int=0, chunkduration: float=0.0) -> None:
        self.samplerate = samplerate or params.norm_samplerate
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.nchannels = nchannels or params.norm_nchannels
        self.chunkduration = chunkduration or params.norm_chunk_duration
        self.samp_queue = queue.Queue(maxsize=100)      # type: queue.Queue[Dict[str, Any]]
        self.supports_streaming = True
        self.all_played = threading.Event()
        self.played_callback = None
        self._job_id_seq = 1
        # the actual playback of the samples from the queue is done in the various subclasses

    def __str__(self) -> str:
        api_ver = self.query_api_version()
        if api_ver and api_ver != "unknown":
            return self.__class__.__name__ + ", " + self.query_api_version()
        else:
            return self.__class__.__name__

    def wipe_queue(self):
        try:
            while True:
                self.samp_queue.get(block=False)
        except queue.Empty:
            self.all_played.set()

    def chunksize(self) -> int:
        return int(self.samplerate * self.samplewidth * self.nchannels * self.chunkduration)

    def play(self, sample: Sample, repeat: bool=False, chunks_delay: int=0) -> int:
        job = {"action": "play", "sample": sample, "repeat": repeat, "delay": chunks_delay}
        job_id = self._job_id_seq
        self._job_id_seq += 1
        job["id"] = job_id
        self.all_played.clear()
        self.samp_queue.put(job)
        return job_id

    def silence(self) -> None:
        self.samp_queue.put({"action": "silence"})

    def close(self) -> None:
        self.samp_queue.put({"action": "close"})

    def stop(self, sid: int) -> None:
        self.samp_queue.put({"action": "stop", "sid": sid})

    def query_api_version(self) -> str:
        return "unknown"

    def query_apis(self) -> List[Dict]:
        return []

    def query_devices(self) -> List[Dict]:
        return []

    def query_device_details(self, device=None, kind=None) -> Any:
        raise NotImplementedError("not available for this audio API")

    def wait_all_played(self):
        self.all_played.wait()

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        pass

    def register_notify_played(self, callback):
        self.played_callback = callback

    def _all_played_callback(self):
        self.all_played.set()


class PyAudio(AudioApi):
    """Api to the somewhat older pyaudio library (that uses portaudio)"""
    def __init__(self, samplerate: int=0, samplewidth: int=0, nchannels: int=0, chunkduration: float=0.0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, chunkduration)
        global pyaudio
        import pyaudio      # type: ignore
        thread_ready = threading.Event()

        def audio_thread():
            audio = pyaudio.PyAudio()
            self.mixer = SampleMixer(chunksize=self.chunksize(), all_played_callback=self._all_played_callback)
            try:
                audio_format = audio.get_format_from_width(self.samplewidth) if self.samplewidth != 4 else pyaudio.paInt32
                stream = audio.open(format=audio_format, channels=self.nchannels, rate=self.samplerate, output=True)
                thread_ready.set()
                try:
                    while True:
                        try:
                            job = self.samp_queue.get_nowait()
                            if job["action"] == "close":
                                break
                            elif job["action"] == "silence":
                                self.mixer.clear_sources()
                                continue
                            elif job["action"] == "stop":
                                self.mixer.clear_source(job["sid"])
                                continue
                            elif job["action"] == "play":
                                self.mixer.add_sample(job["sample"], job["repeat"], job["id"], job["delay"])
                            else:
                                raise ValueError("invalid action: " + job["action"])
                        except queue.Empty:
                            pass
                        data = next(self.mixer.mixed_chunks)
                        if isinstance(data, memoryview):
                            data = data.tobytes()   # PyAudio stream can't deal with memoryview
                        stream.write(data)
                        if self.played_callback:
                            sample = Sample.from_raw_frames(data, self.samplewidth, self.samplerate, self.nchannels)
                            self.played_callback(sample)
                finally:
                    stream.close()
            finally:
                audio.terminate()

        outputter = threading.Thread(target=audio_thread, name="audio-pyaudio", daemon=True)
        outputter.start()
        thread_ready.wait()

    def query_api_version(self):
        return pyaudio.get_portaudio_version_text()

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

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.mixer.set_limit(samplename, max_simultaneously)


class SounddeviceThread(AudioApi):
    """Api to the more featureful sounddevice library (that uses portaudio) -
    using blocking streams with an audio output thread"""
    def __init__(self, samplerate: int=0, samplewidth: int=0, nchannels: int=0, chunkduration: float=0.0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, chunkduration)
        global sounddevice
        import sounddevice      # type: ignore
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
        thread_ready = threading.Event()

        def audio_thread():
            self.mixer = SampleMixer(chunksize=self.chunksize(), all_played_callback=self._all_played_callback)
            try:
                stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype)
                stream.start()
                thread_ready.set()
                try:
                    while True:
                        try:
                            job = self.samp_queue.get_nowait()
                            if job["action"] == "close":
                                break
                            elif job["action"] == "silence":
                                self.mixer.clear_sources()
                                continue
                            elif job["action"] == "stop":
                                self.mixer.clear_source(job["sid"])
                                continue
                            elif job["action"] == "play":
                                self.mixer.add_sample(job["sample"], job["repeat"], job["id"], job["delay"])
                            else:
                                raise ValueError("invalid action: " + job["action"])
                        except queue.Empty:
                            pass
                        data = next(self.mixer.mixed_chunks)
                        stream.write(data)
                        if self.played_callback:
                            sample = Sample.from_raw_frames(data, self.samplewidth, self.samplerate, self.nchannels)
                            self.played_callback(sample)
                finally:
                    stream.close()
            finally:
                sounddevice.stop()

        self.output_thread = threading.Thread(target=audio_thread, name="audio-sounddevice", daemon=True)
        self.output_thread.start()
        thread_ready.wait()

    def query_api_version(self):
        return sounddevice.get_portaudio_version()[1]

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_device_details(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.mixer.set_limit(samplename, max_simultaneously)


class Sounddevice(AudioApi):
    """Api to the more featureful sounddevice library (that uses portaudio) -
    using callback stream, without a separate audio output thread"""
    def __init__(self, samplerate: int=0, samplewidth: int=0, nchannels: int=0, chunkduration: float=0.0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, chunkduration)
        del self.samp_queue     # this one doesn't use a thread with a command queue
        global sounddevice
        import sounddevice
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
        self._empty_sound_data = b"\0" * self.chunksize()
        self.mixer = SampleMixer(chunksize=self.chunksize(), all_played_callback=self._all_played_callback)
        self.stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype,        # type: ignore
                                                  blocksize=self.chunksize() // self.nchannels // self.samplewidth,
                                                  callback=self.streamcallback)
        self.stream.start()

    def query_api_version(self):
        return sounddevice.get_portaudio_version()[1]

    def query_apis(self):
        return list(sounddevice.query_hostapis())

    def query_devices(self):
        return list(sounddevice.query_devices())

    def query_device_details(self, device=None, kind=None):
        return sounddevice.query_devices(device, kind)

    def play(self, sample: Sample, repeat: bool=False, chunks_delay: int=0) -> int:
        self.all_played.clear()
        return self.mixer.add_sample(sample, repeat, chunks_delay=chunks_delay) or 0

    def silence(self):
        self.mixer.clear_sources()

    def stop(self, sid: int) -> None:
        self.mixer.clear_source(sid)

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.mixer.set_limit(samplename, max_simultaneously)

    def close(self):
        self.silence()
        self.stream.stop()
        self.all_played.set()

    def streamcallback(self, outdata, frames, time, status):
        data = next(self.mixer.mixed_chunks)
        if not data:
            # no frames available, use silence
            # raise sounddevice.CallbackAbort   this will abort the stream
            assert len(outdata) == len(self._empty_sound_data)
            outdata[:] = self._empty_sound_data
        elif len(data) < len(outdata):
            # print("underflow", len(data), len(outdata))
            # underflow, pad with silence
            outdata[:len(data)] = data
            outdata[len(data):] = b"\0" * (len(outdata) - len(data))
            # raise sounddevice.CallbackStop    this will play the remaining samples and then stop the stream
        else:
            outdata[:] = data
        if self.played_callback:
            sample = Sample.from_raw_frames(outdata[:], self.samplewidth, self.samplerate, self.nchannels)
            self.played_callback(sample)


class Winsound(AudioApi):
    """Minimally featured api for the winsound library that comes with Python"""
    def __init__(self, samplerate: int=0, samplewidth: int=0, nchannels: int=0, chunkduration: float=0.0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, chunkduration)
        self.supports_streaming = False
        import winsound as _winsound        # type: ignore
        global winsound
        winsound = _winsound
        self.threads = []       # type: List[threading.Thread]
        self.played_callback = None

    def play(self, sample: Sample, repeat: bool=False, chunks_delay: int=0) -> int:
        # plays the sample in a background thread so that we can continue while the sound plays.
        # we don't use SND_ASYNC because that complicates cleaning up the temp files a lot.
        if repeat:
            raise ValueError("winsound player doesn't support repeating samples")
        if chunks_delay != 0:
            raise ValueError("winsound player doesn't support delayed playing")
        self.wait_all_played()
        t = threading.Thread(target=self._play, args=(sample,), daemon=True)
        self.threads.append(t)
        t.start()
        time.sleep(0.0005)
        return 0

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


class Output:
    """Plays samples to audio output device or streams them to a file."""
    def __init__(self, samplerate=0, samplewidth=0, nchannels=0, chunkduration=0):
        self.samplerate = self.samplewidth = self.nchannels = 0
        self.chunkduration = 0.0
        self.audio_api = None
        self.reset_params(samplerate, samplewidth, nchannels, chunkduration)
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

    def reset_params(self, samplerate: int, samplewidth: int, nchannels: int, chunkduration: float) -> None:
        if self.audio_api is not None:
            if samplerate == self.samplerate and samplewidth == self.samplewidth and nchannels == self.nchannels:
                if chunkduration == self.chunkduration:
                    return   # nothing changed
                raise NotImplementedError("chunkduration change")
        if self.audio_api:
            self.audio_api.close()
            self.audio_api.wait_all_played()
        self.samplerate = samplerate or params.norm_samplerate
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.nchannels = nchannels or params.norm_nchannels
        self.chunkduration = chunkduration or params.norm_chunk_duration
        self.audio_api = best_api(self.samplerate, self.samplewidth, self.nchannels, self.chunkduration)

    def play_sample(self, sample, delay=0.0):
        """Play a single sample (asynchronously)."""
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        self.audio_api.play(sample, chunks_delay=delay/self.chunkduration)

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
