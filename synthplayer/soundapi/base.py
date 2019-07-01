import threading
from typing import Optional, Callable, Union, List, Dict, Any
from ..sample import Sample
from ..streaming import RealTimeMixer
from .. import params


class AudioApi:
    """Base class for the various audio APIs."""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0,
                 frames_per_chunk: int = 0, queue_size: int = 100) -> None:
        self.samplerate = samplerate or params.norm_samplerate
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.nchannels = nchannels or params.norm_nchannels
        self.frames_per_chunk = frames_per_chunk or params.norm_frames_per_chunk
        self.supports_streaming = True
        self.all_played = threading.Event()
        self.playing_callback = None    # type: Optional[Callable[[Sample], None]]
        self.queue_size = queue_size
        self.mixer = RealTimeMixer(self.chunksize, self._all_played_callback)
        # the actual playback of the samples from the queue is done in the various subclasses

    def __str__(self) -> str:
        api_ver = self.query_api_version()
        if api_ver and api_ver != "unknown":
            return self.__class__.__name__ + ", " + self.query_api_version()
        else:
            return self.__class__.__name__

    @property
    def chunksize(self) -> int:
        return self.frames_per_chunk * self.samplewidth * self.nchannels

    def play(self, sample: Sample, repeat: bool = False, delay: float = 0.0) -> int:
        self.all_played.clear()
        chunk_delay = int(self.samplerate * delay / self.frames_per_chunk)
        return self.mixer.add_sample(sample, repeat, chunk_delay) or 0

    def silence(self) -> None:
        self.mixer.clear_sources()
        self.all_played.set()

    def stop(self, sid_or_name: Union[int, str]) -> None:
        self.mixer.clear_source(sid_or_name)

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.mixer.set_limit(samplename, max_simultaneously)

    def close(self) -> None:
        self.silence()
        if self.mixer:
            self.mixer.close()

    def query_api_version(self) -> str:
        return "unknown"

    def query_apis(self) -> List[Dict[str, Any]]:
        return []

    def query_devices(self) -> List[Dict[str, Any]]:
        return []

    def query_device_details(self, device: Optional[Union[int, str]] = None, kind: Optional[str] = None) -> Any:
        return None   # not all apis implement this

    def wait_all_played(self) -> None:
        self.all_played.wait()

    def still_playing(self) -> bool:
        return not self.all_played.is_set()

    def register_notify_played(self, callback: Callable[[Sample], None]) -> None:
        self.playing_callback = callback

    def _all_played_callback(self) -> None:
        self.all_played.set()
