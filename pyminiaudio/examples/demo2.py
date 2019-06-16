import miniaudio


def memory_stream(soundfile: miniaudio.DecodedSoundFile) -> miniaudio.AudioProducerType:
    required_frames = yield b""  # generator initialization
    current = 0
    samples = memoryview(soundfile.samples)     # avoid needless memory copying
    while current < len(samples):
        sample_count = required_frames * soundfile.nchannels
        output = samples[current:current + sample_count]
        current += sample_count
        print(".", end="", flush=True)
        required_frames = yield output


device = miniaudio.PlaybackDevice()
decoded = miniaudio.decode_file("samples/music.mp3")
print("The decoded file has {} frames at {} hz and takes {:.1f} seconds"
      .format(decoded.num_frames, decoded.sample_rate, decoded.duration))
stream = memory_stream(decoded)
next(stream)  # start the generator
device.start(stream)
input("Audio file playing in the background. Enter to stop playback: ")
device.close()
