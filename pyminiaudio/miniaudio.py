"""
Python interface to the miniaudio library (https://github.com/dr-soft/miniaudio)

Author: Irmen de Jong (irmen@razorvine.net)
Software license: "MIT software license". See http://opensource.org/licenses/MIT
"""

import sys
import os
import array
import struct
from typing import Generator, List, Tuple, Dict, Callable, Optional, Union, Any
from _miniaudio import ffi, lib
from _miniaudio.lib import ma_format_f32, ma_format_u8, ma_format_s16, ma_format_s32

lib.init_miniaudio()


__version__ = "1.1"


class DecodedSoundFile:
    def __init__(self, name: str, nchannels: int, sample_rate: int, sample_width: int,
                 sample_format: int, samples: array.array) -> None:
        self.name = name
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.sample_format = sample_format      # one of the ma_format_ values
        self.sample_format_name = ffi.string(lib.ma_get_format_name(sample_format)).decode()
        self.samples = samples


class SoundFileInfo:
    def __init__(self, name: str, nchannels: int, sample_rate: int, sample_width: int, sample_format: int,
                 duration: float, num_frames: int, max_frame_size: int) -> None:
        self.name = name
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.sample_width = sample_width
        self.sample_format = sample_format      # one of the ma_format_ values
        self.sample_format_name = ffi.string(lib.ma_get_format_name(sample_format)).decode()
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
        return SoundFileInfo(filename, info.channels, info.sample_rate, 2, ma_format_s16,
                             duration, num_frames, info.max_frame_size)
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
        return SoundFileInfo("<memory>", info.channels, info.sample_rate, 2, ma_format_s16,
                             duration, num_frames, info.max_frame_size)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        sample_width = flac.bitsPerSample // 8
        return SoundFileInfo(filename, flac.channels, flac.sampleRate, sample_width,
                             _ma_format_from_width(sample_width), duration, flac.totalPCMFrameCount, flac.maxBlockSize)
    finally:
        lib.drflac_close(flac)


def flac_get_info(data: bytes) -> SoundFileInfo:
    flac = lib.drflac_open_memory(data, len(data))
    if not flac:
        raise DecodeError("could not open/decode data")
    try:
        duration = flac.totalPCMFrameCount / flac.sampleRate
        sample_width = flac.bitsPerSample // 8
        return SoundFileInfo("<memory>", flac.channels, flac.sampleRate, sample_width,
                             _ma_format_from_width(sample_width), duration, flac.totalPCMFrameCount, flac.maxBlockSize)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, ma_format_s32, samples)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, ma_format_f32, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, ma_format_s32, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, ma_format_f32, samples)
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
        return SoundFileInfo(filename, mp3.channels, mp3.sampleRate, 2, ma_format_s16, duration, num_frames, 0)
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
        return SoundFileInfo("<memory>", mp3.channels, mp3.sampleRate, 2, ma_format_s16, duration, num_frames, 0)
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
        return DecodedSoundFile(filename, config.outputChannels, config.outputSampleRate, 4, ma_format_f32, samples)
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
        return DecodedSoundFile(filename, config.outputChannels, config.outputSampleRate, 2, ma_format_s16, samples)
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
        return DecodedSoundFile("<memory>", config.outputChannels, config.outputSampleRate, 4, ma_format_f32, samples)
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
        return DecodedSoundFile("<memory>", config.outputChannels, config.outputSampleRate, 2, ma_format_s16, samples)
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
        sample_width = wav.bitsPerSample // 8
        return SoundFileInfo(filename, wav.channels, wav.sampleRate, sample_width,
                             _ma_format_from_width(sample_width), duration, wav.totalPCMFrameCount, 0)
    finally:
        lib.drwav_close(wav)


