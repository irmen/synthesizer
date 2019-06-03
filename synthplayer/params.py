"""
Global parameters for the synthesizer, these are configurable.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

# normal sample parameters are for CD quality, 2-channel (stereo), 16 bit samples.
norm_samplerate = 44100
norm_nchannels = 2
norm_samplewidth = 2

# playback stream buffer size = 1/30 sec, about 6kb worth of data
# smaller = less latency but more overhead
norm_frames_per_chunk = norm_samplerate // 30

# oscillator block size (samples)
norm_osc_blocksize = 512

# should the output sound mixer fade samples to prevent click/pop noise?
# (it wil incur a slight performance hit)
auto_sample_pop_prevention = False
