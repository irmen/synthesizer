"""
Python interface to the miniaudio library (https://github.com/dr-soft/miniaudio)

This module Use CFFI to create the glue code but also to actually compile the decoders in one go!
Sound formats supported:
 - ogg vorbis via stb_vorbis
 - mp3 via dr_mp3
 - wav via dr_wav
 - flac via dr_flac

Author: Irmen de Jong (irmen@razorvine.net)
Software license: "MIT software license". See http://opensource.org/licenses/MIT
"""


import os
from cffi import FFI

miniaudio_include_dir = os.getcwd()

if os.name == "nt":
    vorbis_defs = ""        # on windows, visual c++ currently can't compile in the stb_vorbis lib
else:
    vorbis_defs = """

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


"""


ffibuilder = FFI()
ffibuilder.cdef(vorbis_defs + """

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


typedef int ma_result;
#define MA_SUCCESS                                      0

/* General errors. */
#define MA_ERROR                                       -1      /* A generic error. */
#define MA_INVALID_ARGS                                -2
#define MA_INVALID_OPERATION                           -3
#define MA_OUT_OF_MEMORY                               -4
#define MA_ACCESS_DENIED                               -5
#define MA_TOO_LARGE                                   -6
#define MA_TIMEOUT                                     -7

/* General miniaudio-specific errors. */
#define MA_FORMAT_NOT_SUPPORTED                        -100
#define MA_DEVICE_TYPE_NOT_SUPPORTED                   -101
#define MA_SHARE_MODE_NOT_SUPPORTED                    -102
#define MA_NO_BACKEND                                  -103
#define MA_NO_DEVICE                                   -104
#define MA_API_NOT_FOUND                               -105
#define MA_INVALID_DEVICE_CONFIG                       -106

/* State errors. */
#define MA_DEVICE_BUSY                                 -200
#define MA_DEVICE_NOT_INITIALIZED                      -201
#define MA_DEVICE_NOT_STARTED                          -202
#define MA_DEVICE_UNAVAILABLE                          -203

/* Operation errors. */
#define MA_FAILED_TO_MAP_DEVICE_BUFFER                 -300
#define MA_FAILED_TO_UNMAP_DEVICE_BUFFER               -301
#define MA_FAILED_TO_INIT_BACKEND                      -302
#define MA_FAILED_TO_READ_DATA_FROM_CLIENT             -303
#define MA_FAILED_TO_READ_DATA_FROM_DEVICE             -304
#define MA_FAILED_TO_SEND_DATA_TO_CLIENT               -305
#define MA_FAILED_TO_SEND_DATA_TO_DEVICE               -306
#define MA_FAILED_TO_OPEN_BACKEND_DEVICE               -307
#define MA_FAILED_TO_START_BACKEND_DEVICE              -308
#define MA_FAILED_TO_STOP_BACKEND_DEVICE               -309
#define MA_FAILED_TO_CONFIGURE_BACKEND_DEVICE          -310
#define MA_FAILED_TO_CREATE_MUTEX                      -311
#define MA_FAILED_TO_CREATE_EVENT                      -312
#define MA_FAILED_TO_CREATE_THREAD                     -313


#define MA_MIN_CHANNELS                                1
#define MA_MAX_CHANNELS                                32
#define MA_MIN_SAMPLE_RATE                             8000
#define MA_MAX_SAMPLE_RATE                             384000


typedef enum
{
    ma_backend_wasapi,
    ma_backend_dsound,
    ma_backend_winmm,
    ma_backend_coreaudio,
    ma_backend_sndio,
    ma_backend_audio4,
    ma_backend_oss,
    ma_backend_pulseaudio,
    ma_backend_alsa,
    ma_backend_jack,
    ma_backend_aaudio,
    ma_backend_opensl,
    ma_backend_webaudio,
    ma_backend_null    
} ma_backend;

    typedef int8_t   ma_int8;
    typedef uint8_t  ma_uint8;
    typedef int16_t  ma_int16;
    typedef uint16_t ma_uint16;
    typedef int32_t  ma_int32;
    typedef uint32_t ma_uint32;
    typedef int64_t  ma_int64;
    typedef uint64_t ma_uint64;
    typedef uintptr_t ma_uintptr;
    typedef ma_uint8                   ma_bool8;
    typedef ma_uint32                  ma_bool32;
    
    
typedef enum
{
    ma_dither_mode_none = 0,
    ma_dither_mode_rectangle,
    ma_dither_mode_triangle
} ma_dither_mode;

typedef enum
{
    ma_format_unknown = 0,
    ma_format_u8      = 1,
    ma_format_s16     = 2,
    ma_format_s24     = 3,
    ma_format_s32     = 4,
    ma_format_f32     = 5,
    ma_format_count   = 6
} ma_format;


typedef enum
{
    ma_channel_mix_mode_rectangular = 0,   /* Simple averaging based on the plane(s) the channel is sitting on. */
    ma_channel_mix_mode_simple,            /* Drop excess channels; zeroed out extra channels. */
    ma_channel_mix_mode_custom_weights,    /* Use custom weights specified in ma_channel_router_config. */
    ma_channel_mix_mode_planar_blend = ma_channel_mix_mode_rectangular,
    ma_channel_mix_mode_default = ma_channel_mix_mode_planar_blend
} ma_channel_mix_mode;


typedef enum
{
    ma_thread_priority_idle     = -5,
    ma_thread_priority_lowest   = -4,
    ma_thread_priority_low      = -3,
    ma_thread_priority_normal   = -2,
    ma_thread_priority_high     = -1,
    ma_thread_priority_highest  =  0,
    ma_thread_priority_realtime =  1,
    ma_thread_priority_default  =  0
} ma_thread_priority;

    
typedef enum
{
    ma_device_type_playback = 1,
    ma_device_type_capture  = 2,
    ma_device_type_duplex   = 3
} ma_device_type;

typedef enum
{
    ma_share_mode_shared = 0,
    ma_share_mode_exclusive
} ma_share_mode;


typedef union ma_device_id {
    ...;
} ma_device_id;
typedef struct ma_context {
    ma_backend backend;
    ...;
} ma_context;

typedef ma_uint8 ma_channel;
typedef struct ma_device ma_device;

typedef void (* ma_device_callback_proc)(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount);
typedef void (* ma_stop_proc)(ma_device* pDevice);
typedef void (* ma_log_proc)(ma_context* pContext, ma_device* pDevice, ma_uint32 logLevel, const char* message);


struct ma_device {
    ma_context* pContext;
    ma_device_type type;
    ma_uint32 sampleRate;
    ma_uint32 state;
    ma_device_callback_proc onData;
    ma_stop_proc onStop;
    void* pUserData;                        /* Application defined data. */

    ...;
};


typedef struct
{
    ma_device_id id;
    char name[256];
    ma_uint32 formatCount;
    ma_format formats[ma_format_count];
    ma_uint32 minChannels;
    ma_uint32 maxChannels;
    ma_uint32 minSampleRate;
    ma_uint32 maxSampleRate;
    
    ...;
} ma_device_info;


typedef struct
{
    ma_device_type deviceType;
    ma_uint32 sampleRate;
    ma_uint32 bufferSizeInFrames;
    ma_uint32 bufferSizeInMilliseconds;
    ma_device_callback_proc dataCallback;
    ma_stop_proc stopCallback;
    void* pUserData;
    
    /* TODO: missing 'playback' nested struct */
    /* TODO: missing 'capture' nested struct */
    
    ...;
} ma_device_config;


typedef struct
{
    ma_thread_priority threadPriority;
    ...;
} ma_context_config;

typedef struct
{
    ma_format format;
    ma_uint32 channels;
    ma_uint32 sampleRate;
    ma_channel_mix_mode channelMixMode;
    ma_dither_mode ditherMode;
    ...;
} ma_decoder_config;


typedef struct ma_decoder
{
    /* ma_decoder_read_proc onRead; */
    /* ma_decoder_seek_proc onSeek; */
    ma_format  outputFormat;
    ma_uint32  outputChannels;
    ma_uint32  outputSampleRate;
    
    ...;
} ma_decoder;


typedef ma_bool32 (* ma_enum_devices_callback_proc)(ma_context* pContext, ma_device_type deviceType, const ma_device_info* pInfo, void* pUserData);


    /**** allocation / initialization / device control ****/
    void ma_free(void* p);
    ma_result ma_context_init(const ma_backend backends[], ma_uint32 backendCount, const ma_context_config* pConfig, ma_context* pContext);
    ma_result ma_context_uninit(ma_context* pContext);
    ma_result ma_context_enumerate_devices(ma_context* pContext, ma_enum_devices_callback_proc callback, void* pUserData);
    ma_result ma_context_get_devices(ma_context* pContext, ma_device_info** ppPlaybackDeviceInfos, ma_uint32* pPlaybackDeviceCount, ma_device_info** ppCaptureDeviceInfos, ma_uint32* pCaptureDeviceCount);
    ma_result ma_context_get_device_info(ma_context* pContext, ma_device_type deviceType, const ma_device_id* pDeviceID, ma_share_mode shareMode, ma_device_info* pDeviceInfo);
    ma_result ma_device_init(ma_context* pContext, const ma_device_config* pConfig, ma_device* pDevice);
    ma_result ma_device_init_ex(const ma_backend backends[], ma_uint32 backendCount, const ma_context_config* pContextConfig, const ma_device_config* pConfig, ma_device* pDevice);
    void ma_device_uninit(ma_device* pDevice);
    void ma_device_set_stop_callback(ma_device* pDevice, ma_stop_proc proc);
    ma_result ma_device_start(ma_device* pDevice);
    ma_result ma_device_stop(ma_device* pDevice);
    ma_bool32 ma_device_is_started(ma_device* pDevice);
    ma_context_config ma_context_config_init(void);
    ma_device_config ma_device_config_init(ma_device_type deviceType);
    ma_decoder_config ma_decoder_config_init(ma_format outputFormat, ma_uint32 outputChannels, ma_uint32 outputSampleRate);

    /**** decoding ****/
    ma_result ma_decoder_init_memory(const void* pData, size_t dataSize, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_memory_wav(const void* pData, size_t dataSize, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_memory_flac(const void* pData, size_t dataSize, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_memory_vorbis(const void* pData, size_t dataSize, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_memory_mp3(const void* pData, size_t dataSize, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_memory_raw(const void* pData, size_t dataSize, const ma_decoder_config* pConfigIn, const ma_decoder_config* pConfigOut, ma_decoder* pDecoder);

    ma_result ma_decoder_init_file(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_wav(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_flac(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_vorbis(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_mp3(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    
    ma_result ma_decoder_uninit(ma_decoder* pDecoder);
    ma_uint64 ma_decoder_get_length_in_pcm_frames(ma_decoder* pDecoder);
    ma_uint64 ma_decoder_read_pcm_frames(ma_decoder* pDecoder, void* pFramesOut, ma_uint64 frameCount);
    ma_result ma_decoder_seek_to_pcm_frame(ma_decoder* pDecoder, ma_uint64 frameIndex);
    ma_result ma_decode_file(const char* pFilePath, ma_decoder_config* pConfig, ma_uint64* pFrameCountOut, void** ppDataOut);
    ma_result ma_decode_memory(const void* pData, size_t dataSize, ma_decoder_config* pConfig, ma_uint64* pFrameCountOut, void** ppDataOut);
    
    /**** format conversion ****/
    /* TODO: add the streaming DSP conversion API */
    void ma_pcm_u8_to_s16(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_u8_to_s24(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_u8_to_s32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_u8_to_f32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s16_to_u8(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s16_to_s24(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s16_to_s32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s16_to_f32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s24_to_u8(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s24_to_s16(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s24_to_s32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s24_to_f32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s32_to_u8(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s32_to_s16(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s32_to_s24(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_s32_to_f32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_f32_to_u8(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_f32_to_s16(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_f32_to_s24(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_f32_to_s32(void* pOut, const void* pIn, ma_uint64 count, ma_dither_mode ditherMode);
    void ma_pcm_convert(void* pOut, ma_format formatOut, const void* pIn, ma_format formatIn, ma_uint64 sampleCount, ma_dither_mode ditherMode);
    void ma_deinterleave_pcm_frames(ma_format format, ma_uint32 channels, ma_uint64 frameCount, const void* pInterleavedPCMFrames, void** ppDeinterleavedPCMFrames);
    void ma_interleave_pcm_frames(ma_format format, ma_uint32 channels, ma_uint64 frameCount, const void** ppDeinterleavedPCMFrames, void* pInterleavedPCMFrames);
    ma_uint64 ma_convert_frames(void* pOut, ma_format formatOut, ma_uint32 channelsOut, ma_uint32 sampleRateOut, const void* pIn, ma_format formatIn, ma_uint32 channelsIn, ma_uint32 sampleRateIn, ma_uint64 frameCount);
    ma_uint64 ma_convert_frames_ex(void* pOut, ma_format formatOut, ma_uint32 channelsOut, ma_uint32 sampleRateOut, ma_channel channelMapOut[MA_MAX_CHANNELS], const void* pIn, ma_format formatIn, ma_uint32 channelsIn, ma_uint32 sampleRateIn, ma_channel channelMapIn[MA_MAX_CHANNELS], ma_uint64 frameCount);

    /**** misc ****/
    const char* ma_get_backend_name(ma_backend backend);
    const char* ma_get_format_name(ma_format format);
    void ma_zero_pcm_frames(void* p, ma_uint32 frameCount, ma_format format, ma_uint32 channels);

    void init_miniaudio(void);
    void ma_device_config_set_params(ma_device_config* config, ma_uint32 sample_rate, ma_uint32 buffer_size_msec, ma_uint32 buffer_size_frames,
       ma_format format, ma_uint32 channels, ma_format capture_format, ma_uint32 capture_channels);

    extern "Python" void internal_data_callback(ma_device* pDevice, void* pOutput, const void* pInput, ma_uint32 frameCount);
    
""")


