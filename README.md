# rhythmbox

Sample mixer and sequencer, think a simple [Roland TR-909](https://en.wikipedia.org/wiki/Roland_TR-909).
It can mix the patterns into a single output file, but can also stream the mix.
It provides a command line interface where you can edit the song and patterns,
play samples and individual patterns, and mix or stream it by entering simple commands.

Note: *rhythmbox requires Python 3.x.*


The streaming is implemented via Python generators where the main generator essentially produces mixed sample fragments.
They are written to a [pyaudio](http://people.csail.mit.edu/hubert/pyaudio/) audiostream to let you hear the rhythm mix
as it is produced in real time.

Apart from [pyaudio](http://people.csail.mit.edu/hubert/pyaudio/) which is used for audio output, no other custom libraries are required.
On windows you can even run it without having pyaudio installed (it will use winsound, but you won't be able to stream).

## how it works

You assemble rhythm samples into bars and patterns, which are then mixed.
Samples have to be in .wav format but can be anything that the Python wave module understands. 
The 'track' files are in a simple .ini format and can be edited with any text editor.

Here is a very simple example of a track file:

```ini
[paths]
# where to find the sample files and where to write output mix file
samples = samples/
output = ./

[instruments]
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

## invoking rhythmbox

To simply mix and stream your track file to your speakers use the following command:

``python3 rhythmbox.py mytrack.ini``

To load your track file and start the interactive command line interface:

``python3 rhythmbox.py -i mytrack.ini``

...then type ``help`` to see what commands are available.


