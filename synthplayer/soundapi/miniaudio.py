import queue
import miniaudio
from itertools import chain
from typing import List, Dict, Any, Optional, Union
from .base import AudioApi
from ..sample import Sample
from .. import params, streaming


class MiniaudioUtils:
    def ma_query_api_version(self) -> str:
        return miniaudio.__version__

    def ma_query_apis(self) -> List[Dict[str, Any]]:
        backend = miniaudio.Devices().backend
        return [{
            'name': backend
        }]

    def ma_query_devices(self) -> List[Dict[str, Any]]:
        devices = miniaudio.Devices()
        playback, record = devices.get_playbacks(), devices.get_captures()
        return playback + record

    def ma_query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        devices = miniaudio.Devices()
        if kind == miniaudio.DeviceType.PLAYBACK:
            devs = devices.get_playbacks()
        elif kind == miniaudio.DeviceType.CAPTURE:
            devs = devices.get_playbacks()
        else:
            devs = devices.get_playbacks() + devices.get_captures()
        id_buf = miniaudio.ffi.buffer(device)
        for d in devs:
            if miniaudio.ffi.buffer(d["id"]) == id_buf:
                return d
        raise LookupError("device not found")


class MiniaudioMixed(AudioApi, MiniaudioUtils):
    """Api to the miniaudio library using async callback stream, without a separate audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, frames_per_chunk: int = 0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, frames_per_chunk, 0)
        self.mixed_chunks = self.mixer.chunks()
        output_format = {
            1: miniaudio.SampleFormat.UNSIGNED8,
            2: miniaudio.SampleFormat.SIGNED16,
            3: miniaudio.SampleFormat.SIGNED24,
            4: miniaudio.SampleFormat.SIGNED32
        }[self.samplewidth]
        buffersize_msec = self.nchannels * 1000 * self.frames_per_chunk // self.samplerate
        self.mixed_chunks = self.mixer.chunks()
        self.device = miniaudio.PlaybackDevice(output_format, self.nchannels, self.samplerate, buffersize_msec)
        stream = self.generator()
        next(stream)  # start generator
        self.device.start(stream)

    def generator(self) -> miniaudio.PlaybackCallbackGeneratorType:
        playable = next(self.mixed_chunks)
        required_frames = yield b""  # generator initialization
        while True:
            required_bytes = required_frames * self.nchannels * self.samplewidth
            if len(playable) < required_bytes:
                sample_chunk = next(self.mixed_chunks)
                if sample_chunk:
                    playable += sample_chunk      # type: ignore
                    if self.playing_callback:
                        smp = Sample.from_raw_frames(sample_chunk, self.samplewidth, self.samplerate, self.nchannels)
                        self.playing_callback(smp)
            sample_data = playable[:required_bytes]
            playable = playable[required_bytes:]
            required_frames = yield sample_data

    def close(self) -> None:
        super().close()
        self.device.close()
        self.all_played.set()

    def query_api_version(self) -> str:
        return self.ma_query_api_version()

    def query_apis(self) -> List[Dict[str, Any]]:
        return self.ma_query_apis()

    def query_devices(self) -> List[Dict[str, Any]]:
        return self.ma_query_devices()

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return self.ma_query_device_details(device, kind)


class MiniaudioSequential(AudioApi, MiniaudioUtils):
    """Sequential Api to the miniaudio library - simulating blocking stream"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, queue_size: int = 100) -> None:
        super().__init__(samplerate, samplewidth, nchannels, queue_size=queue_size)
        self.command_queue = queue.Queue(maxsize=queue_size)        # type: queue.Queue[Dict[str, Any]]
        output_format = {
            1: miniaudio.SampleFormat.UNSIGNED8,
            2: miniaudio.SampleFormat.SIGNED16,
            3: miniaudio.SampleFormat.SIGNED24,
            4: miniaudio.SampleFormat.SIGNED32
        }[self.samplewidth]
        self.device = miniaudio.PlaybackDevice(output_format, self.nchannels, self.samplerate)
        stream = self.generator()
        next(stream)  # start generator
        self.device.start(stream)

    def generator(self) -> miniaudio.PlaybackCallbackGeneratorType:
        required_frames = yield b""  # generator initialization
        playable = b""
        while True:
            required_bytes = required_frames * self.nchannels * self.samplewidth
            if len(playable) < required_bytes:
                sample = self.process_command()
                if sample:
                    playable += sample.view_frame_data()        # type: ignore
                    if self.playing_callback:
                        self.playing_callback(sample)
            sample_data = playable[:required_bytes]
            playable = playable[required_bytes:]
            required_frames = yield sample_data

    def process_command(self) -> Optional[Sample]:
        sample = None
        repeat = False
        try:
            command = self.command_queue.get(block=False)
            if command is None or command["action"] == "stop":
                return None
            elif command["action"] == "play":
                sample = command["sample"]
                if params.auto_sample_pop_prevention:
                    sample = sample.fadein(streaming.antipop_fadein).fadeout(streaming.antipop_fadeout)
                repeat = command["repeat"]
        except queue.Empty:
            self.all_played.set()
            return None
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
        return sample

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
        self.device.close()
        self.all_played.set()

    def query_api_version(self) -> str:
        return self.ma_query_api_version()

    def query_apis(self) -> List[Dict[str, Any]]:
        return self.ma_query_apis()

    def query_devices(self) -> List[Dict[str, Any]]:
        return self.ma_query_devices()

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return self.ma_query_device_details(device, kind)
