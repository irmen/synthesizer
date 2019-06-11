import sys
import os
import array
from typing import Generator
from _miniaudio import ffi, lib


class DecodedSoundFile:
    def __init__(self, name: str, nchannels: int, sample_rate: int, sample_width: int, samples: array.array) -> None:
        self.name = name
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.samples = samples


class SoundFileInfo:
    def __init__(self, name: str, nchannels: int, sample_rate: int, sample_width: int,
                 duration: float, num_frames: int, max_frame_size: int) -> None:
        self.name = name
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.duration = duration
        self.num_frames = num_frames
        self.max_frame_size = max_frame_size


class DecodeError(IOError):
    pass


def get_file_info(filename: str) -> SoundFileInfo:
    """Fetch some information about the audio file."""
    ext = os.path.splitext(filename)[1].lower()
    print(ext)
    if ext in (".ogg", ".vorbis"):
        return vorbis_get_file_info(filename)
    elif ext == ".mp3":
        return mp3_get_file_info(filename)
    elif ext == ".flac":
        return flac_get_file_info(filename)
    elif ext == ".wav":
        return wav_get_file_info(filename)
    raise ValueError("unsupported file format")


def read_file(filename: str) -> DecodedSoundFile:
    """Reads and decodes the whole audio file. Resulting sample format is 16 bits signed integer."""
    ext = os.path.splitext(filename)[1].lower()
    print(ext)
    if ext in (".ogg", ".vorbis"):
        return vorbis_read_file(filename)
    elif ext == ".mp3":
        return mp3_read_file_s16(filename)
    elif ext == ".flac":
        return flac_read_file_s16(filename)
    elif ext == ".wav":
        return wav_read_file_s16(filename)
    raise ValueError("unsupported file format")


def vorbis_get_file_info(filename: str) -> SoundFileInfo:
    filenamebytes = _get_filename_bytes(filename)
    error = ffi.new("int *")
    vorbis = lib.stb_vorbis_open_filename(filenamebytes, error, ffi.NULL)
    if not vorbis:
        raise DecodeError("could not open/decode file")
    try:
        info = lib.stb_vorbis_get_info(vorbis)
        duration = lib.stb_vorbis_stream_length_in_seconds(vorbis)
        num_frames = lib.stb_vorbis_stream_length_in_samples(vorbis)
        return SoundFileInfo(filename, info.channels, info.sample_rate, 2, duration, num_frames, info.max_frame_size)
    finally:
        lib.stb_vorbis_close(vorbis)


def vorbis_get_info(data: bytes) -> SoundFileInfo:
    error = ffi.new("int *")
    vorbis = lib.stb_vorbis_open_memory(data, len(data), error, ffi.NULL)
    if not vorbis:
        raise DecodeError("could not open/decode data")
    try:
        info = lib.stb_vorbis_get_info(vorbis)
        duration = lib.stb_vorbis_stream_length_in_seconds(vorbis)
        num_frames = lib.stb_vorbis_stream_length_in_samples(vorbis)
        return SoundFileInfo("<memory>", info.channels, info.sample_rate, 2, duration, num_frames, info.max_frame_size)
    finally:
        lib.stb_vorbis_close(vorbis)


def vorbis_read_file(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("int *")
    sample_rate = ffi.new("int *")
    output = ffi.new("short **")
    num_frames = lib.stb_vorbis_decode_filename(filenamebytes, channels, sample_rate, output)
    if num_frames <= 0:
        raise DecodeError("cannot load/decode file")
    try:
        buffer = ffi.buffer(output[0], num_frames * channels[0] * 2)
        samples = _create_int_array(2)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, samples)
    finally:
        lib.free(output[0])


def vorbis_read(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("int *")
    sample_rate = ffi.new("int *")
    output = ffi.new("short **")
    num_samples = lib.stb_vorbis_decode_memory(data, len(data), channels, sample_rate, output)
    if num_samples <= 0:
        raise DecodeError("cannot load/decode data")
    try:
        buffer = ffi.buffer(output[0], num_samples * channels[0] * 2)
        samples = _create_int_array(2)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, samples)
    finally:
        lib.free(output[0])


