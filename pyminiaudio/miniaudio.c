/* #define STB_VORBIS_NO_PUSHDATA_API  */   /*  needed by miniaudio decoding logic  */
#include "miniaudio/stb_vorbis.c"

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
#include "miniaudio/miniaudio.h"


/* Nothing more to do here; all the decoder source is in their own single source/include file */
