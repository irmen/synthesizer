import winsound
import time
import threading
import queue
import io
from typing import Union
from .base import AudioApi
from ..sample import Sample
from .. import params, streaming


class WinsoundSeq(AudioApi):
    """Minimally featured api for the winsound library that comes with Python"""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0, queue_size: int = 100) -> None:
        super().__init__(samplerate, samplewidth, nchannels, queue_size=queue_size)
        self.supports_streaming = False
        self.played_callback = None
        self.sample_queue = queue.Queue(maxsize=queue_size)     # type: queue.Queue[Sample]
        threading.Thread(target=self._play, daemon=True).start()

    def play(self, sample: Sample, repeat: bool = False, delay: float = 0.0) -> int:
        # plays the sample in a background thread so that we can continue while the sound plays.
        # we don't use SND_ASYNC because that complicates cleaning up the temp files a lot.
        if repeat:
            raise ValueError("winsound player doesn't support repeating samples")
        if delay != 0.0:
            raise ValueError("winsound player doesn't support delayed playing")
        self.sample_queue.put(sample)
        return 0

    def _play(self) -> None:
        # this runs in a background thread so a sample playback doesn't block the program
        # (can't use winsound async because we're playing from a memory buffer)
        while True:
            sample = self.sample_queue.get()
            if params.auto_sample_pop_prevention:
                sample = sample.fadein(streaming.antipop_fadein).fadeout(streaming.antipop_fadeout)
            with io.BytesIO() as sample_data:
                sample.write_wav(sample_data)
                winsound.PlaySound(sample_data.getbuffer(), winsound.SND_MEMORY)        # type: ignore
                if self.played_callback:
                    self.played_callback(sample)

    def stop(self, sid_or_name: Union[int, str]) -> None:
        raise NotImplementedError("winsound sequential play mode doesn't support stopping individual samples")

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        raise NotImplementedError("winsound sequential play mode doesn't support setting sample limits")

    def wait_all_played(self) -> None:
        while not self.sample_queue.empty():
            time.sleep(0.2)

    def still_playing(self) -> bool:
        return not self.sample_queue.empty()
