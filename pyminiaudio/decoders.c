#define STB_VORBIS_NO_PUSHDATA_API
#include "miniaudio/stb_vorbis.c"

#define DR_FLAC_IMPLEMENTATION
#define DR_FLAC_NO_OGG
#include "miniaudio/dr_flac.h"

#define DR_MP3_IMPLEMENTATION
#include "miniaudio/dr_mp3.h"

#define DR_WAV_IMPLEMENTATION
#include "miniaudio/dr_wav.h"


/* Nothing more to do here; all the decoder source is in their own single source/include file */
