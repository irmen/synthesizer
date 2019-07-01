import os
import warnings
import sounddevice
import threading
import queue
from typing import List, Dict, Any, Optional, Union
from .base import AudioApi
from ..sample import Sample
from .. import playback, params, streaming


class SounddeviceUtils:
    def samplewidth2dtype(self, swidth: int) -> str:
        if swidth == 1:
            return "int8"
        elif swidth == 2:
            return "int16"
        elif swidth == 3:
            return "int24"
        elif swidth == 4:
            return "int32"
        else:
            raise ValueError("invalid sample width")

    def initialize(self) -> None:
        # check the settings of the default audio device
        if "PY_SYNTHPLAYER_AUDIO_DEVICE" in os.environ:
            playback.default_audio_device = int(os.environ["PY_SYNTHPLAYER_AUDIO_DEVICE"])
        if playback.default_audio_device >= 0:
            sounddevice.default.device["output"] = playback.default_audio_device
            sounddevice.default.device["input"] = playback.default_audio_device
        default_input = sounddevice.default.device["input"]
        default_output = sounddevice.default.device["output"]
        if default_input != default_output and playback.default_audio_device < 0:
            warnings.warn("Trying to determine suitable audio output device. If you don't hear sound, or see "
                          "errors related to audio output, you'll have to specify the correct device manually.",
                          category=ResourceWarning)
            default_audio_device = self.find_default_output_device()
            if default_audio_device >= 0:
                sounddevice.default.device["output"] = default_audio_device
            else:
                msg = """
Cannot determine suitable audio output device. Portaudio devices: input={input} output={output}
Please specify the desired output device number using the
PY_SYNTHPLAYER_AUDIO_DEVICE environment variable, or by setting the
default_output_device parameter to a value >= 0 in your code).
""".format(input=default_input, output=default_output)
                raise IOError(msg.strip())

    def find_default_output_device(self) -> int:
        devices = sounddevice.query_devices()       # type: ignore
        apis = sounddevice.query_hostapis()         # type: ignore
        candidates = []
        for did, d in reversed(list(enumerate(devices))):
            if d["max_output_channels"] < 2:
                continue
            api = apis[d["hostapi"]]
            if api["default_output_device"] < 0:
                continue
            dname = d["name"].lower()
            if dname in ("sysdefault", "default", "front") or "built-in" in dname:
                candidates.append(did)
            elif "generic" in dname or "speakers" in dname or "mme" in dname:
                candidates.append(did)
        if candidates:
            warnings.warn("chosen output device: "+str(candidates[-1]), category=ResourceWarning)
            return candidates[-1]
        return -1


class SounddeviceMixed(AudioApi, SounddeviceUtils):
    """Api to the sounddevice library (that uses portaudio) -
    using callback stream, without a separate audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, frames_per_chunk: int = 0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, frames_per_chunk, 0)
        self.initialize()
        dtype = self.samplewidth2dtype(self.samplewidth)
        self._empty_sound_data = b"\0" * self.chunksize
        self.mixed_chunks = self.mixer.chunks()
        self.stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype,        # type: ignore
                                                  blocksize=self.frames_per_chunk, callback=self.streamcallback)
        self.stream.start()

    def query_api_version(self) -> str:
        return sounddevice.get_portaudio_version()[1]       # type: ignore

    def query_apis(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_hostapis())           # type: ignore

    def query_devices(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_devices())            # type: ignore

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return sounddevice.query_devices(device, kind)      # type: ignore

    def close(self) -> None:
        self.stream.stop()
        self.stream.close()
        self.stream = None
        super().close()

    def streamcallback(self, outdata: bytearray, frames: int, time: int, status: int) -> None:
        try:
            data = next(self.mixed_chunks)
        except StopIteration:
            raise sounddevice.CallbackStop    # type: ignore  # play remaining buffer and then stop the stream
        if not data:
            # no frames available, use silence
            assert len(outdata) == len(self._empty_sound_data)
            outdata[:] = self._empty_sound_data
        elif len(data) < len(outdata):
            # print("underflow", len(data), len(outdata))
            # underflow, pad with silence
            outdata[:len(data)] = data
            outdata[len(data):] = b"\0" * (len(outdata) - len(data))
        else:
            outdata[:] = data
        if self.playing_callback:
            sample = Sample.from_raw_frames(outdata[:], self.samplewidth, self.samplerate, self.nchannels)
            self.playing_callback(sample)


class SounddeviceThreadMixed(AudioApi, SounddeviceUtils):
    """Api to the sounddevice library (that uses portaudio) -
    using blocking streams with an audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, frames_per_chunk: int = 0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, frames_per_chunk, 0)
        self.initialize()
        dtype = self.samplewidth2dtype(self.samplewidth)
        thread_ready = threading.Event()
        self.stream = None      # type: Optional[sounddevice.RawOutputStream]

        def audio_thread() -> None:
            mixed_chunks = self.mixer.chunks()
            self.stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype)
            self.stream.start()
            thread_ready.set()
            try:
                silence = b"\0" * self.chunksize
                while True:
                    data = next(mixed_chunks) or silence
                    self.stream.write(data)
                    if len(data) < self.chunksize:
                        self.stream.write(silence[len(data):])
                    if self.playing_callback:
                        sample = Sample.from_raw_frames(data, self.samplewidth, self.samplerate, self.nchannels)  # type: ignore
                        self.playing_callback(sample)
            except StopIteration:
                pass
            finally:
                self.stream.stop()
                self.stream.close()
                self.stream = None

        self.output_thread = threading.Thread(target=audio_thread, name="audio-sounddevice", daemon=True)
        self.output_thread.start()
        thread_ready.wait()

    def close(self) -> None:
        if self.stream:
            self.stream.stop()
            self.stream.close()
        super().close()
        self.output_thread.join()

    def query_api_version(self) -> str:
        return sounddevice.get_portaudio_version()[1]   # type: ignore

    def query_apis(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_hostapis())       # type: ignore

    def query_devices(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_devices())        # type: ignore

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return sounddevice.query_devices(device, kind)  # type: ignore


class SounddeviceThreadSequential(AudioApi, SounddeviceUtils):
    """Api to the more featureful sounddevice library (that uses portaudio) -
    using blocking streams with an audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, queue_size: int = 100) -> None:
        super().__init__(samplerate, samplewidth, nchannels, queue_size=queue_size)
        self.initialize()
        dtype = self.samplewidth2dtype(self.samplewidth)
        thread_ready = threading.Event()
        self.command_queue = queue.Queue(maxsize=queue_size)        # type: queue.Queue[Dict[str, Any]]

        def audio_thread() -> None:
            stream = sounddevice.RawOutputStream(self.samplerate, channels=self.nchannels, dtype=dtype)     # type: ignore
            stream.start()
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
                stream.stop()
                stream.close()

        self.output_thread = threading.Thread(target=audio_thread, name="audio-sounddevice-seq", daemon=True)
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

    def stop(self, sid_or_name: Union[int, str]) -> None:
        raise NotImplementedError("sequential play mode doesn't support stopping individual samples")

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        raise NotImplementedError("sequential play mode doesn't support setting sample limits")

    def close(self) -> None:
        super().close()
        self.command_queue.put({"action": "stop"})
        self.output_thread.join()

    def query_api_version(self) -> str:
        return sounddevice.get_portaudio_version()[1]       # type: ignore

    def query_apis(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_hostapis())           # type: ignore

    def query_devices(self) -> List[Dict[str, Any]]:
        return list(sounddevice.query_devices())            # type: ignore

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return sounddevice.query_devices(device, kind)      # type: ignore
