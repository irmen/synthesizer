import miniaudio
from synthplayer.playback import Output
from synthplayer.sample import Sample

miniaudio.ma_device_init()
raise SystemExit


c = miniaudio.ma_decode_file("samples/music.ogg", sample_rate=22050)
print(c, c.sample_rate, len(c.samples))
c = miniaudio.ma_decode(open("samples/music.ogg", "rb").read(), sample_rate=22050)
print(c, c.sample_rate, len(c.samples))
c = miniaudio.vorbis_read_file("samples/music.ogg")
print(c, c.sample_rate, len(c.samples))

info = miniaudio.get_file_info("samples/music.mp3")
print(vars(info))
if info.sample_width == 1:
    fmt = miniaudio.ma_format_u8
elif info.sample_width == 2:
    fmt = miniaudio.ma_format_s16
elif info.sample_width == 4:
    fmt = miniaudio.ma_format_s32
else:
    raise IOError("invalid sample width")
stream = miniaudio.ma_stream_memory(open("samples/music.mp3", "rb").read(), ma_output_format=fmt, nchannels=info.nchannels, sample_rate=info.sample_rate)

with Output(info.sample_rate, info.sample_width, info.nchannels, mixing="sequential") as out:
    for chunk in stream:
        print(len(chunk), ".", end="", flush=True)
        s = Sample.from_array(chunk, info.sample_rate, info.nchannels)
        out.play_sample(s)
    out.wait_all_played()

raise SystemExit


# f = miniaudio.get_file_info("samples/music.wav")
# print(vars(f))
# f = miniaudio.wav_get_info(open("samples/music.wav", "rb").read())
# print(vars(f))
# f = miniaudio.get_file_info("samples/music.ogg")
# print(vars(f))
# f = miniaudio.vorbis_get_info(open("samples/music.ogg", "rb").read())
# print(vars(f))
# f = miniaudio.get_file_info("samples/music.mp3")
# print(vars(f))
# f = miniaudio.mp3_get_info(open("samples/music.mp3", "rb").read())
# print(vars(f))
# f = miniaudio.get_file_info("samples/music.flac")
# print(vars(f))
# f = miniaudio.flac_get_info(open("samples/music.flac", "rb").read())
# print(vars(f))
# raise SystemExit

info = miniaudio.get_file_info("samples/music.flac")
print(vars(info))
stream = miniaudio.flac_stream_file("samples/music.flac")

with Output(info.sample_rate, info.sample_width, info.nchannels, mixing="sequential") as out:
    for chunk in stream:
        print(len(chunk), ".", end="", flush=True)
        s = Sample.from_array(chunk, info.sample_rate, info.nchannels)
        out.play_sample(s)
    out.wait_all_played()

raise SystemExit


s1 = miniaudio.vorbis_read_file("samples/music.ogg")
s2 = miniaudio.flac_read_file_s16("samples/music.flac")
s3 = miniaudio.mp3_read_file_s16("samples/music.mp3")
s4 = miniaudio.wav_read_file_s16("samples/music.wav")


def print_details(s: miniaudio.DecodedSoundFile) -> None:
    print(s.name)
    print("  ", s.nchannels, s.sample_rate, s.sample_width, len(s.samples), s.samples.typecode)


print_details(s1)
print_details(s2)
print_details(s3)
print_details(s4)


sample1 = Sample.from_array(s1.samples, s1.sample_rate, s1.nchannels, s1.name)
sample2 = Sample.from_array(s2.samples, s2.sample_rate, s2.nchannels, s2.name)
sample3 = Sample.from_array(s3.samples, s3.sample_rate, s3.nchannels, s3.name)
sample4 = Sample.from_array(s4.samples, s4.sample_rate, s4.nchannels, s4.name)
silence = Sample.from_array([0]*s1.sample_rate*s1.nchannels, s1.sample_rate, s1.nchannels, "silence")


with Output.for_sample(sample1, mixing="sequential") as out:
    out.play_sample(sample1)
    out.play_sample(silence)
    out.play_sample(sample2)
    out.play_sample(silence)
    out.play_sample(sample3)
    out.play_sample(silence)
    out.play_sample(sample4)
    out.wait_all_played()
