"""
Global parameters for the synthesizer, these are configurable.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

norm_samplerate = 44100
norm_nchannels = 2
norm_samplewidth = 2
norm_frames_per_chunk = norm_samplerate // 30    # about 6kb worth of data, 1/30 sec
