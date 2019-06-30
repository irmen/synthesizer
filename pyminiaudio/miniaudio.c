#include <stdlib.h>
#include <stdint.h>

#ifndef NO_STB_VORBIS
/* #define STB_VORBIS_NO_PUSHDATA_API  */   /*  needed by miniaudio decoding logic  */
#define STB_VORBIS_HEADER_ONLY
#include "miniaudio/stb_vorbis.c"
#endif


#define DR_FLAC_IMPLEMENTATION
#define DR_FLAC_NO_OGG
#include "miniaudio/dr_flac.h"

#define DR_MP3_IMPLEMENTATION
#include "miniaudio/dr_mp3.h"

#define DR_WAV_IMPLEMENTATION
#include "miniaudio/dr_wav.h"

#define MINIAUDIO_IMPLEMENTATION
/* #define MA_NO_DECODING */
#define MA_NO_AAUDIO
#define MA_NO_OPENSL
#define MA_NO_WEBAUDIO
#define MA_NO_JACK
#define MA_PA_MINREQ_PATCH      /* tiny patch to fix a multi second pulseaudio startup delay */
#include "miniaudio/miniaudio.h"


#ifndef NO_STB_VORBIS
#undef STB_VORBIS_HEADER_ONLY		/* this time, do include vorbis implementation */
#include "miniaudio/stb_vorbis.c"
#endif


#ifdef _WIN32
int setenv(const char *name, const char *value, int overwrite)
{
    int errcode = 0;
    if(!overwrite) {
        size_t envsize = 0;
        errcode = getenv_s(&envsize, NULL, 0, name);
        if(errcode || envsize) return errcode;
    }
    return _putenv_s(name, value);
}
#endif

void init_miniaudio(void) {

    #ifndef MA_PA_MINREQ_PATCH
    /*
    This is needed to avoid a huge multi second delay when using PulseAudio (without the minreq value patch)
    It seems to be related to the pa_buffer_attr->minreq value
    See https://freedesktop.org/software/pulseaudio/doxygen/structpa__buffer__attr.html#acdbe30979a50075479ee46c56cc724ee
    and https://github.com/pulseaudio/pulseaudio/blob/4e3a080d7699732be9c522be9a96d851f97fbf11/src/pulse/stream.c#L989
    */
    setenv("PULSE_LATENCY_MSEC", "100", 0);
    #endif
}


void ma_device_config_set_params(ma_device_config* config, ma_uint32 sample_rate, ma_uint32 buffer_size_msec,
  ma_uint32 buffer_size_frames, ma_format format, ma_uint32 channels, ma_format capture_format, ma_uint32 capture_channels, ma_device_id* playback_device_id, ma_device_id* capture_device_id) {
    config->sampleRate = sample_rate;
    config->bufferSizeInFrames = buffer_size_frames;
    config->bufferSizeInMilliseconds = buffer_size_msec;
    config->playback.format = format;
    config->playback.channels = channels;
    config->capture.format = capture_format;
    config->capture.channels = capture_channels;
    config->capture.pDeviceID = capture_device_id;
    config->playback.pDeviceID = playback_device_id;
}


/* Nothing more to do here; all the decoder source is in their own single source/include file */
