"""
Jukebox Gui

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import sys
import signal
import os
import time
import math
import subprocess
import datetime
import configparser
from threading import Thread
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
import tkinter.messagebox
import tkinter.filedialog
from .backend import BACKEND_PORT
from synthesizer.streaming import AudiofileToWavStream, StreamMixer, VolumeFilter
from synthesizer.sample import Sample, LevelMeter
from synthesizer.playback import Output
import appdirs
import Pyro4
import Pyro4.errors
import Pyro4.futures

StreamMixer.buffer_size = 4096      # larger means less skips and less cpu usage but more latency and slower levelmeters

try:
    hqresample = AudiofileToWavStream.supports_hq_resample()
    if hqresample:
        print("Great, ffmpeg supports high quality resampling.")
    else:
        print("WARNING: ffmpeg isn't compiled with libsoxr, high quality resampling is not supported.")
except IOError:
    raise SystemExit("Cannot find the ffmpeg and ffprobe executables. They have to be installed on the search path.")


class Player:
    update_rate = 50    # 50 ms = 20 updates/sec
    levelmeter_lowest = -40  # dB
    xfade_duration = 7
    async_buffers = 4

    def __init__(self, app, trackframes):
        self.app = app
        self.trackframes = trackframes
        self.app.after(self.update_rate, self.tick)
        self.stopping = False
        self.mixer = StreamMixer([], endless=True)
        self.output = Output(self.mixer.samplerate, self.mixer.samplewidth, self.mixer.nchannels, queuesize=self.async_buffers)
        self.mixed_samples = iter(self.mixer)
        self.levelmeter = LevelMeter(rms_mode=False, lowest=self.levelmeter_lowest)
        self.output.register_notify_played(self.levelmeter.update)
        for tf in self.trackframes:
            tf.player = self
        player_thread = Thread(target=self._play_sample_in_thread, name="jukebox_sampleplayer")
        player_thread.daemon = True
        player_thread.start()

    def skip(self, trackframe):
        if trackframe.state != TrackFrame.state_needtrack and trackframe.stream:
            trackframe.stream.close()
            trackframe.stream = None
        trackframe.display_track(None, None, None, "(next track...)")
        trackframe.state = TrackFrame.state_switching

    def stop(self):
        self.stopping = True
        for tf in self.trackframes:
            if tf.stream:
                tf.stream.close()
                tf.stream = None
            tf.state = TrackFrame.state_needtrack
        self.mixer.close()
        self.output.close()

    def tick(self):
        # the actual decoding and sound playing is done in a background thread
        self._levelmeter()
        self._load_song()
        self._play_song()
        self._crossfade()
        if not self.stopping:
            self.app.after(self.update_rate, self.tick)

    def _play_sample_in_thread(self):
        """
        This is run in a background thread to avoid GUI interactions interfering with audio output.
        """
        while True:
            if self.stopping:
                break
            _, sample = next(self.mixed_samples)
            if sample and sample.duration > 0:
                self.output.play_sample(sample)
            else:
                self.levelmeter.reset()
                time.sleep(self.update_rate/1000*2)   # avoid hogging the cpu while no samples are played

    def _levelmeter(self):
        self.app.update_levels(self.levelmeter.level_left, self.levelmeter.level_right)

    def _load_song(self):
        if self.stopping:
            return   # make sure we don't load new songs when the player is shutting down
        for tf in self.trackframes:
            if tf.state == TrackFrame.state_needtrack:
                track = self.app.pop_playlist_track()
                if track:
                    tf.track = track
                    tf.state = TrackFrame.state_idle

    def _play_song(self):
        def start_stream(tf, filename, volume):
            def _start_from_thread():
                # start loading the track from a thread to avoid gui stutters when loading takes a bit of time
                tf.stream = AudiofileToWavStream(filename, hqresample=hqresample)
                self.mixer.add_stream(tf.stream, [tf.volumefilter])
                tf.playback_started = datetime.datetime.now()
                tf.state = TrackFrame.state_playing
                tf.volume = volume
            tf.state = TrackFrame.state_loading
            Thread(target=_start_from_thread, name="stream_loader").start()
        for tf in self.trackframes:
            if tf.state == TrackFrame.state_playing:
                remaining = tf.track_duration - (datetime.datetime.now() - tf.playback_started)
                remaining = remaining.total_seconds()
                tf.time = datetime.timedelta(seconds=math.ceil(remaining))
                if tf.stream.closed and tf.time.total_seconds() <= 0:
                    self.skip(tf)  # stream ended!
            elif tf.state == TrackFrame.state_idle:
                if tf.xfade_state == TrackFrame.state_xfade_fadingin:
                    # if we're set to fading in, regardless of other tracks, we start playing as well
                    start_stream(tf, tf.track["location"], 0)
                elif not any(tf for tf in self.trackframes if tf.state in (TrackFrame.state_playing, TrackFrame.state_loading)):
                    # if there is no other track currently playing (or loading), it's our turn!
                    start_stream(tf, tf.track["location"], 100)
            elif tf.state == TrackFrame.state_switching:
                tf.state = TrackFrame.state_needtrack

    def _crossfade(self):
        for tf in self.trackframes:
            # nearing the end of the track? then start a fade out
            if tf.state == TrackFrame.state_playing \
                    and tf.xfade_state == TrackFrame.state_xfade_nofade \
                    and tf.time.total_seconds() <= self.xfade_duration:
                tf.xfade_state = TrackFrame.state_xfade_fadingout
                tf.xfade_started = datetime.datetime.now()
                tf.xfade_start_volume = tf.volume
                # fade in the first other track that is currently idle
                for other_tf in self.trackframes:
                    if tf is not other_tf and other_tf.state == TrackFrame.state_idle:
                        other_tf.xfade_state = TrackFrame.state_xfade_fadingin
                        other_tf.xfade_started = datetime.datetime.now()
                        other_tf.xfade_start_volume = 0
                        other_tf.volume = 0
                        break
        for tf in self.trackframes:
            if tf.xfade_state == TrackFrame.state_xfade_fadingin:
                # fading in, slide volume up from 0 to 100%
                volume = 100 * (datetime.datetime.now() - tf.xfade_started).total_seconds() / self.xfade_duration
                tf.volume = min(volume, 100)
                if volume >= 100:
                    tf.xfade_state = TrackFrame.state_xfade_nofade  # fade reached the end
            elif tf.xfade_state == TrackFrame.state_xfade_fadingout:
                # fading out, slide volume down from what it was at to 0%
                fade_progress = (datetime.datetime.now() - tf.xfade_started)
                fade_progress = (self.xfade_duration - fade_progress.total_seconds()) / self.xfade_duration
                volume = max(0, tf.xfade_start_volume * fade_progress)
                tf.volume = max(volume, 0)
                if volume <= 0:
                    tf.xfade_state = TrackFrame.state_xfade_nofade   # fade reached the end

    def play_sample(self, sample):
        def unmute(trf, vol):
            if trf:
                trf.volume=vol
        if sample and sample.duration > 0:
            for tf in self.trackframes:
                if tf.state == TrackFrame.state_playing:
                    old_volume = tf.mute_volume(40)
                    self.mixer.add_sample(sample, lambda mtf=tf, vol=old_volume: unmute(mtf, vol))
                    break
            else:
                self.mixer.add_sample(sample)


class TrackFrame(ttk.LabelFrame):
    state_idle = 1
    state_playing = 2
    state_needtrack = 3
    state_switching = 4
    state_loading = 5
    state_xfade_nofade = 0
    state_xfade_fadingout = 1
    state_xfade_fadingin = 2

    def __init__(self, master, title):
        self.title = title
        super().__init__(master, text=title, padding=4)
        self.player = None   # will be connected later
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
        scale.bind("<Double-1>", self.on_dblclick_vol)
        scale.pack(side=tk.LEFT)
        self.volumeLabel = ttk.Label(f, text="???%")
        self.volumeLabel.pack(side=tk.RIGHT)
        f.pack(fill=tk.X)
        ttk.Button(self, text="Skip", command=lambda s=self: s.player.skip(s)).pack(pady=4)
        self.volume = 100
        self.stateLabel = tk.Label(self, text="STATE", relief=tk.SUNKEN, border=1)
        self.stateLabel.pack()
        self._track = None
        self._time = None
        self._stream = None
        self._state = self.state_needtrack
        self.state = self.state_needtrack
        self.xfade_state = self.state_xfade_nofade
        self.xfade_started = None
        self.xfade_start_volume = None
        self.playback_started = None
        self.track_duration = None

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        if self.state == self.state_idle:
            self.stateLabel.configure(text=" Waiting ", bg="white", fg="black")
        elif self.state == self.state_loading:
            self.stateLabel.configure(text=" Loading ", bg="white", fg="black")
        elif self.state == self.state_playing:
            self.stateLabel.configure(text=" Playing ", bg="light green", fg="black")
        elif self.state in (self.state_needtrack, self.state_switching):
            self.stateLabel.configure(text=" Needs Track ", bg="red", fg="white")

    @property
    def track(self):
        return self._track

    @track.setter
    def track(self, value):
        self._track = value
        self.display_track(value["title"], value["artist"], value["album"], value["duration"])
        self.track_duration = datetime.timedelta(seconds=value["duration"])
        self.time = self.track_duration

    @property
    def time(self):
        return self._time

    @time.setter
    def time(self, value):
        if type(value) in (float, int):
            value = datetime.timedelta(seconds=math.ceil(value))
        if type(value) is not datetime.timedelta:
            raise TypeError("time should be a datetime.timedelta, or number of seconds. It was:", type(value))
        self._time = value
        self.timeleftLabel["text"] = value

    @property
    def stream(self):
        return self._stream

    @stream.setter
    def stream(self, value):
        self._stream = value
        if value and value.format_probe and value.format_probe.duration:
            # get the duration from the stream itself (more precise)
            self.time = value.format_probe.duration

    def display_track(self, title, artist, album, duration):
        self.titleLabel["text"] = title or "-"
        self.artistLabel["text"] = artist or "-"
        self.albumlabel["text"] = album or "-"
        if type(duration) in (float, int):
            duration = datetime.timedelta(seconds=math.ceil(duration))
        self.timeleftLabel["text"] = duration

    def on_volumechange(self, value):
        value = float(value)
        self.volumefilter.volume = value / 100.0
        self.volumeLabel["text"] = "{:.0f}%".format(value)

    def on_dblclick_vol(self, event):
        self.volume = 100

    @property
    def volume(self):
        return int(self.volumeVar.get())

    @volume.setter
    def volume(self, value):
        self.volumeVar.set(value)
        self.on_volumechange(value)

    def mute_volume(self, maxvolume):
        old_volume = self.volumeVar.get()
        self.volume = min(maxvolume, self.volumeVar.get())
        return old_volume


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
            datetime.timedelta(seconds=math.ceil(track["duration"])),
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
                datetime.timedelta(seconds=math.ceil(track["duration"]))])
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


class BackendGui(tkinter.Toplevel):
    def __init__(self, master, title, backend):
        super().__init__(master)
        self.geometry("+400+400")
        self.title(title)
        f = ttk.LabelFrame(self, text="Stats")
        ttk.Label(f, text="Connected to Database backend at: "+backend._pyroUri.location).pack()
        statstext = "Number of tracks in database: {0} -- Total playing time: {1}".format(backend.num_tracks, datetime.timedelta(seconds=backend.total_playtime))
        ttk.Label(f, text=statstext).pack()
        f.pack()
        ttk.Label(self, text="Adding tracks etc. is done via the command-line interface for now.\n"
                             "Type 'help' in the console there to see the commands available.").pack()
        ttk.Button(self, text="Ok", command=self.destroy).pack()


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
        self.firstTrackFrame = TrackFrame(f1, "Track 1")
        self.secondTrackFrame = TrackFrame(f1, "Track 2")
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
        optionsFrame = ttk.Frame(f3)
        ttk.Button(optionsFrame, text="Database Config", command=self.do_database_config).pack()
        optionsFrame.pack(side=tk.LEFT)
        self.effectsFrame = EffectsFrame(self, f3)
        self.effectsFrame.pack()
        f3.pack(side=tk.TOP)
        self.statusbar = ttk.Label(f, text="<status>", relief=tk.GROOVE, anchor=tk.CENTER)
        self.statusbar.pack(fill=tk.X, expand=True)
        f.pack()
        self.player = Player(self, (self.firstTrackFrame, self.secondTrackFrame))
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

    def connect_backend(self, try_nameserver = True):
        def backend_connected(backend):
            playtime = datetime.timedelta(seconds=backend.total_playtime)
            status = "Connected to backend @ {0:s} | number of tracks: {1:d} | total playtime: {2}"\
                     .format(backend._pyroUri.location, backend.num_tracks, playtime)
            self.show_status(status, 5)
        if try_nameserver:
            # first try if we can find a backend in a name server somewhere
            self.backend = Pyro4.Proxy("PYRONAME:jukebox.backend")
            try:
                self.backend._pyroBind()
                return backend_connected(self.backend)
            except Pyro4.errors.PyroError:
                pass
        try:
            # try a local backend
            self.backend = Pyro4.Proxy("PYRO:jukebox.backend@localhost:{0}".format(BACKEND_PORT))
            self.backend._pyroBind()
            return backend_connected(self.backend)
        except Exception as x:
            self.show_status("ERROR! Connection to backend failed: "+str(x))
            answer = tkinter.messagebox.askokcancel("Connect backend", "Cannot connect to backend. Maybe it is not started.\n\nDo you want me to start the backend server?")
            if answer:
                p = subprocess.Popen([sys.executable, "-m", "jukebox.backend", "-noscan", "-localhost"])
                self.backend_process = p.pid
                self.after(2000, self.connect_backend, False)

    def enqueue(self, track):
        self.playlistFrame.enqueue(track)

    def pop_playlist_track(self, peek=False):
        hashcode = self.playlistFrame.peek() if peek else self.playlistFrame.pop()
        if hashcode:
            return self.backend.track(hashcode)
        return None

    def update_levels(self, left, right):
        self.levelmeterFrame.update_meters(left, right)

    def play_sample(self, sample):
        self.player.play_sample(sample)

    def do_database_config(self):
        bg = BackendGui(self, "Jukebox - Backend Config", self.backend)
        # make it a modal window and wait till it is closed:
        bg.transient(self)
        bg.grab_set()
        self.wait_window(bg)


if __name__ == "__main__":
    app = JukeboxGui()
    app.mainloop()
