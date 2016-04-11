"""
GUI For the synthesizer components, including a piano keyboard.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import platform
import tkinter as tk
from synthesizer.synth import Sine, Triangle, Sawtooth, SawtoothH, Square, SquareH, Harmonics, Pulse, WhiteNoise, Linear
from synthesizer.synth import WaveSynth, note_freq, MixingFilter
from synthesizer.sample import Sample, Output
try:
    import matplotlib
    matplotlib.use("tkagg")
    import matplotlib.pyplot as plot
except ImportError:
    plot = None
if platform.system() == "Darwin":
    print("Sorry but the piano keyboard buttons are messed up on OSX due to not being able to resize buttons...")   # @todo fix that


class OscillatorGUI(tk.Frame):
    def __init__(self, master, gui, title, fm_sources=None, pwm_sources=None):
        super().__init__(master)
        self._title = title
        self.oscframe = tk.LabelFrame(self, text=title)
        self.oscframe.pack(side=tk.LEFT)
        leftframe = tk.Frame(self.oscframe)
        leftframe.pack(side=tk.LEFT, anchor=tk.N)
        waveforms = ["sine", "triangle", "pulse", "sawtooth", "sawtooth_h", "square", "square_h", "harmonics", "noise", "linear"]
        self.input_waveformtype = tk.StringVar()
        self.input_waveformtype.set("sine")
        for w in waveforms:
            b = tk.Radiobutton(leftframe, text=w, variable=self.input_waveformtype, value=w, command=self.waveform_selected)
            if w in ("harmonics", "noise", "linear"):
                b.configure(state="disabled")
            b.pack(anchor=tk.W)
        rightframe = tk.Frame(self.oscframe)
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
        self.input_pwm = tk.StringVar()
        tk.Label(f, text="freq Hz").grid(row=0, column=0)
        tk.Entry(f, width=10, textvariable=self.input_freq).grid(row=0, column=1)
        tk.Label(f, text="amp").grid(row=1, column=0)
        tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_amp, from_=0, to=1.0, resolution=.01).grid(row=1, column=1)
        self.pw_label = tk.Label(f, text="pulsewidth")
        self.pw_label.grid(row=2, column=0)
        self.pw_label.grid_remove()
        self.pw_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_pw, from_=.001, to=.999, resolution=.001)
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
            menu = tk.OptionMenu(f, self.input_fm, *values)
            menu["width"] = 10
            menu.grid(row=5, column=1)
            self.input_fm.set("<none>")
        if pwm_sources:
            self.pwm_label = tk.Label(f, text="PWM")
            self.pwm_label.grid(row=6, column=0)
            self.pwm_label.grid_remove()
            values = ["<none>"]
            values.extend(pwm_sources)
            self.pwm_select = tk.OptionMenu(f, self.input_pwm, *values, command=self.pwm_selected)
            self.pwm_select["width"] = 10
            self.pwm_select.grid(row=6, column=1)
            self.pwm_select.grid_remove()
            self.input_pwm.set("<none>")
        tk.Button(rightframe, text="Play", command=lambda: gui.do_play(self)).pack(side=tk.RIGHT, pady=10)
        tk.Button(rightframe, text="Plot", command=lambda: gui.do_plot(self)).pack(side=tk.RIGHT, pady=10)
        self.pack(side=tk.LEFT, anchor=tk.N, padx=10, pady=10)

    def set_title_status(self, status):
        title = self._title
        if status:
            title = "{} - [{}]".format(self._title, status)
        self.oscframe["text"] = title

    def waveform_selected(self, *args):
        wf = self.input_waveformtype.get()
        if wf == "pulse":
            self.pw_label.grid()
            self.pw_slider.grid()
            if hasattr(self, "pwm_label"):
                self.pwm_label.grid()
                self.pwm_select.grid()
        else:
            self.pw_label.grid_remove()
            self.pw_slider.grid_remove()
            if hasattr(self, "pwm_label"):
                self.pwm_label.grid_remove()
                self.pwm_select.grid_remove()

    def pwm_selected(self, *args):
        if self.input_pwm.get() != "<none>":
            self.pw_label.grid_remove()
            self.pw_slider.grid_remove()
        else:
            self.pw_label.grid()
            self.pw_slider.grid()


class PianoKeyboard(tk.Frame):
    # XXX the keyboard buttons are all wrong on OSX because they can't be resized/styled there... :(
    def __init__(self, master, gui):
        super().__init__(master)
        black_keys = tk.Frame(self)
        white_keys = tk.Frame(self)
        num_octaves = 3
        first_octave = 3
        for key_nr, key in enumerate((["C#", "D#", None, "F#", "G#", "A#", None]*num_octaves)[:-1]):
            octave = first_octave+(key_nr+2)//7
            def key_pressed(event, note=key, octave=octave):
                gui.pressed(event, note, octave, False)
            def key_released(event, note=key, octave=octave):
                gui.pressed(event, note, octave, True)
            if key:
                b = tk.Button(black_keys, bg='black', fg='lightgray', width=2, height=3, text=key, relief=tk.RAISED, borderwidth=2)
                b.bind("<ButtonPress-1>", key_pressed)
                b.bind("<ButtonRelease-1>", key_released)
                b.pack(side=tk.LEFT, padx="5p")
            else:
                tk.Button(black_keys, width=2, height=3, text="", relief=tk.FLAT, borderwidth=2, state="disabled").pack(side=tk.LEFT, padx="5p")
        black_keys.pack(side=tk.TOP, anchor=tk.W, padx="13p")
        for key_nr, key in enumerate("CDEFGAB"*num_octaves):
            octave = first_octave+(key_nr+2)//7
            def key_pressed(event, note=key, octave=octave):
                gui.pressed(event, note, octave, False)
            def key_released(event, note=key, octave=octave):
                gui.pressed(event, note, octave, True)
            b = tk.Button(white_keys, bg='white', fg='gray', width=4, height=4, text=key, relief=tk.RAISED, borderwidth=2)
            b.bind("<ButtonPress-1>", key_pressed)
            b.bind("<ButtonRelease-1>", key_released)
            b.pack(side=tk.LEFT)
        white_keys.pack(side=tk.TOP, anchor=tk.W, pady=(0, 10))


class SynthGUI(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.synth = WaveSynth(samplewidth=2)
        self.master.title("Synthesizer")
        tk.Label(master, text="This shows a few of the possible oscillators and how they can be combined.").pack(side=tk.TOP)
        self.osc_frame = tk.Frame(self)
        self.piano_frame = tk.Frame(self)
        f = tk.Frame(self.osc_frame)
        tk.Button(f, text="+ OSC -->", command=self.add_osc_to_gui).pack()
        tk.Label(f, text="To speaker:").pack(pady=10)
        self.to_speaker_lb = tk.Listbox(f, width=8, height=6, selectmode=tk.MULTIPLE, exportselection=0)
        self.to_speaker_lb.pack()
        f.pack(side=tk.RIGHT)
        self.oscillators = []
        self.add_osc_to_gui()
        self.add_osc_to_gui()
        self.add_osc_to_gui()
        self.piano = PianoKeyboard(self.piano_frame, self)
        self.piano.pack(side=tk.BOTTOM)
        self.osc_frame.pack(side=tk.TOP, padx=10)
        self.piano_frame.pack(side=tk.TOP)
        self.statusbar = tk.Label(self, text="<status>", relief=tk.RIDGE)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.pack()

    def add_osc_to_gui(self):
        osc_nr = len(self.oscillators)
        fm_sources = ["osc "+str(n+1) for n in range(osc_nr)]
        osc_pane = OscillatorGUI(self.osc_frame, self, "Oscillator "+str(osc_nr+1), fm_sources=fm_sources, pwm_sources=fm_sources)
        self.oscillators.append(osc_pane)
        self.to_speaker_lb.insert(tk.END, "osc "+str(osc_nr+1))

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
        phase = from_gui.input_phase.get()
        bias = from_gui.input_bias.get()
        pw = from_gui.input_pw.get()
        fm_choice = from_gui.input_fm.get()
        pwm_choice = from_gui.input_pwm.get()
        if fm_choice in (None, "", "<none>"):
            fm = None
        elif fm_choice.startswith("osc"):
            osc_num = int(fm_choice.split()[1])
            fm = self.create_osc(all_oscillators[osc_num-1], all_oscillators)
        else:
            raise ValueError("invalid fm choice")
        if pwm_choice in (None, "", "<none>"):
            pwm = None
        elif pwm_choice.startswith("osc"):
            osc_num = int(pwm_choice.split()[1])
            pwm = self.create_osc(all_oscillators[osc_num-1], all_oscillators)
        else:
            raise ValueError("invalid fm choice")
        o = oscs[waveform]
        if waveform == "pulse":
            o = o(frequency=freq, amplitude=amp, phase=phase, bias=bias, pulsewidth=pw, fm_lfo=fm, pwm_lfo=pwm, samplerate=self.synth.samplerate)
        else:
            o = o(frequency=freq, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)
        return o

    def do_play(self, osc):
        duration = 1
        osc.set_title_status("TO SPEAKER")
        osc.after(duration*1000, lambda: osc.set_title_status(None))
        o = self.create_osc(osc, all_oscillators=self.oscillators)
        sample = self.generate_sample(o, 1)
        with Output(self.synth.samplerate, self.synth.samplewidth, duration) as out:
            out.play_sample(sample, async=True)

    def do_plot(self, osc):
        o = self.create_osc(osc, all_oscillators=self.oscillators)
        o = iter(o)
        frames = [next(o) for _ in range(self.synth.samplerate)]
        if not plot:
            self.statusbar["text"] = "Cannot plot! To plot things, you need to have matplotlib installed!"
            return
        plot.figure(figsize=(16, 4))
        plot.title("Waveform")
        plot.plot(frames)
        plot.show()
        # @todo properly integrate matplotlib in the tkinter gui because the above causes gui freeze problems
        # see http://matplotlib.org/examples/user_interfaces/embedding_in_tk2.html

    def generate_sample(self, oscillator, duration):
        o = iter(oscillator)
        scale = 2**(8*self.synth.samplewidth-1)
        frames = [int(next(o)*scale) for _ in range(int(self.synth.samplerate*duration))]
        return Sample.from_array(frames, self.synth.samplerate, 1).fadein(0.05).fadeout(0.1)

    def pressed(self, event, note, octave, released=False):
        self.statusbar["text"] = "ok"
        freq = note_freq(note, octave)
        to_speaker = self.to_speaker_lb.curselection()
        to_speaker = [self.oscillators[i] for i in to_speaker]
        if not to_speaker:
            self.statusbar["text"] = "No oscillators connected to speaker output!"
            return
        if released:
            for osc in to_speaker:
                osc.set_title_status(None)
            return
        for osc in to_speaker:
            osc.input_freq.set(freq)
            osc.set_title_status("TO SPEAKER")
        oscs = [self.create_osc(osc, all_oscillators=self.oscillators) for osc in to_speaker]
        mixed_osc = MixingFilter(*oscs) if len(oscs) > 1 else oscs[0]
        sample = self.generate_sample(mixed_osc, 0.5)
        if sample.samplewidth != self.synth.samplewidth:
            sample.make_16bit()
        with Output(self.synth.samplerate, self.synth.samplewidth, 1) as out:
            out.play_sample(sample, async=True)


if __name__ == "__main__":
    root = tk.Tk()
    app = SynthGUI(master=root)
    app.mainloop()
