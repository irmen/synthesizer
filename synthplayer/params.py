"""
Global parameters for the synthesizer, these are configurable.

Written by Irmen de Jong (irmen@razorvine.net) - License: GNU LGPL 3.
"""

norm_samplerate = 44100       # CD quality
norm_nchannels = 2            # two channel stereo
norm_samplewidth = 2          # samples are 2 bytes = 16 bits
norm_frames_per_chunk = norm_samplerate // 30    # about 6kb worth of data, 1/30 sec
mixer_pop_prevention = True   # should the real-time mixer use sound click/pop prevention?