def wav_get_info(data: bytes) -> SoundFileInfo:
    wav = lib.drwav_open_memory(data, len(data))
    if not wav:
        raise DecodeError("could not open/decode data")
    try:
        duration = wav.totalPCMFrameCount / wav.sampleRate
        sample_width = wav.bitsPerSample // 8
        return SoundFileInfo("<memory>", wav.channels, wav.sampleRate, sample_width,
                             _ma_format_from_width(sample_width), duration, wav.totalPCMFrameCount, 0)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, ma_format_s32, samples)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        return DecodedSoundFile(filename, channels[0], sample_rate[0], 4, ma_format_f32, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, ma_format_s32, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 2, ma_format_s16, samples)
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
        return DecodedSoundFile("<memory>", channels[0], sample_rate[0], 4, ma_format_f32, samples)
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


def _ma_format_from_width(sample_width: int, is_float: bool = False) -> int:
    if is_float:
        return ma_format_f32
    elif sample_width == 1:
        return ma_format_u8
    elif sample_width == 2:
        return ma_format_s16
    elif sample_width == 4:
        return ma_format_s32
    else:
        raise ValueError("unsupported sample_width", sample_width)


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
    return DecodedSoundFile(filename, nchannels, sample_rate, sample_width, ma_output_format, samples)


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
    return DecodedSoundFile("<memory>", nchannels, sample_rate, sample_width, ma_output_format, samples)


def _samples_generator(frames_to_read: int, nchannels: int, ma_output_format: int,
                       decoder: ffi.CData, data: Any) -> Generator[array.array, int, None]:
    _reference = data    # make sure any data passed in is not garbage collected
    sample_width, samples_proto = _decode_ma_format(ma_output_format)
    allocated_buffer_frames = max(frames_to_read, 16384)
    try:
        decodebuffer = ffi.new("int8_t[]", allocated_buffer_frames * nchannels * sample_width)
        buf_ptr = ffi.cast("void *", decodebuffer)
        want_frames = (yield samples_proto) or frames_to_read
        while True:
            if want_frames > allocated_buffer_frames:
                raise MiniaudioError("wanted to read more frames than storage was allocated for ({} vs {})"
                                     .format(want_frames, allocated_buffer_frames))
            num_frames = lib.ma_decoder_read_pcm_frames(decoder, buf_ptr, want_frames)
            if num_frames <= 0:
                break
            buffer = ffi.buffer(decodebuffer, num_frames * sample_width * nchannels)
            samples = array.array(samples_proto.typecode)
            samples.frombytes(buffer)
            want_frames = yield samples
    finally:
        lib.ma_decoder_uninit(decoder)


def ma_stream_file(filename: str, ma_output_format: int = ma_format_s16, nchannels: int = 2,
                   sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, int, None]:
    """
    Convenience generator function to decode and stream any supported audio file
    as chunks of raw PCM samples in the chosen format.
    If you send() a number into the generator rather than just using next() on it,
    you'll get that given number of frames, instead of the default configured amount.
    This is particularly useful to plug this stream into an audio device callback that
    wants a variable number of frames per call.
    """
    filenamebytes = _get_filename_bytes(filename)
    decoder = ffi.new("ma_decoder *")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decoder_init_file(filenamebytes, ffi.addressof(decoder_config), decoder)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode file", result)
    g = _samples_generator(frames_to_read, nchannels, ma_output_format, decoder, None)
    next(g)
    return g


def ma_stream_memory(data: bytes, ma_output_format: int = ma_format_s16, nchannels: int = 2,
                     sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, int, None]:
    """
    Convenience generator function to decode and stream any supported audio file in memory
    as chunks of raw PCM samples in the chosen format.
    If you send() a number into the generator rather than just using next() on it,
    you'll get that given number of frames, instead of the default configured amount.
    This is particularly useful to plug this stream into an audio device callback that
    wants a variable number of frames per call.
    """
    decoder = ffi.new("ma_decoder *")
    decoder_config = lib.ma_decoder_config_init(ma_output_format, nchannels, sample_rate)
    result = lib.ma_decoder_init_memory(data, len(data), ffi.addressof(decoder_config), decoder)
    if result != lib.MA_SUCCESS:
        raise MiniaudioError("failed to decode memory", result)
    g = _samples_generator(frames_to_read, nchannels, ma_output_format, decoder, data)
    next(g)
    return g


