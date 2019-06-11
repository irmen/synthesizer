# Use CFFI to create the glue code but also to actually compile the decoders in one go!
#
# Sound formats supported:
# - ogg vorbis via stb_vorbis
# - mp3 via dr_mp3
# - wav via dr_wav
# - flac via dr_flac

import os
from cffi import FFI

ffibuilder = FFI()
ffibuilder.cdef("""

void *malloc(size_t size);
void free(void *ptr);



/********************** stb_vorbis ******************************/

enum STBVorbisError
{
   VORBIS__no_error,

   VORBIS_need_more_data=1,             // not a real error

   VORBIS_invalid_api_mixing,           // can't mix API modes
   VORBIS_outofmem,                     // not enough memory
   VORBIS_feature_not_supported,        // uses floor 0
   VORBIS_too_many_channels,            // STB_VORBIS_MAX_CHANNELS is too small
   VORBIS_file_open_failure,            // fopen() failed
   VORBIS_seek_without_length,          // can't seek in unknown-length file

   VORBIS_unexpected_eof=10,            // file is truncated?
   VORBIS_seek_invalid,                 // seek past EOF

   // decoding errors (corrupt/invalid stream) -- you probably
   // don't care about the exact details of these

   // vorbis errors:
   VORBIS_invalid_setup=20,
   VORBIS_invalid_stream,

   // ogg errors:
   VORBIS_missing_capture_pattern=30,
   VORBIS_invalid_stream_structure_version,
   VORBIS_continued_packet_flag_invalid,
   VORBIS_incorrect_stream_serial_number,
   VORBIS_invalid_first_page,
   VORBIS_bad_packet_type,
   VORBIS_cant_find_last_page,
   VORBIS_seek_failed,
   VORBIS_ogg_skeleton_not_supported
};


typedef struct stb_vorbis stb_vorbis;

typedef struct
{
   unsigned int sample_rate;
   int channels;

   unsigned int setup_memory_required;
   unsigned int setup_temp_memory_required;
   unsigned int temp_memory_required;

   int max_frame_size;
} stb_vorbis_info;

stb_vorbis_info stb_vorbis_get_info(stb_vorbis *f);
int stb_vorbis_get_error(stb_vorbis *f);
void stb_vorbis_close(stb_vorbis *f);


int stb_vorbis_decode_filename(const char *filename, int *channels, int *sample_rate, short **output);
int stb_vorbis_decode_memory(const unsigned char *mem, int len, int *channels, int *sample_rate, short **output);

stb_vorbis * stb_vorbis_open_memory(const unsigned char *data, int len, int *error, void *ignore_alloc_buffer);
stb_vorbis * stb_vorbis_open_filename(const char *filename, int *error, void *ignore_alloc_buffer);

int stb_vorbis_seek_frame(stb_vorbis *f, unsigned int sample_number);
int stb_vorbis_seek(stb_vorbis *f, unsigned int sample_number);
int stb_vorbis_seek_start(stb_vorbis *f);

unsigned int stb_vorbis_stream_length_in_samples(stb_vorbis *f);
float        stb_vorbis_stream_length_in_seconds(stb_vorbis *f);

int stb_vorbis_get_frame_short_interleaved(stb_vorbis *f, int num_c, short *buffer, int num_shorts);

int stb_vorbis_get_samples_float_interleaved(stb_vorbis *f, int channels, float *buffer, int num_floats);
int stb_vorbis_get_samples_short_interleaved(stb_vorbis *f, int channels, short *buffer, int num_shorts);



/********************** dr_flac ******************************/

typedef int8_t           drflac_int8;
typedef uint8_t          drflac_uint8;
typedef int16_t          drflac_int16;
typedef uint16_t         drflac_uint16;
typedef int32_t          drflac_int32;
typedef uint32_t         drflac_uint32;
typedef int64_t          drflac_int64;
typedef uint64_t         drflac_uint64;
typedef drflac_uint8     drflac_bool8;
typedef drflac_uint32    drflac_bool32;

typedef struct
{
    drflac_uint32 sampleRate;
    drflac_uint8 channels;
    drflac_uint8 bitsPerSample;
    drflac_uint16 maxBlockSize;
    drflac_uint64 totalSampleCount;
    drflac_uint64 totalPCMFrameCount;

    ... ;

} drflac;


void drflac_close(drflac* pFlac);
drflac_uint64 drflac_read_pcm_frames_s32(drflac* pFlac, drflac_uint64 framesToRead, drflac_int32* pBufferOut);
drflac_uint64 drflac_read_pcm_frames_s16(drflac* pFlac, drflac_uint64 framesToRead, drflac_int16* pBufferOut);
drflac_uint64 drflac_read_pcm_frames_f32(drflac* pFlac, drflac_uint64 framesToRead, float* pBufferOut);
drflac_bool32 drflac_seek_to_pcm_frame(drflac* pFlac, drflac_uint64 pcmFrameIndex);
drflac* drflac_open_file(const char* filename);
drflac* drflac_open_memory(const void* data, size_t dataSize);

drflac_int32* drflac_open_file_and_read_pcm_frames_s32(const char* filename, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
drflac_int16* drflac_open_file_and_read_pcm_frames_s16(const char* filename, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
float* drflac_open_file_and_read_pcm_frames_f32(const char* filename, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
drflac_int32* drflac_open_memory_and_read_pcm_frames_s32(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
drflac_int16* drflac_open_memory_and_read_pcm_frames_s16(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
float* drflac_open_memory_and_read_pcm_frames_f32(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drflac_uint64* totalPCMFrameCount);
void drflac_free(void* p);


/********************** dr_mp3 **********************************/

    typedef int8_t           drmp3_int8;
    typedef uint8_t          drmp3_uint8;
    typedef int16_t          drmp3_int16;
    typedef uint16_t         drmp3_uint16;
    typedef int32_t          drmp3_int32;
    typedef uint32_t         drmp3_uint32;
    typedef int64_t          drmp3_int64;
    typedef uint64_t         drmp3_uint64;
    typedef drmp3_uint8      drmp3_bool8;
    typedef drmp3_uint32     drmp3_bool32;


typedef struct
{
    drmp3_uint32 outputChannels;
    drmp3_uint32 outputSampleRate;
} drmp3_config;


typedef struct
{
    drmp3_uint32 channels;
    drmp3_uint32 sampleRate;
    ...;
} drmp3;


drmp3_bool32 drmp3_init_memory(drmp3* pMP3, const void* pData, size_t dataSize, const drmp3_config* pConfig);
drmp3_bool32 drmp3_init_file(drmp3* pMP3, const char* filePath, const drmp3_config* pConfig);
void drmp3_uninit(drmp3* pMP3);

drmp3_uint64 drmp3_read_pcm_frames_f32(drmp3* pMP3, drmp3_uint64 framesToRead, float* pBufferOut);
drmp3_uint64 drmp3_read_pcm_frames_s16(drmp3* pMP3, drmp3_uint64 framesToRead, drmp3_int16* pBufferOut);
drmp3_bool32 drmp3_seek_to_pcm_frame(drmp3* pMP3, drmp3_uint64 frameIndex);
drmp3_uint64 drmp3_get_pcm_frame_count(drmp3* pMP3);
drmp3_uint64 drmp3_get_mp3_frame_count(drmp3* pMP3);
drmp3_bool32 drmp3_get_mp3_and_pcm_frame_count(drmp3* pMP3, drmp3_uint64* pMP3FrameCount, drmp3_uint64* pPCMFrameCount);

float* drmp3_open_memory_and_read_f32(const void* pData, size_t dataSize, drmp3_config* pConfig, drmp3_uint64* pTotalFrameCount);
drmp3_int16* drmp3_open_memory_and_read_s16(const void* pData, size_t dataSize, drmp3_config* pConfig, drmp3_uint64* pTotalFrameCount);
float* drmp3_open_file_and_read_f32(const char* filePath, drmp3_config* pConfig, drmp3_uint64* pTotalFrameCount);
drmp3_int16* drmp3_open_file_and_read_s16(const char* filePath, drmp3_config* pConfig, drmp3_uint64* pTotalFrameCount);
void drmp3_free(void* p);



/********************** dr_wav **********************************/

    typedef int8_t           drwav_int8;
    typedef uint8_t          drwav_uint8;
    typedef int16_t          drwav_int16;
    typedef uint16_t         drwav_uint16;
    typedef int32_t          drwav_int32;
    typedef uint32_t         drwav_uint32;
    typedef int64_t          drwav_int64;
    typedef uint64_t         drwav_uint64;
    typedef drwav_uint8      drwav_bool8;
    typedef drwav_uint32     drwav_bool32;


typedef struct
{
    drwav_uint32 sampleRate;
    drwav_uint16 channels;
    drwav_uint16 bitsPerSample;
    drwav_uint16 translatedFormatTag;
    drwav_uint64 totalPCMFrameCount;

    ...;

} drwav;


    drwav_bool32 drwav_init_file(drwav* pWav, const char* filename);
    drwav* drwav_open_file(const char* filename);
    drwav_bool32 drwav_init_memory(drwav* pWav, const void* data, size_t dataSize);
    drwav* drwav_open_memory(const void* data, size_t dataSize);

    void drwav_close(drwav* pWav);
    size_t drwav_read_raw(drwav* pWav, size_t bytesToRead, void* pBufferOut);
    drwav_uint64 drwav_read_pcm_frames(drwav* pWav, drwav_uint64 framesToRead, void* pBufferOut);
    drwav_bool32 drwav_seek_to_pcm_frame(drwav* pWav, drwav_uint64 targetFrameIndex);
    drwav_uint64 drwav_read_pcm_frames_s16(drwav* pWav, drwav_uint64 framesToRead, drwav_int16* pBufferOut);
    drwav_uint64 drwav_read_pcm_frames_f32(drwav* pWav, drwav_uint64 framesToRead, float* pBufferOut);
    drwav_uint64 drwav_read_pcm_frames_s32(drwav* pWav, drwav_uint64 framesToRead, drwav_int32* pBufferOut);

    drwav_int16* drwav_open_file_and_read_pcm_frames_s16(const char* filename, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);
    float* drwav_open_file_and_read_pcm_frames_f32(const char* filename, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);
    drwav_int32* drwav_open_file_and_read_pcm_frames_s32(const char* filename, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);

    drwav_int16* drwav_open_memory_and_read_pcm_frames_s16(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);
    float* drwav_open_memory_and_read_pcm_frames_f32(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);
    drwav_int32* drwav_open_memory_and_read_pcm_frames_s32(const void* data, size_t dataSize, unsigned int* channels, unsigned int* sampleRate, drwav_uint64* totalFrameCount);

    void drwav_free(void* pDataReturnedByOpenAndRead);

""")


libraries = []
compiler_args = []
if os.name == "posix":
    libraries = ["m", "pthread", "dl"]
    compiler_args = ["-g1"]


ffibuilder.set_source("_miniaudio", """
    #include <stdint.h>

    #define DR_FLAC_NO_OGG
    #include "miniaudio/dr_flac.h"
    #include "miniaudio/dr_wav.h"
    #include "miniaudio/dr_mp3.h"

    #define STB_VORBIS_HEADER_ONLY
    /* #define STB_VORBIS_NO_PUSHDATA_API  */   /*  needed by miniaudio decoding logic  */
    #include "miniaudio/stb_vorbis.c"

""",
                      sources=["miniaudio.c"],
                      libraries=libraries,
                      extra_compile_args=compiler_args)

print(libraries)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
