import audioop
import time
from typing import Optional, Union, Callable, BinaryIO, Generator
from synthplayer.playback import Output
from synthplayer.streaming import StreamingSample


class DynamicSample(StreamingSample):
    """
    A sound Sample that does NOT load the full source file/stream into memory,
    but loads and produces chunks of it as they are needed.
    Can be used for the realtime mixing output mode to allow
    on demand decoding and streaming of large sound files.
    """
    def __init__(self, wave_file: Optional[Union[str, BinaryIO]] = None, name: str = "", volume: float = 1.0) -> None:
        super().__init__(wave_file, name)
        self.volume = volume

    def chunked_frame_data(self, chunksize: int, repeat: bool = False, stopcondition: Callable[[], bool] = lambda: False) -> Generator[memoryview, None, None]:
        silence = b"\0" * chunksize
        while True:
            audiodata = self.wave_stream.readframes(chunksize // self.samplewidth // self.nchannels)
            if not audiodata:
                if repeat:
                    self.wave_stream.rewind()
                else:
                    break   # non-repeating source stream exhausted
            if len(audiodata) < chunksize:
                audiodata += silence[len(audiodata):]
            # !! change volume dynamically !!
            audiodata = audioop.mul(audiodata, self.samplewidth, self.volume)
            yield memoryview(audiodata)



print("Playback of a Sample where the volume of just that sample itself is modified")
print("during playback, instead of the 'master' volume of the whole stream.")

with Output() as out:
    vol = 1.0
    smp = DynamicSample("samples/SOS 020.wav", "sample", 1.0)
    out.play_sample(smp)
    for i in range(0, 30):
        if i % 2 == 0:
            vol = 1.0
        else:
            vol = 0.2
        smp.volume = vol
        print(f"time={i} vol={vol}")
        time.sleep(0.6)
