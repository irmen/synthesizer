import miniaudio
from time import sleep


if __name__ == "__main__":
    def pass_through():
        data = yield b""
        while True:
            print(".", end="", flush=True)
            data = yield data

    duplex = miniaudio.DuplexStream(buffersize_msec=0, sample_rate=48000)
    generator = pass_through()
    next(generator)
    print("Starting duplex stream. Press Ctrl + C to exit.")
    duplex.start(generator)

    running = True
    while running:
        try:
            sleep(1)
        except KeyboardInterrupt:
            running = False
    duplex.stop()
