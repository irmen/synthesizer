"""
GUI For the synthesizer components

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import tkinter as tk
import tkinter.messagebox as tkmsgbox
import math
from synthesizer.synth import Sine, Triangle, Sawtooth, SawtoothH, Square, SquareH, Harmonics, Pulse, WhiteNoise, Linear
from synthesizer.synth import WaveSynth
from synthesizer.sample import Sample, Output


class OscillatorGUI(tk.Frame):
    def __init__(self, master, title, fm_sources=None):
        super().__init__(master)
        oscframe = tk.LabelFrame(self, text=title)
        oscframe.pack(side=tk.LEFT)
        leftframe = tk.Frame(oscframe)
        leftframe.pack(side=tk.LEFT, anchor=tk.N)
        waveforms = ["sine", "triangle", "pulse", "sawtooth", "sawtooth_h", "square", "square_h", "harmonics", "noise", "linear"]
        self.input_waveformtype = tk.StringVar()
        self.input_waveformtype.set("sine")
        for w in waveforms:
            b = tk.Radiobutton(leftframe, text=w, variable=self.input_waveformtype, value=w, command=self.waveform_selected)
            if w in ("harmonics", "noise", "linear"):
                b.configure(state="disabled")
            b.pack(anchor=tk.W)
        rightframe = tk.Frame(oscframe)
        rightframe.pack(side=tk.RIGHT, anchor=tk.N)
        f = tk.LabelFrame(rightframe, text="inputs")
        f.pack(side=tk.TOP)
        # freq, amplitude, phase, bias
        self.input_freq = tk.DoubleVar()
        self.input_freq.set(440.0)
        self.input_amp = tk.DoubleVar()
        self.input_amp.set(0.5)
        self.input_phase = tk.DoubleVar()
        self.input_bias = tk.DoubleVar()
        self.input_pw = tk.DoubleVar()
        self.input_pw.set(0.1)
        self.input_fm = tk.StringVar()
        tk.Label(f, text="freq Hz").grid(row=0, column=0)
        tk.Entry(f, width=10, textvariable=self.input_freq).grid(row=0, column=1)
        tk.Label(f, text="amp").grid(row=1, column=0)
        tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_amp, from_=0, to=1.0, resolution=.01).grid(row=1, column=1)
        self.pw_label = tk.Label(f, text="pulsewidth", state="disabled")
        self.pw_label.grid(row=2, column=0)
        self.pw_label.grid_remove()
        self.pw_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_pw, from_=.001, to=.999, resolution=.001, state="disabled")
        self.pw_slider.grid(row=2, column=1)
        self.pw_slider.grid_remove()
        tk.Label(f, text="phase").grid(row=3, column=0)
        tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_phase, from_=0, to=1.0, resolution=.01).grid(row=3, column=1)
        tk.Label(f, text="bias").grid(row=4, column=0)
        tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_bias, from_=-1, to=1, resolution=.01).grid(row=4, column=1)
        if fm_sources:
            tk.Label(f, text="FM").grid(row=5, column=0)
            values = ["<none>"]
            values.extend(fm_sources)
            self.optionMenuWidget = tk.OptionMenu(f, self.input_fm, *values).grid(row=5, column=1)
            self.input_fm.set("<none>")
        tk.Button(rightframe, text="Play", command=lambda: master.do_play(self)).pack(side=tk.RIGHT, pady=10)
        tk.Button(rightframe, text="Plot", command=lambda: master.do_plot(self)).pack(side=tk.RIGHT, pady=10)
        self.pack(side=tk.LEFT, anchor=tk.N, padx=10, pady=10)

    def waveform_selected(self):
        wf = self.input_waveformtype.get()
        if wf == "pulse":
            self.pw_slider.grid()
            self.pw_label.grid()
        else:
            self.pw_slider.grid_remove()
            self.pw_label.grid_remove()


class SynthGUI(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.synth = WaveSynth()
        self.master.title("Synthesizer")
        num_oscillators = 5
        self.oscillators = []
        fm_sources = []
        for n in range(num_oscillators):
            self.oscillators.append(OscillatorGUI(self, "Oscillator "+str(n+1), fm_sources=fm_sources))
            fm_sources.append("osc "+str(n+1))
        self.pack()

    def create_osc(self, from_gui, all_oscillators):
        oscs = {
            "sine": Sine,
            "triangle": Triangle,
            "pulse": Pulse,
            "sawtooth": Sawtooth,
            "sawtooth_h": SawtoothH,
            "square": Square,
            "square_h": SquareH,
            "harmonics": Harmonics,
            "noise": WhiteNoise,
            "linear": Linear
            }
        waveform = from_gui.input_waveformtype.get()
        freq = from_gui.input_freq.get()
        amp = from_gui.input_amp.get()
        phase = from_gui.input_phase.get()*math.pi*2
        bias = from_gui.input_bias.get()
        pw = from_gui.input_pw.get()
        fm_choice = from_gui.input_fm.get()
        if fm_choice in (None, "", "<none>"):
            fm = None
        elif fm_choice.startswith("osc"):
            osc_num = int(fm_choice.split()[1])
            fm = self.create_osc(all_oscillators[osc_num-1], all_oscillators)
        else:
            raise ValueError("invalid fm choice")
        o = oscs[waveform]
        if waveform == "pulse":
            o = o(frequency=freq, amplitude=amp, phase=phase, bias=bias, pulsewidth=pw, fm_lfo=fm, samplerate=self.synth.samplerate)
        else:
            o = o(frequency=freq, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)
        return o

    def do_play(self, osc):
        o = self.create_osc(osc, all_oscillators=self.oscillators)
        o = iter(o)
        scale = 2**(8*self.synth.samplewidth-1)
        frames = [int(next(o)*scale) for _ in range(self.synth.samplerate)]
        sample = Sample.from_array(frames, self.synth.samplerate, 1).fadein(0.05).fadeout(0.1)
        with Output(self.synth.samplerate, self.synth.samplewidth, 1) as out:
            out.play_sample(sample, async=True)

    def do_plot(self, osc):
        o = self.create_osc(osc, all_oscillators=self.oscillators)
        o = iter(o)
        frames = [next(o) for _ in range(self.synth.samplerate)]
        try:
            import matplotlib.pyplot as plot
        except ImportError:
            tkmsgbox.showerror("matplotlib not installed", "To plot things, you need to have matplotlib installed")
        plot.figure(figsize=(16, 4))
        plot.title("Waveform")
        plot.plot(frames)
        plot.show()


if __name__ == "__main__":
    root = tk.Tk()
    app = SynthGUI(master=root)
    app.mainloop()
