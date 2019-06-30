import os
import warnings
import threading
import queue
import pyaudio
from typing import List, Dict, Any, Union
from .base import AudioApi
from ..sample import Sample
from .. import params, playback, streaming


class PyAudioUtils:
    def initialize(self) -> None:
        self.audio = pyaudio.PyAudio()
        # check the settings of the default audio device
        if "PY_SYNTHPLAYER_AUDIO_DEVICE" in os.environ:
            playback.default_audio_device = int(os.environ["PY_SYNTHPLAYER_AUDIO_DEVICE"])
        if playback.default_audio_device < 0:
            default_input = self.audio.get_default_input_device_info()
            default_output = self.audio.get_default_output_device_info()
            if default_input != default_output and playback.default_audio_device < 0:
                warnings.warn("Trying to determine suitable audio output device. If you don't hear sound, or see "
                              "errors related to audio output, you'll have to specify the correct device manually.",
                              category=ResourceWarning)
                playback.default_audio_device = self.find_default_output_device()
                if playback.default_audio_device < 0:
                    msg = """
Cannot determine suitable audio output device. Portaudio devices: input={input} output={output}
Please specify the desired output device number using the
PY_SYNTHPLAYER_AUDIO_DEVICE environment variable, or by setting the
default_output_device parameter to a value >= 0 in your code).
""".format(input=default_input["index"], output=default_output["index"])
                    raise IOError(msg.strip())

    def find_default_output_device(self) -> int:
        num_apis = self.audio.get_host_api_count()
        apis = [self.audio.get_host_api_info_by_index(i) for i in range(num_apis)]
        num_devices = self.audio.get_device_count()
        devices = [self.audio.get_device_info_by_index(i) for i in range(num_devices)]
        candidates = []    # type: List[int]
        for d in reversed(devices):
            if d["maxOutputChannels"] < 2:
                continue
            api = apis[d["hostApi"]]
            if api["defaultOutputDevice"] < 0:
                continue
            dname = d["name"].lower()
            if dname in ("sysdefault", "default", "front") or "built-in" in dname:
                candidates.append(d["index"])
            elif "generic" in dname or "speakers" in dname or "mme" in dname:     # windows
                candidates.append(d["index"])
        if candidates:
            warnings.warn("chosen output device: "+str(candidates[-1]), category=ResourceWarning)
            return candidates[-1]
        return -1