def vorbis_stream_file(filename: str) -> Generator[array.array, None, None]:
    """Streams the ogg vorbis audio file as interleaved 16 bit signed integer sample arrays segments."""
    filenamebytes = _get_filename_bytes(filename)
    error = ffi.new("int *")
    vorbis = lib.stb_vorbis_open_filename(filenamebytes, error, ffi.NULL)
    if not vorbis:
        raise DecodeError("could not open/decode file")
    try:
        info = lib.stb_vorbis_get_info(vorbis)
        decode_buffer1 = ffi.new("short[]", 4096 * info.channels)
        decodebuf_ptr1 = ffi.cast("short *", decode_buffer1)
        decode_buffer2 = ffi.new("short[]", 4096 * info.channels)
        decodebuf_ptr2 = ffi.cast("short *", decode_buffer2)
        # note: we decode several frames to reduce the overhead of very small sample sizes a little
        while True:
            num_samples1 = lib.stb_vorbis_get_frame_short_interleaved(vorbis, info.channels, decodebuf_ptr1,
                                                                      4096 * info.channels)
            num_samples2 = lib.stb_vorbis_get_frame_short_interleaved(vorbis, info.channels, decodebuf_ptr2,
                                                                      4096 * info.channels)
            if num_samples1 + num_samples2 <= 0:
                break
            buffer = ffi.buffer(decode_buffer1, num_samples1 * 2 * info.channels)
            samples = _create_int_array(2)
            samples.frombytes(buffer)
            if num_samples2 > 0:
                buffer = ffi.buffer(decode_buffer2, num_samples2 * 2 * info.channels)
                samples.frombytes(buffer)
            yield samples
    finally:
        lib.stb_vorbis_close(vorbis)


def flac_get_file_info(filename: str) -> SoundFileInfo:
    filenamebytes = _get_filename_bytes(filename)
    flac = lib.drflac_open_file(filenamebytes)
    if not flac:
        raise DecodeError("could not open/decode file")
    try:
        duration = flac.totalPCMFrameCount / flac.sampleRate
        return SoundFileInfo(filename, flac.channels, flac.sampleRate, flac.bitsPerSample // 8, duration,
                             flac.totalPCMFrameCount, flac.maxBlockSize)
    finally:
        lib.drflac_close(flac)


def flac_get_info(data: bytes) -> SoundFileInfo:
    flac = lib.drflac_open_memory(data, len(data))
    if not flac:
        raise DecodeError("could not open/decode data")
    try:
        duration = flac.totalPCMFrameCount / flac.sampleRate
        return SoundFileInfo("<memory>", flac.channels, flac.sampleRate, flac.bitsPerSample // 8, duration,
                             flac.totalPCMFrameCount, flac.maxBlockSize)
    finally:
        lib.drflac_close(flac)


