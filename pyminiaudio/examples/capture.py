import miniaudio
from time import sleep
from miniaudio import ffi, _create_int_array

import ctypes
import array
import numpy as np

if __name__ == "__main__":
    def record_to_raw():
        data = yield
        with open("./examples/capture.raw", "wb") as f:
            while True:
                print(".", end="", flush=True)
                data = yield
                f.write(data)


    capture = miniaudio.CaptureDevice(buffersize_msec=0, sample_rate=48000)
    generator = record_to_raw()
    print("Recording for 3 seconds")
    print("Wring to ./capture.raw")
    next(generator)
    capture.start(generator)
    sleep(3)
    capture.stop()
    print("")
    print("Recording done")