class PyAudioMixed(AudioApi, PyAudioUtils):
    """Api to the somewhat older pyaudio library (that uses portaudio)"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, frames_per_chunk: int = 0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, frames_per_chunk, 0)
        self.initialize()
        thread_ready = threading.Event()

        def audio_thread() -> None:
            audio = pyaudio.PyAudio()       # type: ignore
            try:
                mixed_chunks = self.mixer.chunks()
                audio_format = audio.get_format_from_width(self.samplewidth) \
                    if self.samplewidth != 4 else pyaudio.paInt32     # type: ignore
                output_device = None if playback.default_audio_device < 0 else playback.default_audio_device
                stream = audio.open(format=audio_format, channels=self.nchannels, rate=self.samplerate, output=True,
                                    output_device_index=output_device, input_device_index=output_device)
                thread_ready.set()
                try:
                    silence = b"\0" * self.chunksize
                    while True:
                        data = next(mixed_chunks) or silence
                        if isinstance(data, memoryview):
                            data = data.tobytes()   # PyAudio stream can't deal with memoryview
                        stream.write(data)
                        if len(data) < self.chunksize:
                            stream.write(silence[len(data):])
                        if self.playing_callback:
                            sample = Sample.from_raw_frames(data, self.samplewidth, self.samplerate, self.nchannels)
                            self.playing_callback(sample)
                except StopIteration:
                    pass
                finally:
                    stream.close()
            finally:
                audio.terminate()

        self.output_thread = threading.Thread(target=audio_thread, name="audio-pyaudio", daemon=True)
        self.output_thread.start()
        thread_ready.wait()

    def close(self) -> None:
        super().close()
        self.output_thread.join()

    def query_api_version(self) -> str:
        return pyaudio.get_portaudio_version_text()     # type: ignore

    def query_devices(self) -> List[Dict[str, Any]]:
        num_devices = self.audio.get_device_count()
        return [self.audio.get_device_info_by_index(i) for i in range(num_devices)]

    def query_apis(self) -> List[Dict[str, Any]]:
        num_apis = self.audio.get_host_api_count()
        return [self.audio.get_host_api_info_by_index(i) for i in range(num_apis)]


class PyAudioSequential(AudioApi, PyAudioUtils):
    """Api to the somewhat older pyaudio library (that uses portaudio)"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, queue_size: int = 100) -> None:
        super().__init__(samplerate, samplewidth, nchannels, queue_size=queue_size)
        self.initialize()
        thread_ready = threading.Event()
        self.command_queue = queue.Queue(maxsize=queue_size)        # type: queue.Queue[Dict[str, Any]]

        def audio_thread() -> None:
            audio = pyaudio.PyAudio()       # type: ignore
            try:
                audio_format = audio.get_format_from_width(self.samplewidth) \
                    if self.samplewidth != 4 else pyaudio.paInt32      # type: ignore
                output_device = None if playback.default_audio_device < 0 else playback.default_audio_device
                stream = audio.open(format=audio_format, channels=self.nchannels, rate=self.samplerate, output=True,
                                    output_device_index=output_device, input_device_index=output_device)
                thread_ready.set()
                try:
                    while True:
                        data = b""
                        repeat = False
                        command = None
                        try:
                            command = self.command_queue.get(timeout=0.2)
                            if command is None or command["action"] == "stop":
                                break
                            elif command["action"] == "play":
                                sample = command["sample"]
                                if params.auto_sample_pop_prevention:
                                    sample = sample.fadein(streaming.antipop_fadein).fadeout(streaming.antipop_fadeout)
                                data = sample.view_frame_data() or b""
                                repeat = command["repeat"]
                        except queue.Empty:
                            self.all_played.set()
                            data = b""
                        if data:
                            if isinstance(data, memoryview):
                                data = data.tobytes()    # pyaudio doesn't support memoryview objects
                            stream.write(data)
                            if self.playing_callback:
                                sample = Sample.from_raw_frames(data, self.samplewidth, self.samplerate, self.nchannels)
                                self.playing_callback(sample)
                        if repeat:
                            # remove all other samples from the queue and reschedule this one
                            commands_to_keep = []
                            while True:
                                try:
                                    c2 = self.command_queue.get(block=False)
                                    if c2["action"] == "play":
                                        continue
                                    commands_to_keep.append(c2)
                                except queue.Empty:
                                    break
                            for cmd in commands_to_keep:
                                self.command_queue.put(cmd)
                            if command:
                                self.command_queue.put(command)
                finally:
                    self.all_played.set()
                    stream.close()
            finally:
                audio.terminate()

        self.output_thread = threading.Thread(target=audio_thread, name="audio-pyaudio", daemon=True)
        self.output_thread.start()
        thread_ready.wait()

    def play(self, sample: Sample, repeat: bool = False, delay: float = 0.0) -> int:
        self.all_played.clear()
        self.command_queue.put({"action": "play", "sample": sample, "repeat": repeat})
        return 0

    def silence(self) -> None:
        try:
            while True:
                self.command_queue.get(block=False)
        except queue.Empty:
            pass
        self.all_played.set()

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        raise NotImplementedError("sequential play mode doesn't support setting sample limits")

    def stop(self, sid_or_name: Union[int, str]) -> None:
        raise NotImplementedError("sequential play mode doesn't support stopping individual samples")

    def close(self) -> None:
        super().close()
        self.command_queue.put({"action": "stop"})
        self.output_thread.join()

    def query_api_version(self) -> str:
        return pyaudio.get_portaudio_version_text()     # type: ignore

    def query_devices(self) -> List[Dict[str, Any]]:
        num_devices = self.audio.get_device_count()
        return [self.audio.get_device_info_by_index(i) for i in range(num_devices)]

    def query_apis(self) -> List[Dict[str, Any]]:
        num_apis = self.audio.get_host_api_count()
        return [self.audio.get_host_api_info_by_index(i) for i in range(num_apis)]
