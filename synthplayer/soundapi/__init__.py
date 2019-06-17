from typing import List, Type
from .base import AudioApi

available_sequential_play_apis = []      # type: List[Type]
available_mix_play_apis = []             # type: List[Type]


try:
    from .miniaudio import MiniaudioSequential, MiniaudioMixed
    available_sequential_play_apis.append(MiniaudioSequential)
    available_mix_play_apis.append(MiniaudioMixed)
except ImportError:
    pass


try:
    from .soundcard import SoundcardThreadSequential, SoundcardThreadMixed
    available_sequential_play_apis.append(SoundcardThreadSequential)
    available_mix_play_apis.append(SoundcardThreadMixed)
except ImportError:
    pass
except OSError:
    pass        # on older windows versions (7) the soundcard library may crash with this error


try:
    from .sounddevice import SounddeviceThreadSequential, SounddeviceThreadMixed, SounddeviceMixed
    available_sequential_play_apis.append(SounddeviceThreadSequential)
    available_mix_play_apis.append(SounddeviceMixed)
    available_mix_play_apis.append(SounddeviceThreadMixed)
except ImportError:
    pass

try:
    from .pyaudio import PyAudioSequential, PyAudioMixed
    available_sequential_play_apis.append(PyAudioSequential)
    available_mix_play_apis.append(PyAudioMixed)
except ImportError:
    pass

try:
    from .winsound import WinsoundSeq
    available_sequential_play_apis.append(WinsoundSeq)
except ImportError:
    pass


def best_api(samplerate: int = 0, samplewidth: int = 0, nchannels: int = 0,
             frames_per_chunk: int = 0, mixing: str = "mix", queue_size: int = 100) -> AudioApi:
    if mixing not in ("mix", "sequential"):
        raise ValueError("invalid mix mode, must be mix or sequential")
    if mixing == "mix":
        candidates = available_mix_play_apis
    else:
        candidates = available_sequential_play_apis
    if candidates:
        candidate = candidates[0]
        if mixing == "mix":
            return candidate(samplerate, samplewidth, nchannels, frames_per_chunk)
        else:
            return candidate(samplerate, samplewidth, nchannels, queue_size=queue_size)
    raise Exception("no supported audio output api available")
