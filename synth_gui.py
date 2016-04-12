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


class OscillatorGUI(tk.Frame):
    def __init__(self, master, gui, title, fm_sources=None, pwm_sources=None):
        super().__init__(master)
        self._title = title
        self.oscframe = tk.LabelFrame(self, text=title)
        self.oscframe.pack(side=tk.LEFT)
        leftframe = tk.Frame(self.oscframe)
        leftframe.pack(side=tk.LEFT, anchor=tk.N)
        waveforms = ["sine", "triangle", "pulse", "sawtooth", "sawtooth_h", "square", "square_h", "noise", "linear", "harmonics"]
        self.input_waveformtype = tk.StringVar()
        self.input_waveformtype.set("sine")
        for w in waveforms:
            tk.Radiobutton(leftframe, text=w, variable=self.input_waveformtype, value=w, command=self.waveform_selected).pack(anchor=tk.W)
        rightframe = tk.Frame(self.oscframe)
        rightframe.pack(side=tk.RIGHT, anchor=tk.N)
        self.make_inputs_frame(rightframe, fm_sources, pwm_sources)
        tk.Button(rightframe, text="Play", command=lambda: gui.do_play(self)).pack(side=tk.RIGHT, pady=10)
        tk.Button(rightframe, text="Plot", command=lambda: gui.do_plot(self)).pack(side=tk.RIGHT, pady=10)
        self.pack(side=tk.LEFT, anchor=tk.N, padx=10, pady=10)

    # noinspection PyAttributeOutsideInit
    def make_inputs_frame(self, master, fm_sources, pwm_sources):
        f = tk.LabelFrame(master, text="inputs")
        # freq, amplitude, phase, bias, pw, fm, and other settings
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
        self.input_freq_keys = tk.BooleanVar()
        self.input_freq_keys.set(True)
        self.input_freq_keys_ratio = tk.DoubleVar()
        self.input_freq_keys_ratio.set(1.0)
        self.input_lin_start = tk.DoubleVar()
        self.input_lin_increment = tk.DoubleVar()
        self.input_lin_increment.set(0.00002)
        self.input_lin_min = tk.DoubleVar()
        self.input_lin_min.set(-1.0)
        self.input_lin_max = tk.DoubleVar()
        self.input_lin_max.set(1.0)
        row = 0
        self.freq_label = tk.Label(f, text="freq Hz")
        self.freq_label.grid(row=row, column=0, sticky=tk.E)
        self.freq_entry = tk.Entry(f, width=10, textvariable=self.input_freq)
        self.freq_entry.grid(row=row, column=1)
        row += 1
        self.keys_label = tk.Label(f, text="from keys?")
        self.keys_label.grid(row=row, column=0, sticky=tk.E)
        self.keys_checkbox = tk.Checkbutton(f, variable=self.input_freq_keys, command=self.from_keys_selected)
        self.keys_checkbox.grid(row=row, column=1)
        row += 1
        self.ratio_label = tk.Label(f, text="freq ratio")
        self.ratio_label.grid(row=row, column=0, sticky=tk.E)
        self.ratio_entry = tk.Entry(f, width=10, textvariable=self.input_freq_keys_ratio)
        self.ratio_entry.grid(row=row, column=1)
        row += 1
        self.amp_label = tk.Label(f, text="amp")
        self.amp_label.grid(row=row, column=0, sticky=tk.E)
        self.amp_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_amp, from_=0, to=1.0, resolution=.01)
        self.amp_slider.grid(row=row, column=1)
        row += 1
        self.pw_label = tk.Label(f, text="pulsewidth")
        self.pw_label.grid(row=row, column=0, sticky=tk.E)
        self.pw_label.grid_remove()
        self.pw_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_pw, from_=.001, to=.999, resolution=.001)
        self.pw_slider.grid(row=row, column=1)
        self.pw_slider.grid_remove()
        row += 1
        self.phase_label = tk.Label(f, text="phase")
        self.phase_label.grid(row=row, column=0, sticky=tk.E)
        self.phase_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_phase, from_=0, to=1.0, resolution=.01)
        self.phase_slider.grid(row=row, column=1)
        row += 1
        self.bias_label = tk.Label(f, text="bias")
        self.bias_label.grid(row=row, column=0, sticky=tk.E)
        self.bias_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_bias, from_=-1, to=1, resolution=.01)
        self.bias_slider.grid(row=row, column=1)
        row += 1
        self.lin_start_label = tk.Label(f, text="start")
        self.lin_start_label.grid(row=row, column=0, sticky=tk.E)
        self.lin_start_label.grid_remove()
        self.lin_start_entry = tk.Entry(f, width=10, textvariable=self.input_lin_start)
        self.lin_start_entry.grid(row=row, column=1)
        self.lin_start_entry.grid_remove()
        row += 1
        self.lin_increment_label = tk.Label(f, text="increment")
        self.lin_increment_label.grid(row=row, column=0, sticky=tk.E)
        self.lin_increment_label.grid_remove()
        self.lin_increment_entry = tk.Entry(f, width=10, textvariable=self.input_lin_increment)
        self.lin_increment_entry.grid(row=row, column=1)
        self.lin_increment_entry.grid_remove()
        row += 1
        self.lin_min_label = tk.Label(f, text="min")
        self.lin_min_label.grid(row=row, column=0, sticky=tk.E)
        self.lin_min_label.grid_remove()
        self.lin_min_entry = tk.Entry(f, width=10, textvariable=self.input_lin_min)
        self.lin_min_entry.grid(row=row, column=1)
        self.lin_min_entry.grid_remove()
        row += 1
        self.lin_max_label = tk.Label(f, text="max")
        self.lin_max_label.grid(row=row, column=0, sticky=tk.E)
        self.lin_max_label.grid_remove()
        self.lin_max_entry = tk.Entry(f, width=10, textvariable=self.input_lin_max)
        self.lin_max_entry.grid(row=row, column=1)
        self.lin_max_entry.grid_remove()
        row +=1
        self.harmonics_label = tk.Label(f, text="harmonics\n(num,fraction\npairs)", justify=tk.RIGHT)
        self.harmonics_label.grid(row=row, column=0, sticky=tk.E)
        self.harmonics_text = tk.Text(f, width=16, height=5, font=("helvetica", 10))
        self.harmonics_text.insert(tk.INSERT, "1,1   2,1/2\n3,1/3  4,1/4\n5,1/5  6,1/6\n7,1/7  8,1/8")
        self.harmonics_text.grid(row=row, column=1)
        if fm_sources:
            row += 1
            self.fm_label = tk.Label(f, text="FM")
            self.fm_label.grid(row=row, column=0, sticky=tk.E)
            values = ["<none>"]
            values.extend(fm_sources)
            self.fm_select = tk.OptionMenu(f, self.input_fm, *values)
            self.fm_select["width"] = 10
            self.fm_select.grid(row=row, column=1)
            self.input_fm.set("<none>")
        if pwm_sources:
            row += 1
            self.pwm_label = tk.Label(f, text="PWM")
            self.pwm_label.grid(row=row, column=0, sticky=tk.E)
            self.pwm_label.grid_remove()
            values = ["<none>"]
            values.extend(pwm_sources)
            self.pwm_select = tk.OptionMenu(f, self.input_pwm, *values, command=self.pwm_selected)
            self.pwm_select["width"] = 10
            self.pwm_select.grid(row=row, column=1)
            self.pwm_select.grid_remove()
            self.input_pwm.set("<none>")
        f.pack(side=tk.TOP)

    def set_title_status(self, status):
        title = self._title
        if status:
            title = "{} - [{}]".format(self._title, status)
        self.oscframe["text"] = title

    def waveform_selected(self, *args):
        # restore everything to the basic input set of the sine wave
        self.freq_label.grid()
        self.freq_entry.grid()
        self.keys_label.grid()
        self.keys_checkbox.grid()
        self.ratio_label.grid()
        self.ratio_entry.grid()
        self.phase_label.grid()
        self.phase_slider.grid()
        self.amp_label.grid()
        self.amp_slider.grid()
        self.bias_label.grid()
        self.bias_slider.grid()
        if hasattr(self, "fm_label"):
            self.fm_label.grid()
            self.fm_select.grid()
        self.lin_start_label.grid_remove()
        self.lin_start_entry.grid_remove()
        self.lin_increment_label.grid_remove()
        self.lin_increment_entry.grid_remove()
        self.lin_min_label.grid_remove()
        self.lin_min_entry.grid_remove()
        self.lin_max_label.grid_remove()
        self.lin_max_entry.grid_remove()

        wf = self.input_waveformtype.get()
        if wf == "harmonics":
            self.harmonics_label.grid()
            self.harmonics_text.grid()
        else:
            self.harmonics_label.grid_remove()
            self.harmonics_text.grid_remove()

        if wf in ("noise", "linear"):
            # remove most of the input fields
            self.freq_label.grid_remove()
            self.freq_entry.grid_remove()
            self.keys_label.grid_remove()
            self.keys_checkbox.grid_remove()
            self.ratio_label.grid_remove()
            self.ratio_entry.grid_remove()
            self.phase_label.grid_remove()
            self.phase_slider.grid_remove()
            if hasattr(self, "fm_label"):
                self.fm_label.grid_remove()
                self.fm_select.grid_remove()
            if wf == "linear":
                # remove more stuff and show the linear fields
                self.amp_label.grid_remove()
                self.amp_slider.grid_remove()
                self.bias_label.grid_remove()
                self.bias_slider.grid_remove()
                self.lin_start_label.grid()
                self.lin_start_entry.grid()
                self.lin_increment_label.grid()
                self.lin_increment_entry.grid()
                self.lin_min_label.grid()
                self.lin_min_entry.grid()
                self.lin_max_label.grid()
                self.lin_max_entry.grid()

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
        state = "normal" if self.input_pwm.get() == "<none>" else "disabled"
        self.pw_label["state"]=state
        self.pw_slider["state"]=state

    def from_keys_selected(self, *args):
        state = "normal" if self.input_freq_keys.get() else "disabled"
        self.ratio_label["state"] = state
        self.ratio_entry["state"] = state


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
        waveform = from_gui.input_waveformtype.get()
        amp = from_gui.input_amp.get()
        bias = from_gui.input_bias.get()
        if waveform == "noise":
            return WhiteNoise(amplitude=amp, bias=bias, samplerate=self.synth.samplerate)
        elif waveform == "linear":
            startlevel = from_gui.input_lin_start.get()
            increment = from_gui.input_lin_increment.get()
            minvalue = from_gui.input_lin_min.get()
            maxvalue = from_gui.input_lin_max.get()
            return Linear(startlevel, increment, minvalue, maxvalue)
        else:
            freq = from_gui.input_freq.get()
            phase = from_gui.input_phase.get()
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
            if waveform == "pulse":
                return Pulse(frequency=freq, amplitude=amp, phase=phase, bias=bias, pulsewidth=pw, fm_lfo=fm, pwm_lfo=pwm, samplerate=self.synth.samplerate)
            elif waveform == "harmonics":
                harmonics = self.parse_harmonics(from_gui.harmonics_text.get(1.0, tk.END))
                return Harmonics(frequency=freq, harmonics=harmonics, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)
            else:
                o = {
                    "sine": Sine,
                    "triangle": Triangle,
                    "sawtooth": Sawtooth,
                    "sawtooth_h": SawtoothH,
                    "square": Square,
                    "square_h": SquareH,
                    }[waveform]
                return o(frequency=freq, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)

    def parse_harmonics(self, harmonics):
        parsed = []
        for harmonic in harmonics.split():
            num, frac = harmonic.split(",")
            num = int(num)
            if '/' in frac:
                numerator, denominator = frac.split("/")
            else:
                numerator, denominator = frac, 1
            frac = float(numerator)/float(denominator)
            parsed.append((num, frac))
        return parsed

    def do_play(self, osc):
        if osc.input_waveformtype.get() == "linear":
            self.statusbar["text"] = "cannot output linear osc to speakers"
            return
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
        for osc in self.oscillators:
            if osc.input_freq_keys.get():
                osc.input_freq.set(freq*osc.input_freq_keys_ratio.get())
        for osc in to_speaker:
            if osc.input_waveformtype.get() == "linear":
                self.statusbar["text"] = "cannot output linear osc to speakers"
                return
            else:
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
    if platform.system() == "Darwin":
        # @todo fix this....
        warning = "Sorry but the piano keyboard buttons are messed up on OSX due to not being able to resize buttons..."
        print(warning)
        app.statusbar["text"] = warning
    app.mainloop()
