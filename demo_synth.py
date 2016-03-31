import time
from rhythmbox import Output, Sample
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
                out.play_sample(sample, async=False)
        print("pulse")
        for note, freq in notes4.items():
            print("   {:f} hz".format(freq))
            sample = synth.pulse(freq, 0.1, duration=0.4)
            sample = synth.to_sample(sample).fadein(0.02)
            out.play_sample(sample, async=False)
        print("harmonics (only even)")
        for note, freq in notes3.items():
            print("   {:f} hz".format(freq))
            sample = synth.harmonics(freq, duration=0.4, num_harmonics=5, only_odd=True)
            sample = synth.to_sample(sample).fadein(0.02)
            out.play_sample(sample, async=False)
        print("noise")
        sample = synth.white_noise(duration=1.5)
        sample = synth.to_sample(sample).fadein(0.1)
        out.play_sample(sample, async=False)


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
    with Output(synth.samplerate, synth.samplewidth, 1) as out:
        for note in song.split():
            if note == ";":
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
            out.play_sample(sample, async=False)
        print()


def demo_plot():
    from matplotlib import pyplot as plot
    plot.title("Various waveforms")
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


def modulate_amp():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 110
    s1 = synth.triangle(freq, duration=2)
    m = synth.sine(2, duration=2, amplitude=0.4, bias=0.5)
    s1 = synth.to_sample(s1, False)
    m = synth.to_sample(m, False).get_frame_array()
    s1.modulate_amp(m)
    plot.title("Amplitude modulation by another waveform (not an envelope)")
    plot.plot(s1.get_frame_array())
    plot.show()
    with Output() as out:
        out.play_sample(s1, async=False)


def envelope():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 220
    s = synth.triangle(freq, duration=1)
    s = synth.to_sample(s, False)
    s.envelope(0.05, 0.1, 0.2, 0.4)
    plot.title("ADSR envelope")
    plot.plot(s.get_frame_array())
    plot.show()
    with Output() as out:
        out.play_sample(s, async=False)


