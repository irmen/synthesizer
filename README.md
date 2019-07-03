[![saythanks](https://img.shields.io/badge/say-thanks-ff69b4.svg)](https://saythanks.io/to/irmen)
[![Latest Version](https://img.shields.io/pypi/v/synthplayer.svg)](https://pypi.python.org/pypi/synthplayer/)

**Software sound synthesizer (FM/PWM oscillators), sound file streaming and conversion, 
and sound playback and mixing engine.**

Pypi: [synthplayer](https://pypi.org/project/synthplayer/)  

*requires Python 3.5 or newer*.


## No sound? Configure the correct output audio device
On some systems, the portaudio system audio library seems to report a wrong 
default output audio device. In this case, you may get an ``IOError``
(describing the problem). You can also get another error (or no sound output at all,
without any errors at all...) If this happens, you can manually configure the output audio device
that should be used:

Either set the ``PY_SYNTHPLAYER_AUDIO_DEVICE`` environment variable to the correct device number,
or set the ``synthplayer.playback.default_audio_device`` parameter at the start of your code.
(The environment variable has priority over the code parameter)

To find the correct device number you can use the ``query_devices`` method or type ``python -m sounddevice``.

# synthplayer.synth

A waveform synthesizer that can generate different wave form samples:
sine, triangle, sawtooth, square, pulse wave, harmonics and white noise.
It also supports Frequency Modulation, Pulse-width modulation, and ADSR envelopes using LFOs.

For efficiency reasons, the oscillators and filters return their waveform values in small
chunks/lists instead of per individual value. When running the synthesizer with pypy the
speedup is remarkable over the older version (that used single value generators).
 

![Synth Waveforms overview](./waveforms.png?raw=true "Overview of the basic waveforms available in the synth")

![Synth GUI screenshot](./screenshot.png?raw=true "Screenshot of the Keyboard GUI")


# synthplayer.playback

Sound playback engine. Supports multiple sound APIs, 
efficient sequential streaming or real-time mixing of shorter sound clips.
The streaming is implemented via Python generators where the main generator essentially produces mixed sample fragments.
These are written to an audio stream of one of the supported audio library backends, in this order:

- [``miniaudio``](https://github.com/irmen/pyminiaudio/)
- [``soundcard``](https://soundcard.readthedocs.io/)
- [``sounddevice``](http://python-sounddevice.readthedocs.io/)
- [``pyaudio``](http://people.csail.mit.edu/hubert/pyaudio/) 
- ``winsound`` (only on Windows, and has very limited capabilities). 

# synthplayer.sample

Contains the Sample class that represents a digitized sound clip.
It provides a set of simple sound manipulation methods such as changing
the amplitude, fading in/out, and format conversions.


# synthplayer.streaming

Provides various classes to stream audio data with.
Uses ffmpeg or oggdec to read/stream many different sound formats.


# Example program: jukebox.box

This is a jukebox like party sound player that allows to prepare a playlist,
fade from a track to the next from the list, and insert random soundbytes for added fun.
The songs are queried from a backend audio file database server program.
 

# Example program: trackmixer

You assemble rhythm samples into bars and patterns, which are then mixed.
Samples have to be in .wav format but can be anything that the Python wave module understands. 
The 'track' files are in a simple .ini format and can be edited with any text editor.
Most of the file should be self explanatory but here are a few tips:

- Song bpm means beats per minute, which translates in how many *bars* are played per minute.
  If you put one kick/bass drum trigger in one bar, it exactly hits the specified number of beats per minute.
- Song ticks means how many *ticks* (or *triggers*) are in one bar. More ticks means more resolution. Nice for fast hi-hats.
- A *bar* is a sequence of instrument *ticks* (or *triggers*) where '.' means nothing is played at that instant,
  and another character such as 'x' means that the sample is played at that instant.
- you can separate bars with whitespace for easier readability
- pattern names are prefixed with ``pattern.`` when writing their section (ini file limitation, you can't nest things)
- patterns can contain one or more bars per instrument (so you can have long and short patterns). However inside
  a pattern every instrument has to have the same number of bars.
  

Here is a very simple example of a track file:

```ini
[paths]
# where to find the sample files
samples = samples/

[samples]
# list your samples here
kick7 = biab_kick_7.wav
snare2 = biab_sn_2.wav
snare10 = biab_sn_10.wav
hihat2 = biab_hat_2.wav
hihat4 = biab_hat_4.wav

[song]
# basic song parameters and pattern sequence
bpm = 128
ticks = 4
patterns = pat1 pat2 pat1 pat2 outro

[pattern.pat1]
hihat2     = x.x. x.x. x.x. x.x.
snare2     = .... x... .... x...
kick7      = x... x... x... x...

[pattern.pat2]
hihat4     = x.x. x.x. x.x. x.x.
snare10    = .... .... x... x...

[pattern.outro]
hihat2     = x.x. x.x. 
hihat4     = .... x...
kick7      = .... x...
```

## invoking the mixer

To simply mix and stream your track file to your speakers use the following command:

``python trackmixer.py mytrack.ini``

To load your track file and start the interactive command line interface:

``python trackmixer.py -i mytrack.ini``

...then type ``help`` to see what commands are available.

A few example tracks are provided, try them out!  (pre-mixed output can be found in the example_mixes folder)

- track1.ini  - a short jungle-ish fragment
- track2.ini  - a somewhat longer classic rhythm loop, I guess it's in 4/4 time
- track3.ini  - an experiment with a few liquid drum'n'bass type patterns

