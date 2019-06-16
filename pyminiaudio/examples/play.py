import sys
import miniaudio


def show_info(filename):
    info = miniaudio.get_file_info(filename)
    print("file:", info.name)
    print("format:", info.file_format)
    print("{} channels, {} khz, {:.1f} seconds".format(info.nchannels, info.sample_rate, info.duration))
    print("{} bytes per sample: {}".format(info.sample_width, info.sample_format_name))


def stream_file(filename):
    def progress_stream_wrapper(stream) -> miniaudio.AudioProducerType:
        framecount = yield(b"")
        try:
            while True:
                framecount = yield stream.send(framecount)
                print(".", end="", flush=True)
        except StopIteration:
            return

    stream = progress_stream_wrapper(miniaudio.stream_file(filename))
    next(stream)   # start the generator
    device = miniaudio.PlaybackDevice()
    print("playback device backend:", device.backend)
    device.start(stream)
    input("Audio file playing in the background. Enter to stop playback: ")
    device.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("use one argument: filename")
    show_info(sys.argv[1])
    stream_file(sys.argv[1])