def fm():
    synth = Wavesynth(samplerate=8000)
    from matplotlib import pyplot as plot
    freq = 2000
    lfo1 = synth.oscillator.sine(1, amplitude=0.4)
    s1 = synth.sine(freq, duration=3, fmlfo=lfo1)
    plot.title("Spectrogram")
    plot.ylabel("Freq")
    plot.xlabel("Time")
    plot.specgram(s1, Fs=synth.samplerate, noverlap=90, cmap=plot.cm.gist_heat)
    plot.show()
    with Output() as out:
        synth = Wavesynth()
        freq = 440
        lfo1 = synth.oscillator.sine(1, amplitude=0.2)
        s1 = synth.sine(freq, duration=3, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(freq/17, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(freq/6, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        out.play_sample(s1, async=False)


def pwm():
    from matplotlib import pyplot as plot
    synth = Wavesynth(samplerate=1000)
    pwlfo = synth.oscillator.sine(0.2, amplitude=0.9)
    s1 = synth.pulse(10, width=0.49, amplitude=0.6, duration=4, pwlfo=pwlfo)
    plot.figure(figsize=(16, 4))
    plot.title("Pulse width modulation")
    plot.plot(s1)
    plot.show()
    with Output() as out:
        synth = Wavesynth()
        freq = 110
        lfo2 = synth.oscillator.sine(0.3, amplitude=0.9)
        s1 = synth.pulse(freq, width=0.49, amplitude=0.5, duration=4, fmlfo=None, pwlfo=lfo2)
        s1 = synth.to_sample(s1)
        out.play_sample(s1, async=False)


def oscillator():
    from matplotlib import pyplot as plot
    lfo = Oscillator(1000)
    l2 = lfo.square_h(4)
    plot.subplot(2, 1, 1)
    plot.title("Square from harmonics")
    plot.plot([next(l2) for _ in range(1000)])
    l3 = lfo.harmonics(4, 8, only_even=True)
    plot.subplot(2, 1, 2)
    plot.title("Even harmonics")
    plot.plot([next(l3) for _ in range(1000)])
    plot.show()


def test_lfo_fmfix():
    from matplotlib import pyplot as plot
    samplerate = 1000
    duration = 1
    frequency = 20
    bias = 100
    amplitude = 100
    phase = 0.4
    lfo = Oscillator(samplerate)
    fm = lfo.sine(2, amplitude=0.9)
    s1_osc = lfo.sawtooth(frequency, amplitude=amplitude, phase=phase, bias=bias, fmlfo=fm)
    s_orig = []
    for _ in range(samplerate*duration):
        s_orig.append(next(s1_osc))
    plot.figure(figsize=(20, 5))
    plot.ylabel("Sine FM orig. Gen.")
    plot.plot(s_orig)
    plot.show()
    # play some sound as well to hear it:
    samplerate = 22050
    lfo = Oscillator(samplerate)
    duration = 10
    # fm0 = lfo.sine(1.5, amplitude=0.4, bias=0.5)
    # fm = lfo.sine(440/12, amplitude=1, fmlfo=fm0)
    # fm = lfo.envelope(fm, 0.5, 0.5, 0.5, 0.2, 0.5, cycle=True)
    duration = 4
    fm = lfo.sine(1.5, amplitude=0.8)
    s = lfo.sawtooth(440, amplitude=32000, fmlfo=fm)
    with Output(samplerate, 2, 1) as out:
        import array
        a = array.array('h', [int(next(s)) for _ in range(samplerate*duration)])
        smpl = Sample.from_array(a, samplerate, 1).fadeout(1)
        out.play_sample(smpl, async=False)


def sawtooth2():
    from matplotlib import pyplot as plot
    samplerate = 1000
    duration = 1
    frequency = 20
    bias = 100
    amplitude = 100
    phase = 0.9
    lfo = Oscillator(samplerate)
    fm = lfo.sine(2, amplitude=0.9)
    w1_osc = lfo.sawtooth(frequency, amplitude=amplitude, phase=phase, bias=bias, fmlfo=fm)
    fm = None
    w2_osc = lfo.sawtooth(frequency, amplitude=amplitude, phase=phase, bias=bias, fmlfo=fm)
    w_orig = []
    for _ in range(samplerate*duration):
        w_orig.append(next(w1_osc))
    plot.figure(figsize=(16, 8))
    plot.subplot(211)
    plot.plot(w_orig)
    w_orig = []
    for _ in range(samplerate*duration):
        w_orig.append(next(w2_osc))
    plot.subplot(212)
    plot.plot(w_orig)
    plot.show()


def bias():
    from matplotlib import pyplot as plot
    synth = Wavesynth(samplerate=1000)
    w1 = synth.sine(2, 4, 0.02, bias=0.1)
    w2 = synth.triangle(2, 4, 0.02, bias=0.2)
    w3 = synth.pulse(2, 0.45, 4, 0.02, bias=0.3)
    w4 = synth.harmonics(2, 4, 7, 0.02, bias=0.4)
    w5 = synth.sawtooth(2, 4, 0.02, bias=0.5)
    w6 = synth.sawtooth_h(2, 4, 7, 0.02, bias=0.6)
    w7 = synth.square(2, 4, 0.02, bias=0.7)
    w8 = synth.square_h(2, 4, 7, 0.02, bias=0.8)
    w9 = synth.white_noise(4, amplitude=0.02, bias=0.9)
    plot.plot(w1)
    plot.plot(w2)
    plot.plot(w3)
    plot.plot(w4)
    plot.plot(w5)
    plot.plot(w6)
    plot.plot(w7)
    plot.plot(w8)
    plot.plot(w9)
    plot.title("All waveforms biased to levels above zero")
    plot.show()


def lfo_envelope():
    synth = Wavesynth(samplerate=100)
    lfo = synth.oscillator.constant(bias=1000)
    lfo = synth.oscillator.envelope(lfo, 2, 1, 4, 0.3, 2, stop_at_end=True)
    from matplotlib import pyplot as plot
    plot.title("LFO Envelope")
    plot.plot(list(lfo))
    plot.show()


if __name__ == "__main__":
    # demo_plot()
    # demo_tones()
    # demo_song()
    # modulate_amp()
    # envelope()
    # fm()
    # pwm()
    # oscillator()
    test_lfo_fmfix()
    # sawtooth2()
    # bias()
    # lfo_envelope()

