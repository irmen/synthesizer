import miniaudio
from time import sleep
from miniaudio import ffi, _create_int_array

import ctypes
import array
import numpy as np

if __name__ == "__main__":
    in_device = miniaudio.CaptureDevice(buffersize_msec=0)
    out_device = miniaudio.PlaybackDevice(buffersize_msec=0)

    buffer = b""

    def in_callback(data: bytearray, frame_count: int):
        global buffer
        buffer += data

    def out_callback() -> miniaudio.AudioProducerType:
        required_frames = yield b""  # generator initialization
        global buffer
        while True:
            required_bytes = required_frames * out_device.nchannels * out_device.sample_width
            if required_bytes > len(buffer):
                data = ""
            else:
                data = buffer[0: required_bytes]
                buffer = buffer[required_bytes: ]
            print(".", end="", flush=True)
            required_frames = yield data

    in_device.start(in_callback)
    gen = out_callback()
    gen.send(None)
    out_device.start(gen)

    sleep(5)

    in_device.stop()
    out_device.stop()