libraries = []
compiler_args = []
if os.name == "posix":
    libraries = ["m", "pthread", "dl"]
    compiler_args = ["-g1"]


ffibuilder.set_source("_miniaudio", """
    #include <stdint.h>
    #include <stdlib.h>

    #define DR_FLAC_NO_OGG
    #include "miniaudio/dr_flac.h"
    #include "miniaudio/dr_wav.h"
    #include "miniaudio/dr_mp3.h"


    #ifdef _MSC_VER     /* visual c++ currently can't compile in the vorbis lib */
    #define NO_STB_VORBIS
    #endif
    

    #ifndef NO_STB_VORBIS
    #define STB_VORBIS_HEADER_ONLY
    /* #define STB_VORBIS_NO_PUSHDATA_API  */   /*  needed by miniaudio decoding logic  */
    #include "miniaudio/stb_vorbis.c"
    #endif

    #include "miniaudio/miniaudio.h"
    
    /* low-level initialization */
    void init_miniaudio(void);
    
    /* helper function to set some parameters in the ma_device_config struct which couldn't be parsed by cffi directly */
    void ma_device_config_set_params(ma_device_config* config, ma_uint32 sample_rate, ma_uint32 buffer_size_msec, ma_uint32 buffer_size_frames,
       ma_format format, ma_uint32 channels, ma_format capture_format, ma_uint32 capture_channels);

    /* missing protos */
    ma_result ma_decoder_init_file_wav(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_flac(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_vorbis(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    ma_result ma_decoder_init_file_mp3(const char* pFilePath, const ma_decoder_config* pConfig, ma_decoder* pDecoder);
    
""",
                      sources=["miniaudio.c"],
                      include_dirs=[miniaudio_include_dir],
                      libraries=libraries,
                      extra_compile_args=compiler_args)

if __name__ == "__main__":
    ffibuilder.compile(verbose=True)
