import soundcard
import threading
import queue
import numpy
from typing import List, Dict, Any, Optional, Union
from .base import AudioApi
from ..sample import Sample
from .. import params, streaming


class SoundcardUtils:
    def scard_query_apis(self) -> List[Dict[str, Any]]:
        apis = {}  # type: Dict[str, Dict[str, Any]]
        for d in self.scard_query_devices():
            api = d["device.api"]
            if api in apis:
                apis[api]["devices"].append(d)
            else:
                apis[api] = {
                    "name": api,
                    "devices": []
                }
        return list(apis.values())

    def scard_query_devices(self) -> List[Dict[str, Any]]:
        speakers = soundcard.all_speakers()
        result = []
        for speaker in speakers:
            info = speaker._get_info()
            info['id'] = speaker.id
            result.append(info)
        return result

    def scard_query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        speakers = soundcard.all_speakers()
        if type(device) == str:
            for speaker in speakers:
                if speaker.id == device:
                    result = speaker._get_info()
                    result['id'] = speaker.id
                    return result
        else:
            for idx, speaker in enumerate(speakers):
                if idx == device:
                    result = speaker._get_info()
                    result['id'] = speaker.id
                    return result
        raise LookupError("no such device")


class SoundcardThreadMixed(AudioApi, SoundcardUtils):
    """Mixing Api to the soundcard library - using blocking streams with an audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, frames_per_chunk: int = 0) -> None:
        super().__init__(samplerate, samplewidth, nchannels, frames_per_chunk, 0)
        thread_ready = threading.Event()

        def audio_thread() -> None:
            speaker = soundcard.default_speaker()
            mixed_chunks = self.mixer.chunks()
            with speaker.player(self.samplerate, self.nchannels, blocksize=self.chunksize) as stream:
                thread_ready.set()
                silence = Sample.from_raw_frames(b"\0" * self.chunksize, self.samplewidth, self.samplerate, self.nchannels)
                try:
                    while True:
                        raw_data = next(mixed_chunks)
                        if raw_data:
                            data = Sample.from_raw_frames(raw_data, self.samplewidth, self.samplerate, self.nchannels)
                        else:
                            data = silence
                        stream.play(data.get_frames_numpy_float())
                        if len(data) < self.frames_per_chunk:
                            silence_np = numpy.zeros((self.frames_per_chunk-len(data), self.nchannels), dtype=numpy.float32)
                            stream.play(silence_np)
                        if self.playing_callback:
                            self.playing_callback(data)
                except StopIteration:
                    pass

        self.output_thread = threading.Thread(target=audio_thread, name="audio-soundcard", daemon=True)
        self.output_thread.start()
        thread_ready.wait()

    def close(self) -> None:
        super().close()
        self.output_thread.join()

    def query_apis(self) -> List[Dict[str, Any]]:
        return self.scard_query_apis()

    def query_devices(self) -> List[Dict[str, Any]]:
        return self.scard_query_devices()

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return self.scard_query_device_details(device, kind)


class SoundcardThreadSequential(AudioApi, SoundcardUtils):
    """Sequential Api to the soundcard library - using blocking streams with an audio output thread"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, queue_size: int = 100) -> None:
        super().__init__(samplerate, samplewidth, nchannels, queue_size=queue_size)
        thread_ready = threading.Event()
        self.command_queue = queue.Queue(maxsize=queue_size)        # type: queue.Queue[Dict[str, Any]]

        def audio_thread() -> None:
            speaker = soundcard.default_speaker()
            with speaker.player(self.samplerate, self.nchannels, blocksize=self.chunksize) as stream:
                thread_ready.set()
                try:
                    while True:
                        sample = None
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
                                repeat = command["repeat"]
                        except queue.Empty:
                            self.all_played.set()
                            sample = None
                        if sample:
                            stream.play(sample.get_frames_numpy_float())
                            if self.playing_callback:
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

        self.output_thread = threading.Thread(target=audio_thread, name="audio-soundcard-seq", daemon=True)
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

    def query_apis(self) -> List[Dict[str, Any]]:
        return self.scard_query_apis()

    def query_devices(self) -> List[Dict[str, Any]]:
        return self.scard_query_devices()

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return self.scard_query_device_details(device, kind)