def flac_read_file_s32(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_file_and_read_pcm_frames_s32(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = _create_int_array(4)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drflac_free(memory)


def flac_read_file_s16(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_file_and_read_pcm_frames_s16(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, samples)
    finally:
        lib.drflac_free(memory)


def flac_read_file_f32(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_file_and_read_pcm_frames_f32(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drflac_free(memory)


def flac_read_s32(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_memory_and_read_pcm_frames_s32(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = _create_int_array(4)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drflac_free(memory)


def flac_read_s16(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_memory_and_read_pcm_frames_s16(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, samples)
    finally:
        lib.drflac_free(memory)


def flac_read_f32(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drflac_uint64 *")
    memory = lib.drflac_open_memory_and_read_pcm_frames_f32(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drflac_free(memory)


def flac_stream_file(filename: str, frames_to_read: int = 1024) -> Generator[array.array, None, None]:
    """Streams the flac audio file as interleaved 16 bit signed integer sample arrays segments."""
    filenamebytes = _get_filename_bytes(filename)
    flac = lib.drflac_open_file(filenamebytes)
    if not flac:
        raise DecodeError("could not open/decode file")
    try:
        decodebuffer = ffi.new("drflac_int16[]", frames_to_read * flac.channels)
        buf_ptr = ffi.cast("drflac_int16 *", decodebuffer)
        while True:
            num_samples = lib.drflac_read_pcm_frames_s16(flac, frames_to_read, buf_ptr)
            if num_samples <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_samples * 2 * flac.channels)
            samples = _create_int_array(2)
            samples.frombytes(buffer)
            yield samples
    finally:
        lib.drflac_close(flac)


def mp3_get_file_info(filename: str) -> SoundFileInfo:
    filenamebytes = _get_filename_bytes(filename)
    config = ffi.new("drmp3_config *")
    config.outputChannels = 0
    config.outputSampleRate = 0
    mp3 = ffi.new("drmp3 *")
    if not lib.drmp3_init_file(mp3, filenamebytes, config):
        raise DecodeError("could not open/decode file")
    try:
        num_frames = lib.drmp3_get_pcm_frame_count(mp3)
        duration = num_frames / mp3.sampleRate
        return SoundFileInfo(filename, mp3.channels, mp3.sampleRate, 2, duration, num_frames, 0)
    finally:
        lib.drmp3_uninit(mp3)


def mp3_get_info(data: bytes) -> SoundFileInfo:
    config = ffi.new("drmp3_config *")
    config.outputChannels = 0
    config.outputSampleRate = 0
    mp3 = ffi.new("drmp3 *")
    if not lib.drmp3_init_memory(mp3, data, len(data), config):
        raise DecodeError("could not open/decode data")
    try:
        num_frames = lib.drmp3_get_pcm_frame_count(mp3)
        duration = num_frames / mp3.sampleRate
        return SoundFileInfo("<memory>", mp3.channels, mp3.sampleRate, 2, duration, num_frames, 0)
    finally:
        lib.drmp3_uninit(mp3)


def mp3_read_file_f32(filename: str, want_nchannels: int = 0, want_sample_rate: int = 0) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    config = ffi.new("drmp3_config *")
    config.outputChannels = want_nchannels
    config.outputSampleRate = want_sample_rate
    num_frames = ffi.new("drmp3_uint64 *")
    memory = lib.drmp3_open_file_and_read_f32(filenamebytes, config, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * config.outputChannels * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, config.outputChannels, config.outputSampleRate, 4, samples)
    finally:
        lib.drmp3_free(memory)


def mp3_read_file_s16(filename: str, want_nchannels: int = 0, want_sample_rate: int = 0) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    config = ffi.new("drmp3_config *")
    config.outputChannels = want_nchannels
    config.outputSampleRate = want_sample_rate
    num_frames = ffi.new("drmp3_uint64 *")
    memory = lib.drmp3_open_file_and_read_s16(filenamebytes, config, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * config.outputChannels * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, config.outputChannels, config.outputSampleRate, 2, samples)
    finally:
        lib.drmp3_free(memory)


def mp3_read_f32(data: bytes, want_nchannels: int = 0, want_sample_rate: int = 0) -> DecodedSoundFile:
    config = ffi.new("drmp3_config *")
    config.outputChannels = want_nchannels
    config.outputSampleRate = want_sample_rate
    num_frames = ffi.new("drmp3_uint64 *")
    memory = lib.drmp3_open_memory_and_read_f32(data, len(data), config, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * config.outputChannels * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", config.outputChannels, config.outputSampleRate, 4, samples)
    finally:
        lib.drmp3_free(memory)


def mp3_read_s16(data: bytes, want_nchannels: int = 0, want_sample_rate: int = 0) -> DecodedSoundFile:
    config = ffi.new("drmp3_config *")
    config.outputChannels = want_nchannels
    config.outputSampleRate = want_sample_rate
    num_frames = ffi.new("drmp3_uint64 *")
    memory = lib.drmp3_open_memory_and_read_s16(data, len(data), config, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * config.outputChannels * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", config.outputChannels, config.outputSampleRate, 2, samples)
    finally:
        lib.drmp3_free(memory)


def mp3_stream_file(filename: str, frames_to_read: int = 1024,
                    want_nchannels: int = 0, want_sample_rate: int = 0) -> Generator[array.array, None, None]:
    """Streams the mp3 audio file as interleaved 16 bit signed integer sample arrays segments."""
    filenamebytes = _get_filename_bytes(filename)
    config = ffi.new("drmp3_config *")
    config.outputChannels = want_nchannels
    config.outputSampleRate = want_sample_rate
    mp3 = ffi.new("drmp3 *")
    if not lib.drmp3_init_file(mp3, filenamebytes, config):
        raise DecodeError("could not open/decode file")
    try:
        decodebuffer = ffi.new("drmp3_int16[]", frames_to_read * mp3.channels)
        buf_ptr = ffi.cast("drmp3_int16 *", decodebuffer)
        while True:
            num_samples = lib.drmp3_read_pcm_frames_s16(mp3, frames_to_read, buf_ptr)
            if num_samples <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_samples * 2 * mp3.channels)
            samples = _create_int_array(2)
            samples.frombytes(buffer)
            yield samples
    finally:
        lib.drmp3_uninit(mp3)


def wav_get_file_info(filename: str) -> SoundFileInfo:
    filenamebytes = _get_filename_bytes(filename)
    wav = lib.drwav_open_file(filenamebytes)
    if not wav:
        raise DecodeError("could not open/decode file")
    try:
        duration = wav.totalPCMFrameCount / wav.sampleRate
        return SoundFileInfo(filename, wav.channels, wav.sampleRate, wav.bitsPerSample // 8, duration,
                             wav.totalPCMFrameCount, 0)
    finally:
        lib.drwav_close(wav)


def wav_get_info(data: bytes) -> SoundFileInfo:
    wav = lib.drwav_open_memory(data, len(data))
    if not wav:
        raise DecodeError("could not open/decode data")
    try:
        duration = wav.totalPCMFrameCount / wav.sampleRate
        return SoundFileInfo("<memory>", wav.channels, wav.sampleRate, wav.bitsPerSample // 8, duration,
                             wav.totalPCMFrameCount, 0)
    finally:
        lib.drwav_close(wav)


def wav_read_file_s32(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_file_and_read_pcm_frames_s32(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = _create_int_array(4)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drwav_free(memory)


def wav_read_file_s16(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_file_and_read_pcm_frames_s16(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, samples)
    finally:
        lib.drwav_free(memory)


def wav_read_file_f32(filename: str) -> DecodedSoundFile:
    filenamebytes = _get_filename_bytes(filename)
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_file_and_read_pcm_frames_f32(filenamebytes, channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode file")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drwav_free(memory)


def wav_read_s32(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_memory_and_read_pcm_frames_s32(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = _create_int_array(4)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drwav_free(memory)


def wav_read_s16(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_memory_and_read_pcm_frames_s16(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = _create_int_array(2)
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 2)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, samples)
    finally:
        lib.drwav_free(memory)


def wav_read_f32(data: bytes) -> DecodedSoundFile:
    channels = ffi.new("unsigned int *")
    sample_rate = ffi.new("unsigned int *")
    num_frames = ffi.new("drwav_uint64 *")
    memory = lib.drwav_open_memory_and_read_pcm_frames_f32(data, len(data), channels, sample_rate, num_frames)
    if not memory:
        raise DecodeError("cannot load/decode data")
    try:
        samples = array.array('f')
        buffer = ffi.buffer(memory, num_frames[0] * channels[0] * 4)
        samples.frombytes(buffer)
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, samples)
    finally:
        lib.drwav_free(memory)


def wav_stream_file(filename: str, frames_to_read: int = 1024) -> Generator[array.array, None, None]:
    """Streams the WAV audio file as interleaved 16 bit signed integer sample arrays segments."""
    filenamebytes = _get_filename_bytes(filename)
    wav = lib.drwav_open_file(filenamebytes)
    if not wav:
        raise DecodeError("could not open/decode file")
    try:
        decodebuffer = ffi.new("drwav_int16[]", frames_to_read * wav.channels)
        buf_ptr = ffi.cast("drwav_int16 *", decodebuffer)
        while True:
            num_samples = lib.drwav_read_pcm_frames_s16(wav, frames_to_read, buf_ptr)
            if num_samples <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_samples * 2 * wav.channels)
            samples = _create_int_array(2)
            samples.frombytes(buffer)
            yield samples
    finally:
        lib.drwav_close(wav)


def _create_int_array(itemsize: int) -> array.array:
    for typecode in "bhilq":
        a = array.array(typecode)
        if a.itemsize == itemsize:
            return a
    raise ValueError("cannot create array")


def _get_filename_bytes(filename: str) -> bytes:
    filename2 = os.path.expanduser(filename)
    if not os.path.isfile(filename2):
        raise FileNotFoundError(filename)
    return filename2.encode(sys.getfilesystemencoding())
