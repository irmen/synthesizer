"""
Various audio output options. Here the specific audio library code is located.
Supported audio output libraries:
- pyaudio
- sounddevice (both thread+blocking stream, and nonblocking callback stream variants)
- winsound (limited capabilities)

It can play multiple samples at the same time via real-time mixing, and you can
loop samples as well without noticable overhead (great for continous effects or music)

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

import time
from typing import Generator, Union, Any, Callable, Iterable
from types import TracebackType
from .import params
from .sample import Sample
from .soundapi.base import AudioApi
from .soundapi import best_api


__all__ = ["Output", "best_api"]


# you can override the system's default output device by setting this to a value >= 0,
# or by setting the PY_SYNTHPLAYER_AUDIO_DEVICE environment variable.
default_audio_device = -1


class Output:
    """Plays samples to audio output device or streams them to a file."""
    def __init__(self, samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0,
                 frames_per_chunk: int = 0, mixing: str = "mix", queue_size: int = 100) -> None:
        self.samplerate = self.samplewidth = self.nchannels = 0
        self.frames_per_chunk = 0
        self.audio_api = AudioApi()
        self.supports_streaming = True
        self.mixing = ""
        self.queue_size = -1
        self.reset_params(samplerate, samplewidth, nchannels, frames_per_chunk, mixing, queue_size)

    def __repr__(self) -> str:
        return "<Output at 0x{0:x}, {1:d} channels, {2:d} bits, rate {3:d}>"\
            .format(id(self), self.nchannels, 8*self.samplewidth, self.samplerate)

    @classmethod
    def for_sample(cls, sample: Sample, frames_per_chunk: int = 0, mixing: str = "mix") -> 'Output':
        return cls(sample.samplerate, sample.samplewidth, sample.nchannels, frames_per_chunk, mixing)

    def __enter__(self) -> 'Output':
        return self

    def __exit__(self, exc_type: type, exc_val: Any, exc_tb: TracebackType) -> None:
        self.close()

    def close(self) -> None:
        self.audio_api.close()

    def reset_params(self, samplerate: int, samplewidth: int, nchannels: int,
                     frames_per_chunk: int, mixing: str, queue_size: int) -> None:
        if mixing not in ("mix", "sequential"):
            raise ValueError("invalid mix mode, must be mix or sequential")
        if self.audio_api is not None:
            if samplerate == self.samplerate and samplewidth == self.samplewidth and nchannels == self.nchannels \
                    and frames_per_chunk == self.frames_per_chunk and mixing == self.mixing and queue_size == self.queue_size:
                return   # nothing changed
        if self.audio_api:
            self.audio_api.close()
            self.audio_api.wait_all_played()
        self.samplerate = samplerate or params.norm_samplerate
        self.samplewidth = samplewidth or params.norm_samplewidth
        self.nchannels = nchannels or params.norm_nchannels
        self.frames_per_chunk = frames_per_chunk or params.norm_frames_per_chunk
        self.mixing = mixing
        self.queue_size = queue_size
        self.audio_api = best_api(self.samplerate, self.samplewidth, self.nchannels,
                                  self.frames_per_chunk, self.mixing, self.queue_size)
        self.supports_streaming = self.audio_api.supports_streaming
        time.sleep(0.1)     # allow the mixer thread/stream to warm up (if any)

    def play_sample(self, sample: Sample, repeat: bool = False, delay: float = 0.0) -> int:
        """Play a single sample (asynchronously)."""
        assert sample.samplewidth == self.samplewidth
        assert sample.samplerate == self.samplerate
        assert sample.nchannels == self.nchannels
        return self.audio_api.play(sample, repeat, delay)

    def stop_sample(self, sid_or_name: Union[int, str]) -> None:
        self.audio_api.stop(sid_or_name)

    def wait_all_played(self) -> None:
        self.audio_api.wait_all_played()

    def still_playing(self) -> bool:
        return self.audio_api.still_playing()

    def normalized_samples(self, samples: Iterable[Sample], global_amplification: int = 26000) -> Generator[Sample, None, None]:
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

    def stream_to_file(self, filename: str, samples: Iterable[Sample]) -> None:
        """Saves the samples after each other into one single output wav file."""
        samples = self.normalized_samples(samples, 26000)
        sample = next(samples)
        with Sample.wave_write_begin(filename, sample) as out:
            for sample in samples:
                Sample.wave_write_append(out, sample)
            Sample.wave_write_end(out)

    def silence(self) -> None:
        """Remove all pending samples to be played from the queue"""
        self.audio_api.silence()

    def register_notify_played(self, callback: Callable[[Sample], None]) -> None:
        self.audio_api.register_notify_played(callback)

    def set_sample_play_limit(self, samplename: str, max_simultaneously: int) -> None:
        self.audio_api.set_sample_play_limit(samplename, max_simultaneously)
