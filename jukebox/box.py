"""
Jukebox Gui

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import datetime
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
import tkinter.messagebox
import tkinter.filedialog
from .backend import BACKEND_PORT
from .streaming import AudiofileToWavStream, StreamMixer
from synthesizer.sample import Sample, Output, LevelMeter
import Pyro4
import Pyro4.errors


StreamMixer.buffer_size = 4096      # larger is less skips and less cpu usage but more latency and slower meters


class Player:
    async_queue_size = 3     # larger is less chance of getting skips, but latency increases
    update_rate = 40         # larger is less cpu usage but more chance of getting skips
    levelmeter_lowest = -40  # dB
    def __init__(self, app):
        self.app = app
        self.app.after(self.update_rate, self.tick)
        self.app.firstTrackFrame.play()
        self.stopping = False
        self.mixer = StreamMixer([], endless=True)
        self.output = Output(self.mixer.samplerate, self.mixer.samplewidth, self.mixer.nchannels, queuesize=self.async_queue_size)
        self.mixed_samples = iter(self.mixer)
        self.levelmeter = LevelMeter(rms_mode=False, lowest=self.levelmeter_lowest)

    def stop(self):
        self.stopping = True
        self.app.firstTrackFrame.close_stream()
        self.app.secondTrackFrame.close_stream()
        self.mixer.close()
        self.output.close()

    def switch_player(self):
        first_is_playing = self.app.firstTrackFrame.playing
        self.app.firstTrackFrame.play(not first_is_playing)
        self.app.secondTrackFrame.play(first_is_playing)
        self.mixer.timestamp = 0.0

    def tick(self):
        if self.output.queue_size() <= self.async_queue_size/2:
            timestamp, sample = next(self.mixed_samples)
            self.app.firstTrackFrame.tick(self.mixer, timestamp)
            self.app.secondTrackFrame.tick(self.mixer, timestamp)
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


class TrackFrame(tk.LabelFrame):
    def __init__(self, app, master, title):
        self.title = title
        self.playing = False
        super().__init__(master, text=title, border=4, padx=4, pady=4)
        self.app = app
        self.current_track = None
        self.current_track_filename = None
        self.current_track_duration = None
        self.stream = None
        tk.Label(self, text="title").pack()
        self.titleLabel = tk.Label(self, relief=tk.RIDGE, width=22, anchor=tk.W)
        self.titleLabel.pack()
        tk.Label(self, text="artist").pack()
        self.artistLabel = tk.Label(self, relief=tk.RIDGE, width=22, anchor=tk.W)
        self.artistLabel.pack()
        tk.Label(self, text="album").pack()
        self.albumlabel = tk.Label(self, relief=tk.RIDGE, width=22, anchor=tk.W)
        self.albumlabel.pack()
        tk.Label(self, text="time left").pack()
        self.timeleftLabel = tk.Label(self, relief=tk.RIDGE, width=14)
        self.timeleftLabel.pack()
        tk.Button(self, text="Skip", command=self.skip).pack(pady=4)

    def play(self, playing=True):
        self["text"] = self.title + (" [PLAYING]" if playing else "")
        self.playing = playing

    def skip(self):
        if self.playing:
            self.app.switch_player()
        self.close_stream()
        self.titleLabel["text"] = ""
        self.artistLabel["text"] = ""
        self.albumlabel["text"] = ""
        self.timeleftLabel["text"] = "(next track...)"

    def tick(self, mixer, player_timestamp):
        # if we don't have a track, try go get the next one from the playlist
        if self.current_track is None:
            track = self.app.upcoming_track_hash()
            if track:
                self.next_track(track)
                self["bg"] = self.master.cget("bg")
            else:
                self["bg"] = "yellow"
        if self.playing and self.current_track:
            # update duration timer
            remaining = self.current_track_duration - player_timestamp
            self.timeleftLabel["text"] = datetime.timedelta(seconds=int(remaining))
            # when it is time, load the track and add its stream to the mixer
            if not self.stream:
                self.stream = AudiofileToWavStream(self.current_track_filename)
                self["bg"] = "light green" if self.playing else self.master.cget("bg")
                mixer.add_stream(self.stream)
                if self.stream.format_probe and self.stream.format_probe.duration and not self.current_track_duration:
                    # get the duration from the stream itself
                    self.current_track_duration = self.stream.format_probe.duration

    def close_stream(self):
        self.current_track = None
        if self.stream:
            self.stream.close()
            self.stream = None

    def next_track(self, hashcode):
        if self.stream:
            self.stream.close()
            self.stream = None
        self.current_track = hashcode
        track = self.app.backend.track(hashcode=self.current_track)
        self.titleLabel["text"] = track["title"] or "-"
        self.artistLabel["text"] = track["artist"] or "-"
        self.albumlabel["text"] = track["album"] or "-"
        self.timeleftLabel["text"] = datetime.timedelta(seconds=int(track["duration"]))
        self.current_track_filename = track["location"]
        self.current_track_duration =  track["duration"]


class LevelmeterFrame(tk.LabelFrame):
    def __init__(self, master):
        super().__init__(master, text="Levels", border=4, padx=4, pady=4)
        self.lowest_level = Player.levelmeter_lowest
        self.pbvar_left = tk.IntVar()
        self.pbvar_right = tk.IntVar()
        pbstyle = ttk.Style()
        pbstyle.theme_use("classic")
        pbstyle.configure("green.Vertical.TProgressbar", troughcolor="gray", background="light green")
        pbstyle.configure("yellow.Vertical.TProgressbar", troughcolor="gray", background="yellow")
        pbstyle.configure("red.Vertical.TProgressbar", troughcolor="gray", background="orange")

        frame = tk.LabelFrame(self, text="Left")
        frame.pack(side=tk.LEFT)
        tk.Label(frame, text="dB").pack()
        self.pb_left = ttk.Progressbar(frame, orient=tk.VERTICAL, length=190, maximum=-self.lowest_level, variable=self.pbvar_left, mode='determinate', style='yellow.Vertical.TProgressbar')
        self.pb_left.pack()

        frame = tk.LabelFrame(self, text="Right")
        frame.pack(side=tk.LEFT)
        tk.Label(frame, text="dB").pack()
        self.pb_right = ttk.Progressbar(frame, orient=tk.VERTICAL, length=190, maximum=-self.lowest_level, variable=self.pbvar_right, mode='determinate', style='yellow.Vertical.TProgressbar')
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


class PlaylistFrame(tk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Playlist", border=4, padx=4, pady=4)
        self.app = app
        bf = tk.Frame(self)
        tk.Button(bf, text="Move to Top", command=self.do_to_top).pack()
        tk.Button(bf, text="Move Up", command=self.do_move_up).pack()
        tk.Button(bf, text="Move Down", command=self.do_move_down).pack()
        tk.Button(bf, text="Remove", command=self.do_remove).pack()
        bf.pack(side=tk.LEFT, padx=4)
        sf = tk.Frame(self)
        cols = [("title", 320), ("artist", 200), ("album", 200)]
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
            hashcode = self.listTree.item(top_item, "values")[3]
            self.listTree.delete(top_item)
            return hashcode
        return None

    def peek(self):
        items = self.listTree.get_children()
        if items:
            return self.listTree.item(items[0], "values")[3]
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
            track["hash"]])


class SearchFrame(tk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Search song", border=4, padx=4, pady=4)
        self.app = app
        self.search_text = tk.StringVar()
        self.filter_choice = tk.StringVar(value="title")
        bf = tk.Frame(self)
        tk.Label(bf, text="Search for:").pack()
        e = tk.Entry(bf, textvariable=self.search_text)
        e.bind("<Return>", self.do_search)
        e.bind("<KeyRelease>", self.on_key_up)
        self.search_job = None
        e.pack()
        tk.Label(bf, text="search for:").pack()
        om = tk.OptionMenu(bf, self.filter_choice, "title", "artist", "album", "year", "genre")
        om.nametowidget(om.menuname)["font"] = om["font"]
        om["width"] = 10
        om.pack()
        tk.Button(bf, text="Search", command=self.do_search).pack()
        bf.pack(side=tk.LEFT)
        sf = tk.Frame(self)
        cols = [("title", 320), ("artist", 200), ("album", 200), ("year", 50), ("genre", 120)]
        self.resultTreeView = ttk.Treeview(sf, columns=[col for col, _ in cols], height=10, show="headings")
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
                track["genre"] or '-'])
        self.app.show_status("{:d} results found".format(len(result)), 3)


class JingleFrame(tk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Jingles/Samples - shift+click to change", border=4, padx=4, pady=4)
        self.app = app
        self.jingles = {num: None for num in range(20)}
        f = tk.Frame(self)
        for i in range(1, 11):
            b = tk.Button(f, text="Jingle {:d}".format(i), width=10, fg="grey")
            b.bind("<ButtonRelease>", self.do_button_release)
            b.jingle_nr = i
            b.pack(side=tk.LEFT)
        f.pack()
        f = tk.Frame(self)
        for i in range(11, 21):
            b = tk.Button(f, text="Jingle {:d}".format(i), width=10, fg="grey")
            b.bind("<ButtonRelease>", self.do_button_release)
            b.jingle_nr = i
            b. pack(side=tk.LEFT)
        f.pack()

    def do_button_release(self, event):
        if event.state & 0x0100 == 0:
            return  # no left mouse button event
        shift = event.state & 0x0001
        if shift:
            filename = tkinter.filedialog.askopenfilename()
            if filename:
                with AudiofileToWavStream(filename) as wav:
                    sample = Sample(wav)
                    self.jingles[event.widget.jingle_nr] = sample
                event.widget["fg"] = self.cget("fg")
        else:
            sample = self.jingles[event.widget.jingle_nr]
            if sample:
                self.app.play_sample(sample)


class JukeboxGui(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master.title("Jukebox")
        f1 = tk.Frame()
        self.firstTrackFrame = TrackFrame(self, f1, "Track 1")
        self.secondTrackFrame = TrackFrame(self, f1, "Track 2")
        self.levelmeterFrame = LevelmeterFrame(f1)
        self.playlistFrame = PlaylistFrame(self, f1)
        self.firstTrackFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.secondTrackFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.levelmeterFrame.pack(side=tk.LEFT, fill=tk.Y)
        self.playlistFrame.pack(side=tk.LEFT, fill=tk.Y)
        f1.pack(side=tk.TOP)
        f2 = tk.Frame()
        self.searchFrame = SearchFrame(self, f2)
        self.searchFrame.pack()
        f2.pack(side=tk.TOP)
        f3 = tk.Frame()
        self.jingleFrame = JingleFrame(self, f3)
        self.jingleFrame.pack()
        f3.pack(side=tk.TOP)
        self.statusbar = tk.Label(self, text="<status>", relief=tk.RIDGE)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.player = Player(self)
        self.backend = None
        self.show_status("Connecting to backend file service...")
        self.pack()
        self.after(100, self.connect_backend)

    def destroy(self):
        self.player.stop()
        super().destroy()

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
            self.show_status(status, 2)
        except Exception as x:
            self.show_status("ERROR! Connection to backend failed: "+str(x))
            tkinter.messagebox.showerror("Backend not connected", "Cannot connect to backend. Has it been started?\n\nYou can start it now and try searching again.")

    def enqueue(self, track):
        self.playlistFrame.enqueue(track)

    def upcoming_track_hash(self, peek=False):
        if peek:
            return self.playlistFrame.peek()
        return self.playlistFrame.pop()

    def switch_player(self):
        self.player.switch_player()

    def update_levels(self, left, right):
        self.after_idle(lambda: self.levelmeterFrame.update_meters(left, right))

    def play_sample(self, sample):
        self.player.play_sample(sample)


if __name__ == "__main__":
    root = tk.Tk()
    default_font = tk.font.nametofont("TkDefaultFont")
    default_font.configure(size=11, family="Lucida Sans Unicode")
    default_font = tk.font.nametofont("TkTextFont")
    default_font.configure(size=10, family="Lucida Sans Unicode")
    app = JukeboxGui(master=root)
    app.mainloop()
