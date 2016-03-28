import time
from rhythmbox import Output
from synth import Wavesynth, key_freq, Oscillator
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
    with Output() as out:
        for wave in [synth.square_h, synth.square, synth.sine, synth.triangle, synth.sawtooth, synth.sawtooth_h]:
            print(wave.__name__)
            for note, freq in notes4.items():
                print("   {:f} hz".format(freq))
                sample = wave(freq, duration=0.4)
                sample = synth.to_sample(sample).fadein(0.02)
                out.play_sample(sample)
        print("pulse")
        for note, freq in notes4.items():
            print("   {:f} hz".format(freq))
            sample = synth.pulse(freq, 0.1, duration=0.4)
            sample = synth.to_sample(sample).fadein(0.02)
            out.play_sample(sample)
        print("harmonics (only even)")
        for note, freq in notes3.items():
            print("   {:f} hz".format(freq))
            sample = synth.harmonics(freq, duration=0.4, num_harmonics=5, only_odd=True)
            sample = synth.to_sample(sample).fadein(0.02)
            out.play_sample(sample)
        print("noise")
        sample = synth.white_noise(duration=1.5)
        sample = synth.to_sample(sample).fadein(0.1)
        out.play_sample(sample)


def demo_song():
    synth = Wavesynth()
    notes = {note: key_freq(49+i) for i, note in enumerate(['A', 'A#', 'B', 'C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#'])}
    tempo = 0.3
    def instrument(freq, duration):
        a = synth.harmonics(freq, duration, num_harmonics=4, amplitude=0.8, only_even=True)
        return synth.to_sample(a).envelope(0.05, 0.2, 0.8, 0.5)
    print("Synthesizing tones...")
    quarter_notes = {note: instrument(notes[note], tempo) for note in notes}
    half_notes = {note: instrument(notes[note], tempo*2) for note in notes}
    full_notes = {note: instrument(notes[note], tempo*4) for note in notes}
    song = "A A B. A D. C#.. ;  A A B. A E. D.. ;  A A A. F#.. D C#.. B ;  G G F#.. D E D ; ; "\
        "A A B. A D C#.. ; A A B. A E D. ; A A A. F#.. D C#.. B ; G G F#.. D E D ; ; "
    from pyaudio import PyAudio
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
    s = synth.sine(freq, duration=1)
    plot.plot(s)
    s = synth.triangle(freq, duration=1)
    plot.plot(s)
    s = synth.square(freq, duration=1)
    plot.plot(s)
    s = synth.square_h(freq, duration=1)
    plot.plot(s)
    s = synth.pulse(freq, 0.2, duration=1)
    plot.plot(s)
    plot.show()


def bass_tones():
    synth = Wavesynth()
    with Output() as out:
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
            out.play_sample(s_sin1)


def modulate_amp():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 110
    s1 = synth.triangle(freq, duration=2)
    m = synth.sine(1, duration=2)
    s1 = synth.to_sample(s1, False)
    m = synth.to_sample(m, False).get_frame_array()
    s1.modulate_amp(m)
    plot.plot(s1.get_frame_array())
    plot.show()
    with Output() as out:
        out.play_sample(s1)


def envelope():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 220
    s = synth.triangle(freq, duration=1)
    s = synth.to_sample(s, False)
    s.envelope(0.05, 0.1, 0.6, 0.3)
    plot.plot(s.get_frame_array())
    plot.show()
    with Output() as out:
        out.play_sample(s)


def fm():
    synth = Wavesynth()
    with Output() as out:
        freq = 220
        lfo1 = synth.oscillator.sine(5, amplitude=0.05)
        s1 = synth.sine(freq, duration=3, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1)
        lfo1 = synth.oscillator.sine(6, amplitude=0.1)
        s1 = synth.sine(freq, duration=3, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1)
        lfo1 = synth.oscillator.sine(freq/17, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1)
        lfo1 = synth.oscillator.sine(freq/6, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1)


def oscillator():
    from matplotlib import pyplot as plot
    lfo = Oscillator(1000)
    l2 = lfo.square_h(4)
    plot.subplot(2,1,1)
    plot.plot([next(l2) for _ in range(1000)])
    l3 = lfo.harmonics(4, 8, only_even=True)
    plot.subplot(2,1,2)
    plot.plot([next(l3) for _ in range(1000)])
    plot.show()


if __name__ == "__main__":
    #demo_plot()
    #demo_tones()
    #demo_song()
    #bass_tones()
    #modulate_amp()
    #envelope()
    fm()
    #oscillator()
