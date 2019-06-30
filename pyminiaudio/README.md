[![saythanks](https://img.shields.io/badge/say-thanks-ff69b4.svg)](https://saythanks.io/to/irmen)
[![Latest Version](https://img.shields.io/pypi/v/miniaudio.svg)](https://pypi.python.org/pypi/miniaudio/)


# Python miniaudio

This module provides:

- the [miniaudio](https://github.com/dr-soft/miniaudio/) cross platform sound playback and conversion library
- its decoders for wav, flac, vorbis and mp3
- python bindings via cffi for much of the functions offered in those libraries:
  - getting audio file properties (such as duration, number of channels, sample rate) 
  - reading and decoding audio files
  - streaming audio files
  - playback  (via efficient asynchronous pull-API)
  - streaming and playback are done with generator functions  


*Requires Python 3.5 or newer.  Also works on pypy3 (because it uses cffi).* 

Currently, it is mostly distributed in source form so you need a C compiler to build and install this.
For Linux and Mac this shouldn't be a problem. For Windows users, if the correct binary install
is not available on pypi, you'll have to compile it as well which may be a bit of a hassle 
on this platform: you have to make sure that the required tools (Visual Studio or 
the C++ build tools) are installed that allow you to compile Python extension modules.
 
Software license for these Python bindings, miniaudio and the decoders: MIT

## Todo

- the various format conversion functions aren't properly exposed yet.
- only playback for now, the recording capabilities of miniaudio aren't exposed yet 


## Examples

### Most basic audio file playback

```python
import miniaudio
stream = miniaudio.stream_file("samples/music.mp3")
device = miniaudio.PlaybackDevice()
device.start(stream)
input("Audio file playing in the background. Enter to stop playback: ")
device.close()
```

### Playback using several other API functions

```python
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
```

### Playback of a file format that miniaudio can't decode by itself

This example uses ffmpeg as an external tool to decode an audio file in a format
that miniaudio itself can't decode (m4a/aac in this case):

```python
import subprocess
import miniaudio

channels = 2
sample_rate = 44100
sample_width = 2  # 16 bit pcm
filename = "samples/music.m4a"  # AAC encoded audio file

def stream_pcm(source):
    required_frames = yield b""  # generator initialization
    while True:
        required_bytes = required_frames * channels * sample_width
        sample_data = source.read(required_bytes)
        if not sample_data:
            break
        print(".", end="", flush=True)
        required_frames = yield sample_data

device = miniaudio.PlaybackDevice(ma_output_format=miniaudio.ma_format_s16,
                                  nchannels=channels, sample_rate=sample_rate)
ffmpeg = subprocess.Popen(["ffmpeg", "-v", "fatal", "-hide_banner", "-nostdin",
                           "-i", filename, "-f", "s16le", "-acodec", "pcm_s16le",
                           "-ac", str(channels), "-ar", str(sample_rate), "-"],
                          stdin=None, stdout=subprocess.PIPE)
stream = stream_pcm(ffmpeg.stdout)
next(stream)  # start the generator
device.start(stream)
input("Audio file playing in the background. Enter to stop playback: ")
device.close()
ffmpeg.terminate()
``` 

## API

    get_file_info(filename: str) -> miniaudio.SoundFileInfo
        Fetch some information about the audio file.

    flac_get_file_info(filename: str) -> miniaudio.SoundFileInfo
        Fetch some information about the audio file (flac format).
    
    flac_get_info(data: bytes) -> miniaudio.SoundFileInfo
        Fetch some information about the audio data (flac format).
        
    flac_read_f32(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio file. Resulting sample format is 32 bits float.
    
    flac_read_file_f32(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio file. Resulting sample format is 32 bits float.
    
    flac_read_file_s16(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio file. Resulting sample format is 16 bits signed integer.
    
    flac_read_file_s32(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio file. Resulting sample format is 32 bits signed integer.
    
    flac_read_s16(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio data. Resulting sample format is 16 bits signed integer.
    
    flac_read_s32(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole flac audio data. Resulting sample format is 32 bits signed integer.
    
    flac_stream_file(filename: str, frames_to_read: int = 1024) -> Generator[array.array, NoneType, NoneType]
        Streams the flac audio file as interleaved 16 bit signed integer sample arrays segments.
    
    decode(data: bytes, ma_output_format: int = 2, nchannels: int = 2, sample_rate: int = 44100) -> miniaudio.DecodedSoundFile
        Convenience function to decode any supported audio file in memory to raw PCM samples in your chosen format.
    
    decode_file(filename: str, ma_output_format: int = 2, nchannels: int = 2, sample_rate: int = 44100) -> miniaudio.DecodedSoundFile
        Convenience function to decode any supported audio file to raw PCM samples in your chosen format.
    
    stream_file(filename: str, ma_output_format: int = 2, nchannels: int = 2, sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, int, NoneType]
        Convenience generator function to decode and stream any supported audio file
        as chunks of raw PCM samples in the chosen format.
        If you send() a number into the generator rather than just using next() on it,
        you'll get that given number of frames, instead of the default configured amount.
        This is particularly useful to plug this stream into an audio device callback that
        wants a variable number of frames per call.
    
    stream_memory(data: bytes, ma_output_format: int = 2, nchannels: int = 2, sample_rate: int = 44100, frames_to_read: int = 1024) -> Generator[array.array, int, NoneType]
        Convenience generator function to decode and stream any supported audio file in memory
        as chunks of raw PCM samples in the chosen format.
        If you send() a number into the generator rather than just using next() on it,
        you'll get that given number of frames, instead of the default configured amount.
        This is particularly useful to plug this stream into an audio device callback that
        wants a variable number of frames per call.
    
    mp3_get_file_info(filename: str) -> miniaudio.SoundFileInfo
        Fetch some information about the audio file (mp3 format).
    
    mp3_get_info(data: bytes) -> miniaudio.SoundFileInfo
        Fetch some information about the audio data (mp3 format).
    
    mp3_read_f32(data: bytes, want_nchannels: int = 0, want_sample_rate: int = 0) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole mp3 audio data. Resulting sample format is 32 bits float.
    
    mp3_read_file_f32(filename: str, want_nchannels: int = 0, want_sample_rate: int = 0) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole mp3 audio file. Resulting sample format is 32 bits float.
    
    mp3_read_file_s16(filename: str, want_nchannels: int = 0, want_sample_rate: int = 0) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole mp3 audio file. Resulting sample format is 16 bits signed integer.
    
    mp3_read_s16(data: bytes, want_nchannels: int = 0, want_sample_rate: int = 0) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole mp3 audio data. Resulting sample format is 16 bits signed integer.
    
    mp3_stream_file(filename: str, frames_to_read: int = 1024, want_nchannels: int = 0, want_sample_rate: int = 0) -> Generator[array.array, NoneType, NoneType]
        Streams the mp3 audio file as interleaved 16 bit signed integer sample arrays segments.
    
    read_file(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole audio file. Resulting sample format is 16 bits signed integer.
    
    vorbis_get_file_info(filename: str) -> miniaudio.SoundFileInfo
        Fetch some information about the audio file (vorbis format).
    
    vorbis_get_info(data: bytes) -> miniaudio.SoundFileInfo
        Fetch some information about the audio data (vorbis format).
    
    vorbis_read(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole vorbis audio data. Resulting sample format is 16 bits signed integer.
    
    vorbis_read_file(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole vorbis audio file. Resulting sample format is 16 bits signed integer.
    
    vorbis_stream_file(filename: str) -> Generator[array.array, NoneType, NoneType]
        Streams the ogg vorbis audio file as interleaved 16 bit signed integer sample arrays segments.
    
    wav_get_file_info(filename: str) -> miniaudio.SoundFileInfo
        Fetch some information about the audio file (wav format).
    
    wav_get_info(data: bytes) -> miniaudio.SoundFileInfo
        Fetch some information about the audio data (wav format).
    
    wav_read_f32(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio data. Resulting sample format is 32 bits float.
    
    wav_read_file_f32(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio file. Resulting sample format is 32 bits float.
    
    wav_read_file_s16(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio file. Resulting sample format is 16 bits signed integer.
    
    wav_read_file_s32(filename: str) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio file. Resulting sample format is 32 bits signed integer.
    
    wav_read_s16(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio data. Resulting sample format is 16 bits signed integer.
    
    wav_read_s32(data: bytes) -> miniaudio.DecodedSoundFile
        Reads and decodes the whole wav audio data. Resulting sample format is 32 bits signed integer.
    
    wav_stream_file(filename: str, frames_to_read: int = 1024) -> Generator[array.array, NoneType, NoneType]
        Streams the WAV audio file as interleaved 16 bit signed integer sample arrays segments.

    wav_write_file(filename: str, sound: miniaudio.DecodedSoundFile) -> None
        Writes the pcm sound to a WAV file


    class PlaybackDevice(ma_output_format: int = 2, nchannels: int = 2, sample_rate: int = 44100, buffersize_msec: int = 200)
       An audio device provided by miniaudio, for audio playback.
       
       close(self)
           Halt playback and close down the device.
       
       start(self, audio_producer: Callable[[int, int, int], Union[bytes, array.array]]) -> None
           Start the audio device: playback begins. The audio data is provided by the given audio_producer
           generator. The generator gets sent the required number of frames and should yield the sample data
           as raw bytes or as an array.array.  (it should already be started before passing it in)
       
       stop(self) -> None
           Halt playback.


    class WavFileReadStream(pcm_sample_gen: Generator[Union[bytes, array.array], int, NoneType], sample_rate: int, nchannels: int, ma_output_format: int, max_frames: int = 0) -> None
        An IO stream that reads as a .wav file, and which gets its pcm samples from the provided producer
    
        close(self) -> None
            Flush and close the IO object.
        
        read(self, amount: int) -> Union[bytes, NoneType]
            Read bytes from the stream.


    class Devices:
        Access to the audio playback and record devices that miniaudio exposes
    
        get_captures(self) -> List[miniaudio.Device]
            Get a list of capture devices
        
        get_playbacks(self) -> List[miniaudio.Device]
            Get a list of playback devices
        

    class DeviceInfo:
        Contains various properties of a miniaudio playback or record device

        info(self) -> Dict[str, Any]
            obtain detailed info about the device
