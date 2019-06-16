import sys
import miniaudio


def show_info(filename):
    info = miniaudio.get_file_info(filename)
    print("file:", info.name)
    print("format:", info.file_format)
    print("{} channels, {} khz, {:.1f} seconds".format(info.nchannels, info.sample_rate, info.duration))
    print("{} bytes per sample: {}".format(info.sample_width, info.sample_format_name))


def stream_file(filename):
    stream = miniaudio.stream_file(filename)

    def stream_producer(num_frames, sample_width, nchannels):
        assert nchannels == 2 and sample_width == 2
        try:
            return stream.send(num_frames)      # provide num_frames frames from the sample generator
        except StopIteration:
            return None

    device = miniaudio.PlaybackDevice()
    print("playback device backend:", device.backend)
    device.start(stream_producer)
    input("Audio file playing in the background. Enter to stop playback: ")
    device.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("use one argument: filename")
    show_info(sys.argv[1])
    stream_file(sys.argv[1])
