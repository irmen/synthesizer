"""
Jukebox Gui

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import datetime
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.font
from .backend import BACKEND_PORT
from .streaming import AudiofileToWavStream, StreamMixer
from synthesizer.sample import Sample, Output, LevelMeter
import Pyro4
import Pyro4.errors


class TrackFrame(tk.LabelFrame):
    def __init__(self, master, title):
        super().__init__(master, text=title)
        tk.Label(self, text="sdfasfd").pack()


class RequestsFrame(tk.LabelFrame):
    def __init__(self, master):
        super().__init__(master, text="Request list")
        tk.Listbox(self).pack()
        tk.Label(self, text="sdfsdfasfd").pack()


class SearchFrame(tk.LabelFrame):
    def __init__(self, app, master):
        super().__init__(master, text="Search song")
        self.app = app
        self.search_text = tkinter.StringVar()
        self.filter_choice = tk.StringVar(value="title")
        bf = tk.Frame(self)
        tk.Label(bf, text="search string:").pack()
        e = tk.Entry(bf, textvariable=self.search_text)
        e.bind("<Return>", self.do_search)
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
        for col, colwidth in cols:
            self.resultTreeView.heading(col, text=col.title(), command=lambda c=col: self.sortby(self.resultTreeView, c, 0))
            self.resultTreeView.column(col, width=colwidth)
        self.resultTreeView.pack()
        sf.pack(side=tk.RIGHT)

    def sortby(self, tree, col, descending):
        """sort tree contents when a column header is clicked on"""
        # grab values to sort and sort in place
        data = [(tree.set(child, col), child) for child in tree.get_children('')]
        data.sort(reverse=descending)
        for ix, item in enumerate(data):
            tree.move(item[1], '', ix)
        # switch the heading so it will sort in the opposite direction next time
        tree.heading(col, command=lambda col=col: self.sortby(tree, col, int(not descending)))

    def do_search(self, event=None):
        self.app.show_status("Searching...")
        for i in self.resultTreeView.get_children():
            self.resultTreeView.delete(i)
        queryinfo = {self.filter_choice.get(): self.search_text.get()}
        try:
            result = self.app.backend.query(**queryinfo)
        except Exception as x:
            self.app.show_status("ERROR: "+str(x))
            return
        result = sorted(result, key=lambda track: (track["title"], track["artist"] or "", track["album"] or "", track["year"] or 0, track["genre"] or ""))[:50]
        for track in result:
            self.resultTreeView.insert("", tkinter.END, values=[
                track["title"] or '-',
                track["artist"] or '-',
                track["album"] or '-',
                track["year"] or '-',
                track["genre"] or '-'])
        self.app.show_status("{:d} results found".format(len(result)), 3)


class JingleFrame(tk.LabelFrame):
    def __init__(self, master):
        super().__init__(master, text="Jingles/Samples - shift+click to change")
        self["pady"] = "4"
        self["padx"] = "4"
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
            print("SHIFTCLICK", event.widget.jingle_nr)
        else:
            print("CLICK", event.widget.jingle_nr)


class JukeboxGui(tk.Frame):
    def __init__(self, master=None):
        super().__init__(master)
        self.master.title("Jukebox")
        f1 = tk.Frame()
        self.firstTrackFrame = TrackFrame(f1, "Track 1")
        self.secondTrackFrame = TrackFrame(f1, "Track 2")
        self.requestsFrame = RequestsFrame(f1)
        self.firstTrackFrame.pack(side=tk.LEFT)
        self.secondTrackFrame.pack(side=tk.LEFT)
        self.requestsFrame.pack(side=tk.LEFT)
        f1.pack(side=tk.TOP)
        f2 = tk.Frame()
        self.searchFrame = SearchFrame(self, f2)
        self.searchFrame.pack()
        f2.pack(side=tk.TOP)
        f3 = tk.Frame()
        self.jingleFrame = JingleFrame(f3)
        self.jingleFrame.pack()
        f3.pack(side=tk.TOP)
        self.statusbar = tk.Label(self, text="<status>", relief=tk.RIDGE)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.pack()
        self.backend = None
        self.show_status("Connecting to backend file service...")
        self.after(100, self.connect_backend)

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


if __name__ == "__main__":
    root = tk.Tk()
    default_font = tkinter.font.nametofont("TkDefaultFont")
    default_font.configure(size=12, family="Lucida Sans Unicode")
    default_font = tkinter.font.nametofont("TkTextFont")
    default_font.configure(size=11, family="Lucida Sans Unicode")
    app = JukeboxGui(master=root)
    app.mainloop()
