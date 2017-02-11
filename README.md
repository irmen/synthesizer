[![saythanks](https://img.shields.io/badge/say-thanks-ff69b4.svg)](https://saythanks.io/to/irmen)

# synthesizer.mixer and synthesizer.sample

Sample mixer and sequencer, think a simple [Roland TR-909](https://en.wikipedia.org/wiki/Roland_TR-909).
It can mix the patterns into a single output file, but can also stream the mix.
It provides a command line interface where you can edit the song and patterns,
play samples and individual patterns, and mix or stream it by entering simple commands.

Note: *requires Python 3.x.*


The streaming is implemented via Python generators where the main generator essentially produces mixed sample fragments.
These are written to an audio stream of one of the supported audio libraries.
Libraries supported are: [``sounddevice``](http://python-sounddevice.readthedocs.io/),
[``pyaudio``](http://people.csail.mit.edu/hubert/pyaudio/) and ``winsound`` (in this order). 
``winsound`` cannot stream audio however so not everything works with this one.

# synthesizer.synth

There's also a waveform synthesizer that can generate different wave form samples:
sine, triangle, sawtooth, square, pulse wave, harmonics and white noise.
It also supports Frequency Modulation, Pulse-width modulation, and ADSR envelopes using LFOs.

![Synth GUI screenshot](./screenshot.png?raw=true "Screenshot of the Synth GUI")

# jukebox.box

This is a jukebox like party sound player that allows to prepare a playlist,
fade from a track to the next from the list, and insert random soundbytes for added fun.
The songs are queried from a backend audio file database server program.
 

## how the track mixer works

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

``python3 trackmixer.py mytrack.ini``

To load your track file and start the interactive command line interface:

``python3 trackmixer.py -i mytrack.ini``

...then type ``help`` to see what commands are available.

A few example tracks are provided, try them out!  (pre-mixed output can be found in the example_mixes folder)

- track1.ini  - a short jungle-ish fragment
- track2.ini  - a somewhat longer classic rhythm loop, I guess it's in 4/4 time
- track3.ini  - an experiment with a few liquid drum'n'bass type patterns

