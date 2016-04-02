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
    with Output(nchannels=1) as out:
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
            sample = synth.pulse(freq, duration=0.4, pulsewidth=0.1)
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
    s = synth.pulse(freq, duration=1, pulsewidth=0.2)
    plot.plot(s)
    plot.show()


def modulate_amp():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 220
    s1 = synth.triangle(freq, duration=2)
    m = synth.sine(2, duration=2, amplitude=0.4, bias=0.5)
    s1 = synth.to_sample(s1, False)
    m = synth.to_sample(m, False).get_frame_array()
    s1.modulate_amp(m)
    plot.title("Amplitude modulation by another waveform (not an envelope)")
    plot.plot(s1.get_frame_array())
    plot.show()
    with Output(nchannels=1) as out:
        out.play_sample(s1, async=False)


def envelope():
    from matplotlib import pyplot as plot
    synth = Wavesynth()
    freq = 440
    s = synth.triangle(freq, duration=1)
    s = synth.to_sample(s, False)
    s.envelope(0.05, 0.1, 0.2, 0.4)
    plot.title("ADSR envelope")
    plot.plot(s.get_frame_array())
    plot.show()
    with Output(nchannels=1) as out:
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
    with Output(nchannels=1, samplerate=22050) as out:
        synth = Wavesynth(samplerate=22050)
        freq = 440
        lfo1 = synth.oscillator.linear(5)
        lfo1 = synth.oscillator.envelope(lfo1, 1, 0.5, 0.5, 0.5, 1)
        s1 = synth.sine(freq, duration=3, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all = s1.copy()
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(1, amplitude=0.2)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all.join(s1)
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(freq/17, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all.join(s1)
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(freq/6, amplitude=0.5)
        s1 = synth.sine(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all.join(s1)
        out.play_sample(s1, async=False)
        lfo1 = synth.oscillator.sine(1, amplitude=0.4)
        s1 = synth.triangle(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all.join(s1)
        out.play_sample(s1, async=False)
        freq = 440*2
        lfo1 = synth.oscillator.sine(freq/80, amplitude=0.4)
        s1 = synth.triangle(freq, duration=2, fmlfo=lfo1)
        s1 = synth.to_sample(s1)
        s_all.join(s1)
        out.play_sample(s1, async=False)
        # s_all.write_wav("fmtestall.wav")


def pwm():
    from matplotlib import pyplot as plot
    synth = Wavesynth(samplerate=1000)
    pwmlfo = synth.oscillator.sine(0.2, amplitude=0.25, bias=0.25)
    s1 = synth.pulse(4, amplitude=0.6, duration=20, pwmlfo=pwmlfo)
    plot.figure(figsize=(16, 4))
    plot.title("Pulse width modulation")
    plot.plot(s1)
    plot.show()
    with Output(nchannels=1) as out:
        synth = Wavesynth()
        lfo2 = synth.oscillator.sine(0.2, amplitude=0.48, bias=0.5)
        s1 = synth.pulse(440/6, amplitude=0.5, duration=6, fmlfo=None, pwmlfo=lfo2)
        s1 = synth.to_sample(s1)
        out.play_sample(s1, async=False)
        # s1.write_wav("pwmtest.wav")


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


def bias():
    from matplotlib import pyplot as plot
    synth = Wavesynth(samplerate=1000)
    w1 = synth.sine(2, 4, 0.02, bias=0.1)
    w2 = synth.triangle(2, 4, 0.02, bias=0.2)
    w3 = synth.pulse(2, 4, 0.02, bias=0.3, pulsewidth=0.45)
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
    lfo = synth.oscillator.linear(1000)
    lfo = synth.oscillator.envelope(lfo, 2, 1, 4, 0.3, 2, stop_at_end=True)
    from matplotlib import pyplot as plot
    plot.title("LFO Envelope")
    plot.plot(list(lfo))
    plot.show()


def a440():
    synth = Wavesynth()
    with Output(nchannels=1) as out:
        a440 = synth.sine(440, duration=4)
        a440 = synth.to_sample(a440)
        out.play_sample(a440, async=False)


def echo():
    # @TODO this echo is still based on the Sample not on the LFO's
    synth = Wavesynth(samplerate=22050)
    lfo = synth.oscillator.linear(1, -0.0001)
    s = synth.pulse(220, .5, fmlfo=lfo)
    s = synth.to_sample(s).fadeout(.2)
    with Output(s.samplerate, s.samplewidth, s.nchannels) as out:
        e = s.copy().echo(1, 4, 0.5, 0.4)   # echo
        out.play_sample(e, async=False)
        e = s.copy().echo(1, 15, 0.1, 0.6)    # reverberation
        out.play_sample(e, async=False)


if __name__ == "__main__":
    echo()
    raise SystemExit
    demo_plot()
    a440()
    demo_tones()
    demo_song()
    modulate_amp()
    envelope()
    pwm()
    fm()
    oscillator()
    bias()
    lfo_envelope()
