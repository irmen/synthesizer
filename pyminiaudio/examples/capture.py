import miniaudio
from time import sleep


if __name__ == "__main__":
    buffer = b""

    def record_to_buffer():
        data = yield
        while True:
            data = yield
            print(".", end="", flush=True)
            global buffer
            buffer += data


    capture = miniaudio.CaptureDevice(buffersize_msec=0, sample_rate=48000)
    generator = record_to_buffer()
    print("Recording for 3 seconds")
    next(generator)
    capture.start(generator)
    sleep(3)
    capture.stop()

    print("")
    print("Wring to ./capture.wav")
    samples = miniaudio._create_int_array(capture.format)
    samples.frombytes(buffer)
    sound = miniaudio.DecodedSoundFile('capture', capture.nchannels, capture.sample_rate, capture.sample_width, capture.format, samples)
    miniaudio.wav_write_file('./examples/capture.wav', sound)
    print("Recording done")

