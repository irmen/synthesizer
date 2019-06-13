import sys
import os
import array
import struct
import weakref
import queue
from typing import Generator, List, Tuple, Optional
from _miniaudio import ffi, lib
from _miniaudio.lib import ma_format_f32, ma_format_u8, ma_format_s16, ma_format_s32


__version__ = "1.0"


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


class MiniaudioError(Exception):
    pass


class DecodeError(MiniaudioError):
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


# MiniAudio API follows


class DeviceInfo:
    def __init__(self, name: str, ma_device_type: int, formats: List[str],
                 min_channels: int, max_channels: int, min_sample_rate: int, max_sample_rate: int) -> None:
        self.name = name
        self.ma_device_type = ma_device_type
        self.formats = formats
        self.min_channels = min_channels
        self.max_channels = max_channels
        self.min_sample_rate = min_sample_rate
        self.max_sample_rate = max_sample_rate


def ma_get_devices() -> Tuple[List[str], List[str]]:
    playback_infos = ffi.new("ma_device_info**")
    playback_count = ffi.new("ma_uint32*")
    capture_infos = ffi.new("ma_device_info**")
    capture_count = ffi.new("ma_uint32*")
    context = ffi.new("ma_context*")
    result = lib.ma_context_init(ffi.NULL, 0, ffi.NULL, context)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("cannot init context", result)
    try:
        result = lib.ma_context_get_devices(context, playback_infos, playback_count, capture_infos, capture_count)
        if result != lib.MA_SUCCESS:
            raise MiniaudioError("cannot get device infos", result)
        devs_playback = []
        devs_captures = []
        for i in range(playback_count[0]):
            ma_device_info = playback_infos[0][i]
            devs_playback.append(ffi.string(ma_device_info.name).decode())
            # rest of the info structure is not filled...
        for i in range(capture_count[0]):
            ma_device_info = capture_infos[0][i]
            devs_captures.append(ffi.string(ma_device_info.name).decode())
            # rest of the info structure is not filled...
        return devs_playback, devs_captures
    finally:
        lib.ma_context_uninit(context)


def _decode_ma_format(ma_output_format: int) -> Tuple[int, array.array]:
    if ma_output_format == ma_format_f32:
        return 4, array.array('f')
    elif ma_output_format == ma_format_u8:
        return 1, _create_int_array(1)
    elif ma_output_format == ma_format_s16:
        return 2, _create_int_array(2)
    elif ma_output_format == ma_format_s32:
        return 4, _create_int_array(4)
    else:
        raise ValueError("unsupported miniaudio sample format", ma_output_format)


def ma_decode_file(filename: str, ma_output_format: int = ma_format_s16,
                   nchannels: int = 2, sample_rate: int = 44100) -> DecodedSoundFile:
    """Convenience function to decode any supported audio file to raw PCM samples in your chosen format."""
    sample_width, samples = _decode_ma_format(ma_output_format)
    filenamebytes = _get_filename_bytes(filename)
    frames = ffi.new("ma_uint64 *")
    data = ffi.new("void **")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decode_file(filenamebytes, ffi.addressof(decoder_config), frames, data)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode file", result)
    buffer = ffi.buffer(data[0], frames[0] * nchannels * sample_width)
    samples.frombytes(buffer)
    return DecodedSoundFile(filename, nchannels, sample_rate, sample_width, samples)


def ma_decode(data: bytes, ma_output_format: int = ma_format_s16,
              nchannels: int = 2, sample_rate: int = 44100) -> DecodedSoundFile:
    """Convenience function to decode any supported audio file in memory to raw PCM samples in your chosen format."""
    sample_width, samples = _decode_ma_format(ma_output_format)
    frames = ffi.new("ma_uint64 *")
    memory = ffi.new("void **")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decode_memory(data, len(data), ffi.addressof(decoder_config), frames, memory)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode data", result)
    buffer = ffi.buffer(memory[0], frames[0] * nchannels * sample_width)
    samples.frombytes(buffer)
    return DecodedSoundFile("<memory>", nchannels, sample_rate, sample_width, samples)


def ma_stream_file(filename: str, ma_output_format: int = ma_format_s16,
                   nchannels: int = 2, sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, None, None]:
    """Convenience function to decode and stream any supported audio file as chunks of raw PCM samples in the chosen format."""
    sample_width, samples_proto = _decode_ma_format(ma_output_format)
    filenamebytes = _get_filename_bytes(filename)
    decoder = ffi.new("ma_decoder *")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decoder_init_file(filenamebytes, ffi.addressof(decoder_config), decoder)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode file", result)
    try:
        decodebuffer = ffi.new("int8_t[]", frames_to_read * nchannels * sample_width)
        buf_ptr = ffi.cast("void *", decodebuffer)
        while True:
            num_frames = lib.ma_decoder_read_pcm_frames(decoder, buf_ptr, frames_to_read)
            if num_frames <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_frames * sample_width * nchannels)
            samples = array.array(samples_proto.typecode)
            samples.frombytes(buffer)
            yield samples
    finally:
        lib.ma_decoder_uninit(decoder)