_callback_data = {}     # type: Dict[int, PlaybackDevice]


@ffi.def_extern()
def internal_data_callback(device: ffi.CData, output: ffi.CData, input: ffi.CData, framecount: int) -> None:
    if framecount == 0 or not device.pUserData:
        return
    userdata_id = struct.unpack('q', ffi.unpack(ffi.cast("char *", device.pUserData), struct.calcsize('q')))[0]
    playback_device = _callback_data[userdata_id]  # type: PlaybackDevice
    playback_device.data_callback(device, output, input, framecount)


AudioProducerType = Callable[[int, int, int], Union[bytes, array.array]]


class PlaybackDevice:
    def __init__(self, ma_output_format: int = ma_format_s16, nchannels: int = 2,
                 sample_rate: int = 44100, buffersize_msec: int = 200):
        self.format = ma_output_format
        self.sample_width, self.samples_array_proto = _decode_ma_format(ma_output_format)
        self.nchannels = nchannels
        self.sample_rate = sample_rate
        self.buffersize_msec = buffersize_msec
        self._device = ffi.new("ma_device *")
        _callback_data[id(self)] = self
        self.userdata_ptr = ffi.new("char[]", struct.pack('q', id(self)))
        self._devconfig = lib.ma_device_config_init(lib.ma_device_type_playback)
        lib.ma_device_config_set_params(ffi.addressof(self._devconfig), self.sample_rate, self.buffersize_msec,
                                        0, self.format, self.nchannels, 0, 0)
        self._devconfig.pUserData = self.userdata_ptr
        self._devconfig.dataCallback = lib.internal_data_callback
        self.audio_producer = None   # type: Optional[AudioProducerType]
        result = lib.ma_device_init(ffi.NULL, ffi.addressof(self._devconfig), self._device)
        if result != lib.MA_SUCCESS:
            raise MiniaudioError("failed to init device", result)
        if self._device.pContext.backend == lib.ma_backend_null:
            raise MiniaudioError("no suitable audio backend found")
        self.backend = ffi.string(lib.ma_get_backend_name(self._device.pContext.backend)).decode()

    def __del__(self) -> None:
        self.close()

    def start(self, audio_producer: AudioProducerType) -> None:
        if self.audio_producer:
            raise MiniaudioError("can't start an already started device")
        self.audio_producer = audio_producer
        result = lib.ma_device_start(self._device)
        if result != lib.MA_SUCCESS:
            raise MiniaudioError("failed to start audio device", result)

    def stop(self) -> None:
        self.audio_producer = None
        result = lib.ma_device_stop(self._device)
        if result != lib.MA_SUCCESS:
            raise MiniaudioError("failed to stop audio device", result)

    def close(self):
        self.audio_producer = None
        if self._device is not None:
            lib.ma_device_uninit(self._device)
            self._device = None
        if id(self) in _callback_data:
            del _callback_data[id(self)]

    def data_callback(self, device: ffi.CData, output: ffi.CData, input: ffi.CData, framecount: int) -> None:
        if self.audio_producer:
            samples = self.audio_producer(framecount, self.sample_width, self.nchannels)
            if isinstance(samples, array.array):
                samples_bytes = memoryview(samples).cast('B')       # type: ignore
            else:
                samples_bytes = samples
            if samples_bytes:
                if len(samples_bytes) > framecount * self.sample_width * self.nchannels:
                    self.audio_producer = None
                    raise MiniaudioError("number of frames from callback exceeds maximum")
                ffi.memmove(output, samples_bytes, len(samples_bytes))
