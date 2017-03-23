"""
GUI For the synthesizer components, including a piano keyboard.
Implements a set of LFOs with all of their parameters,
a set of ADSR envelope filters,
and a few other output filters such as tremolo and echo.
You can play simple notes, chords, or let an arpeggiator run the notes.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import time
import collections
import tkinter as tk
from tkinter.filedialog import askopenfile, asksaveasfile
from threading import Semaphore
from configparser import ConfigParser
from synthesizer.synth import Sine, Triangle, Sawtooth, SawtoothH, Square, SquareH, Harmonics, Pulse, WhiteNoise, Linear
from synthesizer.synth import WaveSynth, note_freq, MixingFilter, EchoFilter, AmpMudulationFilter, EnvelopeFilter
from synthesizer.synth import major_chord_keys
from synthesizer.sample import Sample
from synthesizer.playback import Output
try:
    import matplotlib
    matplotlib.use("tkagg")
    import matplotlib.pyplot as plot
except ImportError:
    plot = None


class OscillatorGUI(tk.LabelFrame):
    def __init__(self, master, gui, title, fm_sources=None, pwm_sources=None):
        super().__init__(master, text=title, padx=8, pady=8)
        self._title = title
        f = tk.Frame(self)
        self.input_waveformtype = tk.StringVar()
        self.input_waveformtype.set("sine")
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
        waveforms = ["sine", "triangle", "pulse", "sawtooth", "sawtooth_h", "square", "square_h", "noise", "linear", "harmonics"]
        tk.Label(f, text="waveform").grid(row=row, column=0, sticky=tk.E)
        waveform = tk.OptionMenu(f, self.input_waveformtype, *waveforms, command=self.waveform_selected)
        waveform["width"] = 10
        waveform.grid(row=row, column=1)
        row += 1
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
        self.amp_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_amp, from_=0, to=1.0, resolution=.01, width=10, length=120)
        self.amp_slider.grid(row=row, column=1)
        row += 1
        self.pw_label = tk.Label(f, text="pulsewidth")
        self.pw_label.grid(row=row, column=0, sticky=tk.E)
        self.pw_label.grid_remove()
        self.pw_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_pw, from_=.001, to=.999, resolution=.001, width=10, length=120)
        self.pw_slider.grid(row=row, column=1)
        self.pw_slider.grid_remove()
        row += 1
        self.phase_label = tk.Label(f, text="phase")
        self.phase_label.grid(row=row, column=0, sticky=tk.E)
        self.phase_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_phase, from_=0, to=1.0, resolution=.01, width=10, length=120)
        self.phase_slider.grid(row=row, column=1)
        row += 1
        self.bias_label = tk.Label(f, text="bias")
        self.bias_label.grid(row=row, column=0, sticky=tk.E)
        self.bias_slider = tk.Scale(f, orient=tk.HORIZONTAL, variable=self.input_bias, from_=-1, to=1, resolution=.01, width=10, length=120)
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
        row += 1
        self.harmonics_label = tk.Label(f, text="harmonics\n(num,fraction)\npairs", justify=tk.RIGHT)
        self.harmonics_label.grid(row=row, column=0, sticky=tk.E)
        self.harmonics_label.grid_remove()
        self.harmonics_text = tk.Text(f, width=15, height=5)
        self.harmonics_text.insert(tk.INSERT, "1,1   2,1/2\n3,1/3  4,1/4\n5,1/5  6,1/6\n7,1/7  8,1/8")
        self.harmonics_text.grid(row=row, column=1)
        self.harmonics_text.grid_remove()
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
        f = tk.Frame(self, pady=4)
        tk.Button(f, text="Play", command=lambda: gui.do_play(self)).pack(side=tk.RIGHT, padx=5)
        tk.Button(f, text="Plot", command=lambda: gui.do_plot(self)).pack(side=tk.RIGHT, padx=5)
        f.pack(side=tk.TOP, anchor=tk.E)

    def set_title_status(self, status):
        title = self._title
        if status:
            title = "{} - [{}]".format(self._title, status)
        self["text"] = title

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
        self.pw_label["state"] = state
        self.pw_slider["state"] = state

    def from_keys_selected(self, *args):
        state = "normal" if self.input_freq_keys.get() else "disabled"
        self.ratio_label["state"] = state
        self.ratio_entry["state"] = state


class PianoKeyboardGUI(tk.Frame):
    def __init__(self, master, gui):
        super().__init__(master)
        white_key_width = 30
        white_key_height = 110
        black_key_width = white_key_width * 0.5
        black_key_height = white_key_height * 0.6
        num_octaves = 5
        first_octave = 2
        x_offset = 3
        y_offset = 20
        canvas = tk.Canvas(self, width=white_key_width*num_octaves*7+2, height=white_key_height+10+y_offset, borderwidth=0)
        # white keys:
        for key_nr, key in enumerate("CDEFGAB"*num_octaves):
            octave = first_octave+key_nr//7
            def key_pressed(event, note=key, octave=octave):
                force = min(white_key_height, event.y*1.08)/white_key_height   # @todo control output volume, unused for now...
                gui.pressed(event, note, octave, False)
            def key_released(event, note=key, octave=octave):
                gui.pressed(event, note, octave, True)
            x = key_nr * white_key_width
            key_rect = canvas.create_rectangle(x+x_offset, y_offset, x+white_key_width+x_offset, white_key_height+y_offset, fill="white", outline="gray50", width=1, activewidth=2)
            canvas.tag_bind(key_rect, "<ButtonPress-1>", key_pressed)
            canvas.tag_bind(key_rect, "<ButtonRelease-1>", key_released)
            canvas.create_text(x+white_key_width/2+2, 1, text=key, anchor=tk.N, fill="gray")
            if 10 <= key_nr <= 21:
                keychar = "qwertyuiop[]"[key_nr-10]
                canvas.create_text(x+white_key_width/2+2, white_key_height+3, text=keychar, anchor=tk.N, fill="maroon")
                gui.bind_keypress(keychar, key, octave)
        # black keys:
        for key_nr, key in enumerate((["C#", "D#", None, "F#", "G#", "A#", None]*num_octaves)[:-1]):
            if key:
                octave = first_octave + key_nr // 7
                def key_pressed(event, note=key, octave=octave):
                    force = min(black_key_height, event.y * 1.1) / black_key_height   # @todo control output volume, unused for now...
                    gui.pressed(event, note, octave, False)
                def key_released(event, note=key, octave=octave):
                    gui.pressed(event, note, octave, True)
                x = key_nr * white_key_width + white_key_width*0.75
                key_rect = canvas.create_rectangle(x+x_offset, y_offset, x+black_key_width+x_offset, black_key_height+y_offset, fill="black", outline="gray50", width=1, activewidth=2)
                canvas.tag_bind(key_rect, "<ButtonPress-1>", key_pressed)
                canvas.tag_bind(key_rect, "<ButtonRelease-1>", key_released)
        canvas.pack()


class EchoFilterGUI(tk.LabelFrame):
    def __init__(self, master, gui):
        super().__init__(master, text="output: Echo / Delay")
        self.input_enabled = tk.BooleanVar()
        self.input_after = tk.DoubleVar()
        self.input_after.set(0.00)
        self.input_amount = tk.IntVar()
        self.input_amount.set(6)
        self.input_delay = tk.DoubleVar()
        self.input_delay.set(0.2)
        self.input_decay = tk.DoubleVar()
        self.input_decay.set(0.7)
        row = 0
        tk.Label(self, text="enable?").grid(row=row, column=0)
        tk.Checkbutton(self, variable=self.input_enabled).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Label(self, text="after").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_after, from_=0, to=2.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="amount").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_amount, from_=1, to=10, resolution=1, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="delay").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_delay, from_=0.0, to=0.5, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="decay").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_decay, from_=0.01, to=1.5, resolution=.1, width=10, length=120).grid(row=row, column=1)

    def filter(self, source):
        if self.input_enabled.get():
            after = self.input_after.get()
            amount = self.input_amount.get()
            delay = self.input_delay.get()
            decay = self.input_decay.get()
            return EchoFilter(source, after, amount, delay, decay)
        return source


class TremoloFilterGUI(tk.LabelFrame):
    def __init__(self, master, gui):
        super().__init__(master, text="output: Tremolo")
        self.gui = gui
        self.input_waveform = tk.StringVar()
        self.input_waveform.set("<off>")
        self.input_rate = tk.DoubleVar()
        self.input_depth = tk.DoubleVar()
        self.input_rate.set(5)
        self.input_depth.set(80)
        row = 0
        tk.Label(self, text="waveform").grid(row=row, column=0)
        values = ["<off>", "sine", "triangle", "sawtooth", "square"]
        menu = tk.OptionMenu(self, self.input_waveform, *values)
        menu["width"] = 10
        menu.grid(row=row, column=1)
        row += 1
        tk.Label(self, text="rate").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_rate, from_=0.0, to=10.0, resolution=.1, width=10, length=100).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="depth").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_depth, from_=0.0, to=1.0, resolution=.02, width=10, length=100).grid(row=row, column=1)

    def filter(self, source):
        wave = self.input_waveform.get()
        freq = self.input_rate.get()
        amp = self.input_depth.get() / 2.0
        samplerate = self.gui.synth.samplerate
        bias = 1.0 - amp
        if amp == 0.0 or freq == 0.0 or wave in (None, "", "<none>", "<off>"):
            return source
        if wave == "sine":
            modulator = Sine(freq, amp, bias=bias, samplerate=samplerate)
        elif wave == "triangle":
            modulator = Triangle(freq, amp, bias=bias, samplerate=samplerate)
        elif wave == "sawtooth":
            modulator = SawtoothH(freq, 9, amp, bias=bias, samplerate=samplerate)
        elif wave == "square":
            modulator = SquareH(freq, 9, amp, bias=bias, samplerate=samplerate)
        return AmpMudulationFilter(source, iter(modulator))


class ArpeggioFilterGUI(tk.LabelFrame):
    def __init__(self, master, gui):
        super().__init__(master, text="keys: Chords / Arpeggio")
        self.gui = gui
        self.input_mode = tk.StringVar()
        self.input_mode.set("off")
        self.input_rate = tk.DoubleVar()    # duration of note triggers
        self.input_rate.set(0.2)
        self.input_ratio = tk.IntVar()   # how many % the note is on vs off
        self.input_ratio.set(100)
        row = 0
        tk.Label(self, text="Major Chords Arp").grid(row=row, column=0, columnspan=2)
        row += 1
        tk.Radiobutton(self, variable=self.input_mode, value="off", text="off", pady=0, command=self.mode_off_selected).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Radiobutton(self, variable=self.input_mode, value="chords3", text="Chords Maj. 3", pady=0).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Radiobutton(self, variable=self.input_mode, value="chords4", text="Chords Maj. 7th", pady=0).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Radiobutton(self, variable=self.input_mode, value="arpeggio3", text="Arpeggio 3", pady=0).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Radiobutton(self, variable=self.input_mode, value="arpeggio4", text="Arpeggio 7th", pady=0).grid(row=row, column=1, sticky=tk.W)
        row += 1
        tk.Label(self, text="rate").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_rate, from_=0.02, to=.5, resolution=.01, width=10, length=100).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="ratio").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_ratio, from_=1, to=100, resolution=1, width=10, length=100).grid(row=row, column=1)

    def mode_off_selected(self):
        self.gui.arpeggio_playing = False   # stop any arpeggio that may be running
        self.gui.statusbar["text"] = "ok"


class EnvelopeFilterGUI(tk.LabelFrame):
    def __init__(self, master, name, gui):
        super().__init__(master, text="ADSR Envelope "+name)
        self.input_source = tk.StringVar()
        self.input_attack = tk.DoubleVar()
        self.input_attack.set(0.05)
        self.input_decay = tk.DoubleVar()
        self.input_decay.set(0.5)
        self.input_sustain = tk.DoubleVar()
        self.input_sustain.set(0.6)
        self.input_sustain_level = tk.DoubleVar()
        self.input_sustain_level.set(0.5)
        self.input_release = tk.DoubleVar()
        self.input_release.set(0.6)
        row = 0
        tk.Label(self, text="apply to").grid(row=row, column=0, sticky=tk.E)
        values = ["<none>", "osc 1", "osc 2", "osc 3", "osc 4", "osc 5"]
        menu = tk.OptionMenu(self, self.input_source, *values)
        menu["width"] = 10
        menu.grid(row=row, column=1)
        row += 1
        tk.Label(self, text="attack").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_attack, from_=0, to=2.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="decay").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_decay, from_=0, to=2.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="sustain").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_sustain, from_=0.0, to=2.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="sustain lvl").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_sustain_level, from_=0.0, to=1.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        row += 1
        tk.Label(self, text="release").grid(row=row, column=0, sticky=tk.E)
        tk.Scale(self, orient=tk.HORIZONTAL, variable=self.input_release, from_=0.0, to=2.0, resolution=.01, width=10, length=120).grid(row=row, column=1)
        self.input_source.set("<none>")

    @property
    def duration(self):
        if self.input_source.get() in (None, "", "<none>"):
            return 0
        return self.input_attack.get() + self.input_decay.get() + self.input_sustain.get() + self.input_release.get()

    def filter(self, source):
        attack = self.input_attack.get()
        decay = self.input_decay.get()
        sustain = self.input_sustain.get()
        sustain_level = self.input_sustain_level.get()
        release = self.input_release.get()
        return EnvelopeFilter(source, attack, decay, sustain, sustain_level, release, False)


class SynthGUI(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master.title("Synthesizer")
        self.keypress_sema = Semaphore(1)    # XXX improve mechanism, see keyboard presses?
        self.osc_frame = tk.Frame(self)
        self.oscillators = []
        self.piano_frame = tk.Frame(self)
        self.piano = PianoKeyboardGUI(self.piano_frame, self)
        self.piano.pack(side=tk.BOTTOM)
        filter_frame = tk.LabelFrame(self, text="Filters etc.", padx=10, pady=10)
        self.envelope_filters = [
            EnvelopeFilterGUI(filter_frame, "1", self),
            EnvelopeFilterGUI(filter_frame, "2", self),
            EnvelopeFilterGUI(filter_frame, "3", self)]
        self.echo_filter = EchoFilterGUI(filter_frame, self)
        for ev in self.envelope_filters:
            ev.pack(side=tk.LEFT, anchor=tk.N)
        self.arp_filter = ArpeggioFilterGUI(filter_frame, self)
        self.arp_filter.pack(side=tk.LEFT, anchor=tk.N)
        f = tk.Frame(filter_frame)
        self.tremolo_filter = TremoloFilterGUI(f, self)
        self.tremolo_filter.pack(side=tk.TOP)
        lf = tk.LabelFrame(f, text="A4 tuning")
        lf.pack(pady=(4, 0))
        lf = tk.LabelFrame(f, text="Performance")
        self.samplerate_choice = tk.IntVar()
        self.samplerate_choice.set(44100)
        tk.Label(lf, text="Samplerate:").pack(anchor=tk.W)
        subf = tk.Frame(lf)
        tk.Radiobutton(subf, variable=self.samplerate_choice, value=44100, text="44.1 kHz", pady=0, command=self.create_synth).pack(side=tk.LEFT)
        tk.Radiobutton(subf, variable=self.samplerate_choice, value=22050, text="22 kHz", pady=0, command=self.create_synth).pack(side=tk.LEFT)
        subf.pack()
        tk.Label(lf, text="Piano key response:").pack(anchor=tk.W)
        subf = tk.Frame(lf)
        self.rendering_choice = tk.StringVar()
        self.rendering_choice.set("realtime")
        tk.Radiobutton(subf, variable=self.rendering_choice, value="realtime", text="realtime", pady=0).pack(side=tk.LEFT)
        tk.Radiobutton(subf, variable=self.rendering_choice, value="render", text="render", pady=0).pack(side=tk.LEFT)
        subf.pack()
        lf.pack(pady=(4, 0))
        f.pack(side=tk.LEFT, anchor=tk.N)
        self.echo_filter.pack(side=tk.LEFT, anchor=tk.N)
        misc_frame = tk.Frame(filter_frame, padx=10)
        tk.Label(misc_frame, text="To Speaker:").pack(pady=(5, 0))
        self.to_speaker_lb = tk.Listbox(misc_frame, width=8, height=5, selectmode=tk.MULTIPLE, exportselection=0)
        self.to_speaker_lb.pack()
        lf = tk.LabelFrame(misc_frame, text="A4 tuning")
        self.a4_choice = tk.IntVar()
        self.a4_choice.set(440)
        tk.Radiobutton(lf, variable=self.a4_choice, value=440, text="440 Hz", pady=0).pack()
        tk.Radiobutton(lf, variable=self.a4_choice, value=432, text="432 Hz", pady=0).pack()
        lf.pack(pady=(4, 0))
        tk.Button(misc_frame, text="Load preset", command=self.load_preset).pack()
        tk.Button(misc_frame, text="Save preset", command=self.save_preset).pack()
        for _ in range(5):
            self.add_osc_to_gui()
        self.to_speaker_lb.select_set(4)
        self.osc_frame.pack(side=tk.TOP, padx=10)
        filter_frame.pack(side=tk.TOP)
        misc_frame.pack(side=tk.RIGHT, anchor=tk.N)
        self.piano_frame.pack(side=tk.TOP, padx=10, pady=10)
        self.statusbar = tk.Label(self, text="<status>", relief=tk.RIDGE)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.pack()
        self.synth = self.output = None
        self.create_synth()
        self.playing_note = False
        self.current_note = None
        self.echos_ending_time = 0
        self.arpeggio_playing = False
        self.pressed_keyboard_keys = set()

    def bind_keypress(self, key, note, octave):
        def kbpress(event):
            if key not in self.pressed_keyboard_keys:
                self.pressed(event, note, octave, False)
            self.pressed_keyboard_keys.add(key)
        def kbrelease(event):
            self.pressed(event, note, octave, True)
            self.pressed_keyboard_keys.remove(key)
        self.master.bind(key, kbpress)
        if key=='[':
            key = "bracketleft"
        if key==']':
            key = "bracketright"
        self.master.bind("<KeyRelease-%s>" % key, kbrelease)

    def create_synth(self):
        samplerate = self.samplerate_choice.get()
        self.synth = WaveSynth(samplewidth=2, samplerate=samplerate)
        if self.output is not None:
            self.output.close()
        self.output = Output(self.synth.samplerate, self.synth.samplewidth, 1, queuesize=2)

    def add_osc_to_gui(self):
        osc_nr = len(self.oscillators)
        fm_sources = ["osc "+str(n+1) for n in range(osc_nr)]
        osc_pane = OscillatorGUI(self.osc_frame, self, "Oscillator "+str(osc_nr+1), fm_sources=fm_sources, pwm_sources=fm_sources)
        osc_pane.pack(side=tk.LEFT, anchor=tk.N, padx=10, pady=10)
        self.oscillators.append(osc_pane)
        self.to_speaker_lb.insert(tk.END, "osc "+str(osc_nr+1))

    def create_osc(self, from_gui, all_oscillators, is_audio=False):
        def create_unfiltered_osc():
            def create_chord_osc(clazz, **arguments):
                if is_audio and self.arp_filter.input_mode.get().startswith("chords"):
                    chord_keys = major_chord_keys(self.current_note[0], self.current_note[1])
                    if self.arp_filter.input_mode.get() == "chords3":
                        chord_keys = list(chord_keys)[:-1]
                    a4freq = self.a4_choice.get()
                    chord_freqs = [note_freq(note, octave, a4freq) for note, octave in chord_keys]
                    self.statusbar["text"] = "major chord: "+" ".join(note for note, octave in chord_keys)
                    oscillators = []
                    arguments["amplitude"] /= len(chord_freqs)
                    for f in chord_freqs:
                        arguments["frequency"] = f
                        oscillators.append(clazz(**arguments))
                    return MixingFilter(*oscillators)
                else:
                    # no chord (or an LFO instead of audio output oscillator), return one osc for only the given frequency
                    return clazz(**arguments)
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
                    return create_chord_osc(Pulse, frequency=freq, amplitude=amp, phase=phase, bias=bias, pulsewidth=pw, fm_lfo=fm, pwm_lfo=pwm, samplerate=self.synth.samplerate)
                elif waveform == "harmonics":
                    harmonics = self.parse_harmonics(from_gui.harmonics_text.get(1.0, tk.END))
                    return create_chord_osc(Harmonics, frequency=freq, harmonics=harmonics, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)
                else:
                    o = {
                        "sine": Sine,
                        "triangle": Triangle,
                        "sawtooth": Sawtooth,
                        "sawtooth_h": SawtoothH,
                        "square": Square,
                        "square_h": SquareH,
                        }[waveform]
                    return create_chord_osc(o, frequency=freq, amplitude=amp, phase=phase, bias=bias, fm_lfo=fm, samplerate=self.synth.samplerate)

        def envelope(osc, envelope_gui):
            adsr_src = envelope_gui.input_source.get()
            if adsr_src not in (None, "", "<none>"):
                osc_num = int(adsr_src.split()[1])
                if from_gui is self.oscillators[osc_num-1]:
                    return envelope_gui.filter(osc)
            return osc

        osc = create_unfiltered_osc()
        for ev in self.envelope_filters:
            osc = envelope(osc, ev)
        return osc

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
        o = self.create_osc(osc, all_oscillators=self.oscillators, is_audio=True)
        o = self.apply_filters(o)
        sample = self.generate_sample(iter(o), 1)
        with Output(self.synth.samplerate, self.synth.samplewidth, duration) as out:
            out.play_sample(sample)

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

    def generate_sample(self, oscillator, duration, use_fade=False):
        o = oscillator  # iter(oscillator)
        scale = 2**(8*self.synth.samplewidth-1)
        try:
            frames = [int(next(o)*scale) for _ in range(int(self.synth.samplerate*duration))]
        except StopIteration:
            return None
        else:
            sample = Sample.from_array(frames, self.synth.samplerate, 1)
            if use_fade:
                sample.fadein(0.05).fadeout(0.1)
            return sample

    def continue_play_note(self, oscillator, first=True):
        if self.echos_ending_time and time.time() >= self.echos_ending_time:
            self.stop_playing_note()
            return
        if not self.playing_note:
            sample = self.generate_sample(oscillator, 0.1).fadeout(0.1)
            if sample:
                if sample.samplewidth != self.synth.samplewidth:
                    print("16 bit overflow!")  # XXX
                    sample.make_16bit()
                self.output.play_sample(sample)
            return
        if first:
            sample = self.generate_sample(oscillator, 0.1)
            if sample:
                sample.fadein(0.05)
                if sample.samplewidth != self.synth.samplewidth:
                    print("16 bit overflow!")  # XXX
                    sample.make_16bit()
                self.output.play_sample(sample)
        sample = self.generate_sample(oscillator, 0.1)
        if sample:
            if sample.samplewidth != self.synth.samplewidth:
                print("16 bit overflow!")  # XXX
                sample.make_16bit()
            self.output.play_sample(sample)
            self.after_idle(lambda: self.continue_play_note(oscillator, False))

    def render_and_play_note(self, oscillator, max_duration=4):
        duration = 0
        for ev in self.envelope_filters:
            duration = max(duration, ev.duration)
        if duration == 0:
            duration = max_duration
        duration = min(duration, max_duration)
        sample = self.generate_sample(oscillator, duration)
        if sample:
            sample.fadein(0.05).fadeout(0.05)
            if sample.samplewidth != self.synth.samplewidth:
                print("16 bit overflow!")  # XXX
                sample.make_16bit()
            self.output.play_sample(sample)

    def stop_playing_note(self):
        self.playing_note = False
        to_speaker = [self.oscillators[i] for i in self.to_speaker_lb.curselection()]
        for osc in to_speaker:
            osc.set_title_status(None)
        self.keypress_sema.release()

    def pressed(self, event, note, octave, released=False):
        if self.arpeggio_playing:
            if not released:
                # arp still playing... stop it
                self.arpeggio_playing = False
            return
        a4freq = self.a4_choice.get()
        if self.arp_filter.input_mode.get().startswith("arp"):
            if released:
                self._pressed([0, 1, 2], released=True)
                return
            chord_keys = major_chord_keys(note, octave)
            if self.arp_filter.input_mode.get() == "arpeggio3":
                chord_keys = list(chord_keys)[:-1]
            chord_freqs = [note_freq(note, octave, a4freq) for note, octave in chord_keys]
            self.statusbar["text"] = "arpeggio: "+" ".join(note for note, octave in chord_keys)
            self.arpeggio_playing = True
            self._pressed(chord_freqs)
        else:
            self.statusbar["text"] = "ok"
            a4freq = self.a4_choice.get()
            freq = note_freq(note, octave, a4freq)
            self.current_note = (note, octave, freq)
            self._pressed(freq, released)

    def _pressed(self, freqs, released=False):
        # freqs can be a single frequency or a sequence of freqs (ARP)
        if isinstance(freqs, (tuple, list)):
            freq = freqs[0]
            arpeggio = True
        else:
            freq = freqs
            arpeggio = False
        if arpeggio and not self.arpeggio_playing:
            # stop the running arp cycle
            return
        to_speaker = [self.oscillators[i] for i in self.to_speaker_lb.curselection()]
        if not to_speaker:
            self.statusbar["text"] = "No oscillators connected to speaker output!"
            return
        if not arpeggio:
            if released:
                # only stop sound immediately if no echo filter is enabled
                if not self.echos_ending_time:
                    self.stop_playing_note()
                return
            if not self.keypress_sema.acquire(blocking=False):
                self.statusbar["text"] = "can't play new note - previous one still playing (monophonic, sorry)"
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
        oscs = [self.create_osc(osc, self.oscillators, is_audio=True) for osc in to_speaker]
        mixed_osc = MixingFilter(*oscs) if len(oscs) > 1 else oscs[0]
        if not arpeggio:
            # at this time you can't use filters when using arpeggio
            mixed_osc = self.apply_filters(mixed_osc)
        current_echos_duration = getattr(mixed_osc, "echo_duration", 0)
        if current_echos_duration > 0:
            self.echos_ending_time = time.time() + current_echos_duration
        else:
            self.echos_ending_time = 0
        self.playing_note = True
        if arpeggio:
            # cycle the arp notes
            freqs.append(freqs[0])
            freqs = freqs[1:]
            rate = self.arp_filter.input_rate.get()
            duration = rate * self.arp_filter.input_ratio.get() / 100.0
            self.after_idle(lambda: self.render_and_play_note(iter(mixed_osc), max_duration=duration))
            self.after(int(rate*1000*0.95), lambda: self._pressed(freqs))
        else:
            # normal, single note
            self.output.wipe_queue()
            if self.rendering_choice.get() == "render":
                self.statusbar["text"] = "rendering note sample..."
                self.after_idle(lambda: self.render_and_play_note(iter(mixed_osc)))
                self.after_idle(lambda: self.stop_playing_note())
            else:
                self.after_idle(lambda: self.continue_play_note(iter(mixed_osc)))

    def apply_filters(self, output_oscillator):
        output_oscillator = self.tremolo_filter.filter(output_oscillator)
        output_oscillator = self.echo_filter.filter(output_oscillator)
        return output_oscillator

    def load_preset(self):
        file = askopenfile(filetypes=[("Synth presets", "*.ini")])
        cf = ConfigParser()
        cf.read_file(file)
        file.close()
        # general settings
        self.samplerate_choice.set(cf["settings"]["samplerate"])
        self.rendering_choice.set(cf["settings"]["rendering"])
        self.a4_choice.set(cf["settings"]["a4tuning"])
        self.to_speaker_lb.selection_clear(0, tk.END)
        to_speaker = cf["settings"]["to_speaker"]
        to_speaker = tuple(to_speaker.split(','))
        for o in to_speaker:
            self.to_speaker_lb.selection_set(int(o)-1)
        for section in cf.sections():
            if section.startswith("oscillator"):
                num = int(section.split('_')[1])-1
                osc = self.oscillators[num]
                for name, value in cf[section].items():
                    getattr(osc, name).set(value)
                osc.waveform_selected()
            elif section.startswith("envelope"):
                num = int(section.split('_')[1])-1
                env = self.envelope_filters[num]
                for name, value in cf[section].items():
                    getattr(env, name).set(value)
            elif section == "arpeggio":
                for name, value in cf[section].items():
                    getattr(self.arp_filter, name).set(value)
            elif section == "tremolo":
                for name, value in cf[section].items():
                    getattr(self.tremolo_filter, name).set(value)
            elif section == "echo":
                for name, value in cf[section].items():
                    getattr(self.echo_filter, name).set(value)
        self.statusbar["text"] = "preset loaded."

    def save_preset(self):
        file = asksaveasfile(filetypes=[("Synth presets", "*.ini")])
        cf = ConfigParser(dict_type=collections.OrderedDict)
        # general settings
        cf.add_section("settings")
        cf["settings"]["samplerate"] = str(self.samplerate_choice.get())
        cf["settings"]["rendering"] = self.rendering_choice.get()
        cf["settings"]["to_speaker"] = ",".join(str(v+1) for v in self.to_speaker_lb.curselection())
        cf["settings"]["a4tuning"] = str(self.a4_choice.get())
        # oscillators
        for num, osc in enumerate(self.oscillators, 1):
            section = "oscillator_"+str(num)
            cf.add_section(section)
            for name, var in vars(osc).items():
                if name.startswith("input_"):
                    cf[section][name] = str(var.get())
        # adsr envelopes
        for num, filter in enumerate(self.envelope_filters, 1):
            section = "envelope_"+str(num)
            cf.add_section(section)
            for name, var in vars(filter).items():
                if name.startswith("input_"):
                    cf[section][name] = str(var.get())
        # echo
        cf.add_section("echo")
        for name, var in vars(self.echo_filter).items():
            if name.startswith("input_"):
                cf["echo"][name] = str(var.get())
        # tremolo
        cf.add_section("tremolo")
        for name, var in vars(self.tremolo_filter).items():
            if name.startswith("input_"):
                cf["tremolo"][name] = str(var.get())
        # arpeggio
        cf.add_section("arpeggio")
        for name, var in vars(self.arp_filter).items():
            if name.startswith("input_"):
                cf["arpeggio"][name] = str(var.get())

        cf.write(file)
        file.close()


if __name__ == "__main__":
    root = tk.Tk()
    app = SynthGUI(master=root)
    app.mainloop()