def ma_stream_memory(data: bytes, ma_output_format: int = ma_format_s16,
                   nchannels: int = 2, sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, None, None]:
    """Convenience function to decode and stream any supported audio file in memory
    as chunks of raw PCM samples in the chosen format."""
    sample_width, samples_proto = _decode_ma_format(ma_output_format)
    decoder = ffi.new("ma_decoder *")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decoder_init_memory(data, len(data), ffi.addressof(decoder_config), decoder)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode memory", result)
    try:
        decodebuffer = ffi.new("int8_t[]", frames_to_read * nchannels * sample_width)
        buf_ptr = ffi.cast("void *", decodebuffer)
        while True:
            num_frames = lib.ma_decoder_read_pcm_frames(decoder, buf_ptr, frames_to_read)
            if num_frames <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_frames * sample_width * nchannels)
            samples = array.array(samples_proto.typecode)
            samples.frombytes(buffer)
            yield samples
    finally:
        lib.ma_decoder_uninit(decoder)



_callback_data = {}
global_weakkeydict = weakref.WeakKeyDictionary()


class CallbackUserdata:
    def __init__(self, sample_width: int, nchannels: int) -> None:
        self.queue = queue.Queue(maxsize=100)
        self.residue = _create_int_array(sample_width)
        self.nchannels = nchannels

    def residue_too_small(self, frames_wanted: int) -> bool:
        return len(self.residue) < frames_wanted        # TODO ???

    def get_required_residue_and_keep_rest(self, frames_wanted: int) -> array.array:
        result = self.residue[:frames_wanted]       # ???
        self.residue = self.residue[frames_wanted:]
        return result


@ffi.def_extern()
def data_callback(device: ffi.CData, output: ffi.CData, input: ffi.CData, framecount: int) -> None:
    if framecount == 0 or not device.pUserData:
        return
    userdata_id = struct.unpack('q', ffi.unpack(ffi.cast("char *", device.pUserData), struct.calcsize('q')))[0]
    userdata = _callback_data[userdata_id]  # type: CallbackUserdata
    while userdata.residue_too_small(framecount):
        try:
            samples = userdata.queue.get_nowait()
            userdata.residue.extend(samples)
        except queue.Empty:
            # hmm, there's still not enough data to proceed...
            pass # TODO extend with zero samples
    data = userdata.get_required_residue_and_keep_rest(framecount)
    print("got", len(data), framecount)   # TODO process


def ma_device_init(ma_output_format: int = ma_format_s16, nchannels: int = 2,
                   sample_rate: int = 44100, buffersize_msec: int = 200) -> Generator[None, Tuple[str, array.array], None]:
    # always assume playback for now
    # TODO meaningful implementation
    devconfig = lib.ma_device_config_init(lib.ma_device_type_playback)
    devconfig.sampleRate = sample_rate
    devconfig.bufferSizeInMilliseconds = buffersize_msec
    devconfig.dataCallback = lib.data_callback
    sample_width, samples_proto = _decode_ma_format(ma_output_format)
    userdata = CallbackUserdata(sample_width, nchannels)
    userdata_id = id(userdata)
    _callback_data[userdata_id] = userdata
    userdata_ptr = ffi.new("char[]", struct.pack('q', userdata_id))
    global_weakkeydict[devconfig] = userdata_ptr    # keep ownership alive of the pointer
    devconfig.pUserData = userdata_ptr
    #devconfig.playback.format = 9999 # TODO
    #devconfig.playback.channels = nchannels # TODO
    device = ffi.new("ma_device *")
    result = lib.ma_device_init(ffi.NULL, ffi.addressof(devconfig), device)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to init device", result)
    try:
        print("GOT", result, device[0], dir(device[0]), device[0].sampleRate)  # TODO
        while True:
            command, arg = yield None
            if command == "start":
                result = lib.ma_device_start(device)
                if result != lib.MA_SUCCESS:
                    raise MiniaudioError("failed to start audio device", result)
            elif command == "stop":
                lib.ma_device_stop(device)
            elif command == "quit":
                break
            elif command == "play":
                if not isinstance(arg, array.array) or arg.typecode != samples_proto.typecode:
                    raise TypeError("play arg should be array.array with typecode "+samples_proto.typecode)
                userdata.queue.put(arg)
                print("put some data", len(arg))
            else:
                raise MiniaudioError("invalid device command", command)
    finally:
        lib.ma_device_uninit(device)
        del _callback_data[userdata_id]
        try:
            yield
        except GeneratorExit:
            pass

    # void ma_device_set_stop_callback(ma_device* pDevice, ma_stop_proc proc);
