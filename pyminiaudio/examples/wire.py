import miniaudio
from time import sleep
from miniaudio import ffi, _create_int_array

import ctypes
import array
import numpy as np

if __name__ == "__main__":
    in_device = miniaudio.CaptureDevice(buffersize_msec=0)

    def callback(input_pointer, frame_count):
        print("\n")
        print(frame_count)
        buffer = ffi.new("char *")
        ffi.memmove(buffer, input_pointer, frame_count)
        as_bytes = ffi.string(buffer)
        print(len(as_bytes))
        data = np.frombuffer(as_bytes, dtype="int16")
        print(data)


    in_device.start(callback)
    sleep(1)
    in_device.stop()