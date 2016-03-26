import time
from pyaudio import PyAudio
from synth import Wavesynth, key_freq
from collections import OrderedDict

# some note frequencies for octaves 1 to 7
octave_notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
notes1 = OrderedDict((note, key_freq(4+i)) for i, note in enumerate(octave_notes))
notes2 = OrderedDict((note, key_freq(16+i)) for i, note in enumerate(octave_notes))
notes3 = OrderedDict((note, key_freq(28+i)) for i, note in enumerate(octave_notes))
notes4 = OrderedDict((note, key_freq(40+i)) for i, note in enumerate(octave_notes))
notes5 = OrderedDict((note, key_freq(52+i)) for i, note in enumerate(octave_notes))
notes6 = OrderedDict((note, key_freq(64+i)) for i, note in enumerate(octave_notes))
notes7 = OrderedDict((note, key_freq(76+i)) for i, note in enumerate(octave_notes))


def demo_tones():
    synth = Wavesynth()
    audio = PyAudio()
    stream = audio.open(format=audio.get_format_from_width(synth.samplewidth),
                        channels=1, rate=synth.samplerate, output=True)
    for wave in [synth.squareh, synth.square, synth.sine, synth.triangle, synth.sawtooth]:
        print(wave.__name__)
        for note, freq in notes4.items():
            print("   {:f} hz".format(freq))
            sample = wave(freq, duration=0.4)
            sample = synth.to_sample(sample).fadeout(0.1).fadein(0.02)
            sample.write_frames(stream)
    print("pulse")
    for note, freq in notes4.items():
        print("   {:f} hz".format(freq))
        sample = synth.pulse(freq, 0.1, duration=0.4)
        sample = synth.to_sample(sample).fadeout(0.1).fadein(0.02)
        sample.write_frames(stream)
    print("noise")
    sample = synth.white_noise(duration=1.5)
    sample = synth.to_sample(sample).fadeout(0.5).fadein(0.1)
    sample.write_frames(stream)
    stream.close()


def demo_song():
    synth = Wavesynth()
    print("Synthesizing tones...")
    notes = {note: key_freq(49+i) for i, note in enumerate(['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#'])}
    tempo = 0.3
    quarter_notes = {note: synth.to_sample(synth.triangle(notes[note], tempo)).fadeout(0.1).fadein(0.02) for note in notes}
    half_notes = {note: synth.to_sample(synth.triangle(notes[note], tempo*2)).fadeout(0.1).fadein(0.02) for note in notes}
    full_notes = {note: synth.to_sample(synth.triangle(notes[note], tempo*4)).fadeout(0.1).fadein(0.02) for note in notes}
    song = "A A B. A D. C#.. ;  A A B. A E. D.. ;  A A A. F#.. D C#.. B ;  G G F#.. D E D ; ; "\
        "A A B. A D C#.. ; A A B. A E D. ; A A A. F#.. D C#.. B ; G G F#.. D E D ; ; "
    audio = PyAudio()
    stream = audio.open(format=audio.get_format_from_width(synth.samplewidth),
                        channels=1, rate=synth.samplerate, output=True)
    for note in song.split():
        if note == ";":
            filler = b"\0"*sample.sampwidth*sample.nchannels*stream.get_write_available()
            stream.write(filler)
            time.sleep(stream.get_output_latency()+stream.get_input_latency()+0.001)
            print()
            time.sleep(tempo*2)
            continue
        print(note, end="  ", flush=True)
        if note.endswith(".."):
            sample = full_notes[note[:-2]]
        elif note.endswith("."):
            sample = half_notes[note[:-1]]
        else:
            sample = quarter_notes[note]
        sample.write_frames(stream)
    stream.close()
    print()


def demo_plot():
    from matplotlib import pyplot as plot
    synth = Wavesynth(samplerate=1000)
    freq = 4
    s = synth.sawtooth(freq, duration=1)
    plot.plot(s)
    # s = synth.sawtooth(freq, duration=1, phase=5)
    # plot.plot(s)
    s = synth.sine(freq, duration=1)
    plot.plot(s)
    # s = synth.sine(freq, duration=1, phase=0.1)
    # plot.plot(s)
    s = synth.triangle(freq, duration=1)
    plot.plot(s)
    # s = synth.triangle(freq, duration=1, phase=0.25)
    # plot.plot(s)
    s = synth.square(freq, duration=1)
    plot.plot(s)
    # s = synth.square(freq, duration=1, phase=0.25)
    # plot.plot(s)
    s = synth.squareh(freq, duration=1)
    plot.plot(s)
    # s = synth.squareh(freq, duration=1, phase=0.5)
    # plot.plot(s)
    s = synth.pulse(freq, 0.2, duration=1)
    plot.plot(s)
    # s = synth.pulse(freq, 0.2, duration=1, phase=0.5)
    # plot.plot(s)
    plot.show()


def bass_tones():
    synth = Wavesynth()
    audio = PyAudio()
    stream = audio.open(format=audio.get_format_from_width(synth.samplewidth),
                        channels=1, rate=synth.samplerate, output=True)
    for note, freq in notes2.items():
        print(note, freq)
        duration = 2
        a_sin1 = synth.triangle(freq, duration=duration, amplitude=0.2)
        a_sin2 = synth.sine(freq*1.03, duration=duration, amplitude=0.4)
        a_sin3 = synth.sine(freq*0.95, duration=duration, amplitude=0.3)
        s_sin1 = synth.to_sample(a_sin1)
        s_sin2 = synth.to_sample(a_sin2)
        s_sin3 = synth.to_sample(a_sin3)
        s_sin1.mix(s_sin2).mix(s_sin3)
        s_sin1.amplify_max().fadeout(0.2).fadein(0.1)
        s_sin1.write_frames(stream)
    stream.close()


if __name__ == "__main__":
    # demo_plot()
    # demo_tones()
    demo_song()
    # bass_tones()

