import time
import array
from typing import Union
import miniaudio


sound = miniaudio.decode_file("samples/music.ogg")
offset = 0


def memory_producer(framecount: int, sample_width: int, nchannels: int) -> Union[bytes, array.array, None]:
    global offset
    assert nchannels == 2 and sample_width == 2
    result = sound.samples[offset:offset+framecount*nchannels]
    offset += framecount*nchannels
    print(".", end="", flush=True)
    # print(" ", len(result), "    ", end="\r")
    return result


stream = miniaudio.stream_file("samples/music.ogg")
# stream = miniaudio.stream_memory(open("samples/music.ogg", "rb").read())


def stream_producer(num_frames: int, sample_width: int, nchannels: int) -> Union[bytes, array.array, None]:
    assert nchannels == 2 and sample_width == 2
    try:
        print(".", end="", flush=True)
        return stream.send(num_frames)
    except StopIteration:
        return None


d = miniaudio.PlaybackDevice(buffersize_msec=200)
print("playback device backend:", d.backend)
d.start(memory_producer)
time.sleep(4)
d.stop()
d.close()
print()

