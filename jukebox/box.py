"""
Jukebox Gui

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import sys
import signal
import os
import subprocess
import datetime
import configparser
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
import tkinter.messagebox
import tkinter.filedialog
from .backend import BACKEND_PORT
from synthesizer.streaming import AudiofileToWavStream, StreamMixer, VolumeFilter
from synthesizer.sample import Sample, Output, LevelMeter
import appdirs
import Pyro4
import Pyro4.errors
import Pyro4.futures

StreamMixer.buffer_size = 4096      # larger is less skips and less cpu usage but more latency and slower meters
hqresample = AudiofileToWavStream.supports_hq_resample()
if not hqresample:
    print("WARNING: ffmpeg isn't compiled with libsoxr, so hq resampling is not supported.")


class Player:
    async_queue_size = 3     # larger is less chance of getting skips, but latency increases
    update_rate = 40         # larger is less cpu usage but more chance of getting skips
    levelmeter_lowest = -40  # dB

    def __init__(self, app):
        self.app = app
        self.app.after(self.update_rate, self.tick)
        self.stopping = False
        self.mixer = StreamMixer([], endless=True)
        self.output = Output(self.mixer.samplerate, self.mixer.samplewidth, self.mixer.nchannels, queuesize=self.async_queue_size)
        self.mixed_samples = iter(self.mixer)
        self.levelmeter = LevelMeter(rms_mode=False, lowest=self.levelmeter_lowest)

    def stop(self):
        self.stopping = True
        self.mixer.close()
        self.output.close()

    def tick(self):
        if self.output.queue_size() <= self.async_queue_size/2:
            _, sample = next(self.mixed_samples)
            if sample and sample.duration > 0:
                self.output.play_sample(sample, async=True)
                left, _, right, _ = self.levelmeter.update(sample)
                self.app.update_levels(left, right)
            else:
                self.levelmeter.reset()
                self.app.update_levels(self.levelmeter.level_left, self.levelmeter.level_right)
        if not self.stopping:
            self.app.after(self.update_rate, self.tick)

    def play_sample(self, sample):
        if sample and sample.duration > 0:
            self.mixer.add_sample(sample)


class TrackFrame(ttk.LabelFrame):
    state_idle = 1
    state_playing = 2
    state_needtrack = 3

    def __init__(self, app, master, title):
        self.title = title
        super().__init__(master, text=title, padding=4)
        self.app = app
        self.volumeVar = tk.DoubleVar(value=100)
        self.volumefilter = VolumeFilter()
        ttk.Label(self, text="title / artist / album").pack()
        self.titleLabel = ttk.Label(self, relief=tk.GROOVE, width=22, anchor=tk.W)
        self.titleLabel.pack()
        self.artistLabel = ttk.Label(self, relief=tk.GROOVE, width=22, anchor=tk.W)
        self.artistLabel.pack()
        self.albumlabel = ttk.Label(self, relief=tk.GROOVE, width=22, anchor=tk.W)
        self.albumlabel.pack()
        f = ttk.Frame(self)
        ttk.Label(f, text="time left: ").pack(side=tk.LEFT)
        self.timeleftLabel = ttk.Label(f, relief=tk.GROOVE, anchor=tk.CENTER)
        self.timeleftLabel.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        f.pack(fill=tk.X)
        f = ttk.Frame(self)
        ttk.Label(f, text="V: ").pack(side=tk.LEFT)
        scale = ttk.Scale(f, from_=0, to=150, length=120, variable=self.volumeVar, command=self.on_volumechange)
        scale.bind("<Double-1>", lambda event: self.set_volume(100))
        scale.pack(side=tk.LEFT)
        self.volumeLabel = ttk.Label(f, text="???%")
        self.volumeLabel.pack(side=tk.RIGHT)
        f.pack(fill=tk.X)
        ttk.Button(self, text="Skip", command=self.skip).pack(pady=4)
        self.set_volume(100)
        self.stateLabel = tk.Label(self, text="STATE", relief=tk.SUNKEN, border=1)
        self.stateLabel.pack()
        self.display_state(self.state_idle)

    def skip(self):
        self.display_track(None, None, None, "(next track...)")
        # @todo actually stop playing and switch to other track player

    def display_track(self, title, artist, album, duration):
        self.titleLabel["text"] = title or "-"
        self.artistLabel["text"] = artist or "-"
        self.albumlabel["text"] = album or "-"
        if type(duration) in (float, int):
            duration = datetime.timedelta(seconds=int(duration))
        self.timeleftLabel["text"] = duration

    def on_volumechange(self, value):
        value = float(value)
        self.volumefilter.volume = value / 100.0
        self.volumeLabel["text"] = "{:.0f}%".format(value)

    def set_volume(self, volume):
        self.volumeVar.set(volume)
        self.on_volumechange(volume)

    def display_state(self, state):
        if state == self.state_idle:
            self.stateLabel.configure(text=" Waiting ", bg="white", fg="black")
        elif state == self.state_playing:
            self.stateLabel.configure(text=" Playing ", bg="light green", fg="black")
        elif state == self.state_needtrack:
            self.stateLabel.configure(text=" Needs Track ", bg="red", fg="white")


class LevelmeterFrame(ttk.LabelFrame):
    def __init__(self, master):
        super().__init__(master, text="Levels", padding=4)
        self.lowest_level = Player.levelmeter_lowest
        self.pbvar_left = tk.IntVar()
        self.pbvar_right = tk.IntVar()
        pbstyle = ttk.Style()
        # pbstyle.theme_use("classic")  # clam, alt, default, classic
        pbstyle.configure("green.Vertical.TProgressbar", troughcolor="gray", background="light green")
        pbstyle.configure("yellow.Vertical.TProgressbar", troughcolor="gray", background="yellow")
        pbstyle.configure("red.Vertical.TProgressbar", troughcolor="gray", background="orange")

        ttk.Label(self, text="dB").pack(side=tkinter.TOP)
        frame = ttk.LabelFrame(self, text="L.")
        frame.pack(side=tk.LEFT)
        self.pb_left = ttk.Progressbar(frame, orient=tk.VERTICAL, length=200, maximum=-self.lowest_level, variable=self.pbvar_left, mode='determinate', style='yellow.Vertical.TProgressbar')
        self.pb_left.pack()

        frame = ttk.LabelFrame(self, text="R.")
        frame.pack(side=tk.LEFT)
        self.pb_right = ttk.Progressbar(frame, orient=tk.VERTICAL, length=200, maximum=-self.lowest_level, variable=self.pbvar_right, mode='determinate', style='yellow.Vertical.TProgressbar')
        self.pb_right.pack()

    def update_meters(self, left, right):
        self.pbvar_left.set(left-self.lowest_level)
        self.pbvar_right.set(right-self.lowest_level)
        if left > -3:
            self.pb_left.configure(style="red.Vertical.TProgressbar")
        elif left > -6:
            self.pb_left.configure(style="yellow.Vertical.TProgressbar")
        else:
            self.pb_left.configure(style="green.Vertical.TProgressbar")
        if right > -3:
            self.pb_right.configure(style="red.Vertical.TProgressbar")
        elif right > -6:
            self.pb_right.configure(style="yellow.Vertical.TProgressbar")
        else:
            self.pb_right.configure(style="green.Vertical.TProgressbar")


class PlaylistFrame(ttk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Playlist", padding=4)
        self.app = app
        bf = ttk.Frame(self)
        ttk.Button(bf, text="Move to Top", width=11, command=self.do_to_top).pack()
        ttk.Button(bf, text="Move Up", width=11, command=self.do_move_up).pack()
        ttk.Button(bf, text="Move Down", width=11, command=self.do_move_down).pack()
        ttk.Button(bf, text="Remove", width=11, command=self.do_remove).pack()
        bf.pack(side=tk.LEFT, padx=4)
        sf = ttk.Frame(self)
        cols = [("title", 300), ("artist", 180), ("album", 180), ("length", 60)]
        self.listTree = ttk.Treeview(sf, columns=[col for col, _ in cols], height=10, show="headings")
        vsb = ttk.Scrollbar(orient="vertical", command=self.listTree.yview)
        self.listTree.configure(yscrollcommand=vsb.set)
        self.listTree.grid(column=1, row=0, sticky=tk.NSEW, in_=sf)
        vsb.grid(column=0, row=0, sticky=tk.NS, in_=sf)
        for col, colwidth in cols:
            self.listTree.heading(col, text=col.title())
            self.listTree.column(col, width=colwidth)
        sf.grid_columnconfigure(0, weight=1)
        sf.grid_rowconfigure(0, weight=1)
        sf.pack(side=tk.LEFT, padx=4)

    def pop(self):
        items = self.listTree.get_children()
        if items:
            top_item = items[0]
            hashcode = self.listTree.item(top_item, "values")[4]
            self.listTree.delete(top_item)
            return hashcode
        return None

    def peek(self):
        items = self.listTree.get_children()
        if items:
            return self.listTree.item(items[0], "values")[4]
        return None

    def do_to_top(self):
        sel = self.listTree.selection()
        if sel:
            s = sel[0]
            self.listTree.move(s, self.listTree.parent(s), 0)

    def do_remove(self):
        sel = self.listTree.selection()
        if sel:
            self.listTree.delete(*sel)

    def do_move_up(self):
        sel = self.listTree.selection()
        if sel:
            for s in sel:
                idx = self.listTree.index(s)
                self.listTree.move(s, self.listTree.parent(s), idx-1)

    def do_move_down(self):
        sel = self.listTree.selection()
        if sel:
            for s in sel:
                idx = self.listTree.index(s)
                self.listTree.move(s, self.listTree.parent(s), idx+1)

    def enqueue(self, track):
        self.listTree.insert("", tk.END, values=[
            track["title"] or '-',
            track["artist"] or '-',
            track["album"] or '-',
            datetime.timedelta(seconds=int(track["duration"])),
            track["hash"]])


class SearchFrame(ttk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Search song", padding=4)
        self.app = app
        self.search_text = tk.StringVar()
        self.filter_choice = tk.StringVar(value="title")
        bf = ttk.Frame(self)
        ttk.Label(bf, text="Search for:").pack()
        e = ttk.Entry(bf, textvariable=self.search_text)
        e.bind("<Return>", self.do_search)
        e.bind("<KeyRelease>", self.on_key_up)
        self.search_job = None
        e.pack()
        ttk.Radiobutton(bf, text="title", value="title", variable=self.filter_choice, width=10).pack()
        ttk.Radiobutton(bf, text="artist", value="artist", variable=self.filter_choice, width=10).pack()
        ttk.Radiobutton(bf, text="album", value="album", variable=self.filter_choice, width=10).pack()
        ttk.Radiobutton(bf, text="year", value="year", variable=self.filter_choice, width=10).pack()
        ttk.Radiobutton(bf, text="genre", value="genre", variable=self.filter_choice, width=10).pack()
        ttk.Button(bf, text="Search", command=self.do_search).pack()
        ttk.Button(bf, text="Add all selected", command=self.do_add_selected).pack()
        bf.pack(side=tk.LEFT)
        sf = ttk.Frame(self)
        cols = [("title", 320), ("artist", 200), ("album", 200), ("year", 50), ("genre", 120), ("length", 60)]
        self.resultTreeView = ttk.Treeview(sf, columns=[col for col, _ in cols], height=11, show="headings")
        vsb = ttk.Scrollbar(orient="vertical", command=self.resultTreeView.yview)
        self.resultTreeView.configure(yscrollcommand=vsb.set)
        self.resultTreeView.grid(column=1, row=0, sticky=tk.NSEW, in_=sf)
        vsb.grid(column=0, row=0, sticky=tk.NS, in_=sf)
        for col, colwidth in cols:
            self.resultTreeView.heading(col, text=col.title(), command=lambda c=col: self.sortby(self.resultTreeView, c, 0))
            self.resultTreeView.column(col, width=colwidth)
        self.resultTreeView.bind("<Double-1>", self.on_doubleclick)
        sf.grid_columnconfigure(0, weight=1)
        sf.grid_rowconfigure(0, weight=1)
        sf.pack(side=tk.LEFT, padx=4)

    def on_key_up(self, event):
        if self.search_job:
            self.after_cancel(self.search_job)
        self.search_job = self.after(600, self.do_search)

    def on_doubleclick(self, event):
        sel = self.resultTreeView.selection()
        if not sel:
            return
        track_hash = sel[0]
        track = self.app.backend.track(hashcode=track_hash)
        self.app.enqueue(track)

    def do_add_selected(self):
        sel = self.resultTreeView.selection()
        if not sel:
            return
        for track_hash in sel:
            track = self.app.backend.track(hashcode=track_hash)
            self.app.enqueue(track)

    def sortby(self, tree, col, descending):
        # grab values to sort and sort in place
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        data.sort(reverse=descending)
        for ix, item in enumerate(data):
            tree.move(item[1], '', ix)
        # switch the heading so it will sort in the opposite direction next time
        tree.heading(col, command=lambda col=col: self.sortby(tree, col, int(not descending)))

    def do_search(self, event=None):
        search_text = self.search_text.get().strip()
        if not search_text:
            return
        self.app.show_status("Searching...")
        for i in self.resultTreeView.get_children():
            self.resultTreeView.delete(i)
        queryinfo = {self.filter_choice.get(): search_text}
        try:
            result = self.app.backend.query(**queryinfo)
        except Exception as x:
            self.app.show_status("ERROR: "+str(x))
            return
        result = sorted(result, key=lambda track: (track["title"], track["artist"] or "", track["album"] or "", track["year"] or 0, track["genre"] or ""))
        for track in result:
            self.resultTreeView.insert("", tk.END, iid=track["hash"], values=[
                track["title"] or '-',
                track["artist"] or '-',
                track["album"] or '-',
                track["year"] or '-',
                track["genre"] or '-',
                datetime.timedelta(seconds=int(track["duration"]))])
        self.app.show_status("{:d} results found".format(len(result)), 3)


class EffectsFrame(ttk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Effects/Samples - shift+click to assign sample", padding=4)
        self.app = app
        self.effects = {num: None for num in range(16)}
        f = ttk.Frame(self)
        self.buttons = []
        for i in range(1, 9):
            b = ttk.Button(f, text="# {:d}".format(i), width=14, state=tk.DISABLED)
            b.bind("<ButtonRelease>", self.do_button_release)
            b.effect_nr = i
            b.pack(side=tk.LEFT)
            self.buttons.append(b)
        f.pack()
        f = ttk.Frame(self)
        for i in range(9, 17):
            b = ttk.Button(f, text="# {:d}".format(i), width=14, state=tk.DISABLED)
            b.bind("<ButtonRelease>", self.do_button_release)
            b.effect_nr = i
            b. pack(side=tk.LEFT)
            self.buttons.append(b)
        f.pack()
        self.after(2000, lambda: Pyro4.Future(self.load_settings)(True))

    def do_button_release(self, event):
        if event.state & 0x0100 == 0:
            return  # no left mouse button event
        shift = event.state & 0x0001
        if shift:
            filename = tkinter.filedialog.askopenfilename()
            if filename:
                self.set_effect(event.widget.effect_nr, filename)
                self.update_settings(event.widget.effect_nr, filename)
        else:
            sample = self.effects[event.widget.effect_nr]
            if sample:
                self.app.play_sample(sample)

    def load_settings(self, load_samples=False):
        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(self.app.config_location, "soundeffects.ini"))
        if load_samples and cfg.has_section("Effects"):
            self.app.show_status("Loading effect samples...")
            for button in self.buttons:
                filename = cfg["Effects"].get("e"+str(button.effect_nr))
                if filename:
                    self.set_effect(button.effect_nr, filename)
            self.app.show_status("Ready.")
        return cfg

    def set_effect(self, effect_nr, filename):
        try:
            with AudiofileToWavStream(filename, hqresample=hqresample) as wav:
                sample = Sample(wav)
                self.effects[effect_nr] = sample
        except IOError as x:
            print("Can't load effect sample:", x)
        else:
            for button in self.buttons:
                if button.effect_nr == effect_nr:
                    button["state"] = tk.NORMAL
                    button["text"] = os.path.splitext(os.path.basename(filename))[0]
                    break

    def update_settings(self, effect_nr, filename):
        cfg = self.load_settings()
        if not cfg.has_section("Effects"):
            cfg.add_section("Effects")
        cfg["Effects"]["e"+str(effect_nr)] = filename or ""
        with open(os.path.join(self.app.config_location, "soundeffects.ini"), "w") as fp:
            cfg.write(fp)


class JukeboxGui(tk.Tk):
    def __init__(self):
        super().__init__()
        self.config_location = appdirs.user_data_dir("PythonJukebox", "Razorvine")
        os.makedirs(self.config_location, mode=0o700, exist_ok=True)
        default_font = tk.font.nametofont("TkDefaultFont")
        default_font["size"] = abs(default_font["size"])+2
        default_font = tk.font.nametofont("TkTextFont")
        default_font["size"] = abs(default_font["size"])+2
        self.title("Jukebox")
        f = ttk.Frame()
        f1 = ttk.Frame(f)
        self.firstTrackFrame = TrackFrame(self, f1, "Track 1")
        self.secondTrackFrame = TrackFrame(self, f1, "Track 2")
        self.levelmeterFrame = LevelmeterFrame(f1)
        self.playlistFrame = PlaylistFrame(self, f1)
        self.firstTrackFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.secondTrackFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.levelmeterFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.playlistFrame.pack(side=tk.LEFT, fill=tk.Y)
        f1.pack(side=tk.TOP)
        f2 = ttk.Frame(f)
        self.searchFrame = SearchFrame(self, f2)
        self.searchFrame.pack()
        f2.pack(side=tk.TOP)
        f3 = ttk.Frame(f)
        self.effectsFrame = EffectsFrame(self, f3)
        self.effectsFrame.pack()
        f3.pack(side=tk.TOP)
        self.statusbar = ttk.Label(f, text="<status>", relief=tk.GROOVE, anchor=tk.CENTER)
        self.statusbar.pack(fill=tk.X, expand=True)
        f.pack()
        self.player = Player(self)
        self.backend = None
        self.backend_process = None
        self.show_status("Connecting to backend file service...")
        self.after(500, self.connect_backend)

    def destroy(self):
        self.player.stop()
        super().destroy()
        if self.backend_process:
            print("\n")
            if hasattr(signal, "SIGINT"):
                os.kill(self.backend_process, signal.SIGINT)
            else:
                os.kill(self.backend_process, signal.SIGTERM)
        try:
            import tty
            os.system("stty sane")   # sometimes needed because spawning ffmpeg sometimes breaks the terminal...
        except ImportError:
            pass

    def show_status(self, statustext, duration=None):
        def reset_status(text):
            self.statusbar["text"] = text
        reset_status(statustext)
        if duration and duration > 0:
            self.after(duration*1000, lambda: reset_status("Ready."))

    def connect_backend(self):
        try:
            self.backend = Pyro4.Proxy("PYRO:jukebox.backend@localhost:{0}".format(BACKEND_PORT))
            self.backend._pyroBind()
            playtime = datetime.timedelta(seconds=self.backend.total_playtime)
            status = "Connected to backend @ {0:s} | number of tracks: {1:d} | total playtime: {2}"\
                     .format(self.backend._pyroUri.location, self.backend.num_tracks, playtime)
            self.show_status(status, 5)
        except Exception as x:
            self.show_status("ERROR! Connection to backend failed: "+str(x))
            answer = tkinter.messagebox.askokcancel("Connect backend", "Cannot connect to backend. Maybe it is not started.\n\nDo you want me to start the backend server?")
            if answer:
                p = subprocess.Popen([sys.executable, "-m", "jukebox.backend", "-noscan"])
                self.backend_process = p.pid
                self.after(2000, self.connect_backend)

    def enqueue(self, track):
        self.playlistFrame.enqueue(track)

    def upcoming_track_hash(self, peek=False):
        if peek:
            return self.playlistFrame.peek()
        return self.playlistFrame.pop()

    def update_levels(self, left, right):
        self.levelmeterFrame.update_meters(left, right)

    def play_sample(self, sample):
        self.player.play_sample(sample)


if __name__ == "__main__":
    app = JukeboxGui()
    app.mainloop()
