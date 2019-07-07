import tkinter
import sys
import glob
import os
import io
import tkinter.font
import tkinter.filedialog
from .drumkit import Instrument, DrumKit


class ButtonGrid(tkinter.Frame):
    def __init__(self, master, audio):
        super().__init__(master)
        self.buttons = []
        self.columns = 6
        self.rows = 4
        self.font = tkinter.font.Font(family="Helvetica", size=22, weight="bold")
        self.audio = audio
        keys = ["1234567890", "qwertyuiop", "asdfghjkl;", "zxcvbnm,./"]
        for y in range(self.rows):
            for x in range(self.columns):
                key = keys[y][x]
                button = tkinter.Button(self, text=str(key), height=5, width=10, padx=24, pady=20)
                button["font"] = self.font
                button.hotkey = key
                button.dk_instrument = None
                button.bind("<Button-1>", lambda x=x, y=y, button=button: self.pressed(button))
                button.grid(row=y, column=x)
                self.buttons.append(button)

    def hotkeyed(self, event, button):
        button.configure(relief="sunken", bg=button["activebackground"])
        self.master.update_idletasks()
        self.pressed(button)
        self.after(200, lambda b=button: b.configure(relief="raised", bg=button["highlightbackground"]))

    def pressed(self, button):
        if button.dk_instrument:
            name, instr, velocity = button.dk_instrument
            self.audio(button.hotkey, name or instr.name, instr, velocity)

    def set_button_sound(self, x, y, name: str, instr: Instrument, velocity: int):
        button = self.buttons[y*self.columns + x]
        button["text"] = "{}\n\n{}".format(button.hotkey, name or instr.name)
        button.dk_instrument = (name, instr, velocity)


class Gui(tkinter.Tk):
    def __init__(self, audio):
        super().__init__()
        self.audio = audio
        self.wm_title("DrumKit")
        self.buttongrid = ButtonGrid(self, self.audio)
        self.buttongrid.pack()
        self.messages = tkinter.Text(self, height=4, font=tkinter.font.Font(size=12), padx=10, pady=10)
        self.messages.pack(fill=tkinter.X)
        self.audio = None
        for b in self.buttongrid.buttons:
            self.bind(b.hotkey, lambda e, b=b: self.buttongrid.hotkeyed(e, b))
        sys.stdout = StdoutAdapter(self.messages)

    def set_button_sound(self, x, y, name: str, instr: Instrument, velocity: int):
        self.buttongrid.set_button_sound(x, y, name, instr, velocity)

    def start(self, samples_location: str):
        self.messages.insert(tkinter.END, "~~~~ Python DrumKit ~~~~\n")
        if not os.path.isdir(samples_location):
            print(">>>> Select the directory contaiting the  Salamander Drumkit v1 files <<<<")
            samples_location = tkinter.filedialog.askdirectory()
        import threading
        threading.Thread(target=self.load_drumkit, args=(samples_location,)).start()
        self.mainloop()

    def load_drumkit(self, location) -> None:
        files = glob.glob(os.path.normpath(location + "/*.sfz"))
        if not files:
            print("ERROR: There are no *.sfz sample instrument files in the drumkit location! ({})".format(location))
            print("Download the Salamander Drumkit from: "
                  "http://download.linuxaudio.org/musical-instrument-libraries/sfz/salamander_drumkit_v1.tar.7z")
            return
        dk = DrumKit()
        dk.load(location)

        name = "ride:48"
        self.set_button_sound(0, 0, name, dk.instruments[name], 100)
        name = "ride:49"
        self.set_button_sound(1, 0, name, dk.instruments[name], 100)
        name = "ride:50"
        self.set_button_sound(2, 0, name, dk.instruments[name], 100)
        name = "ride:52"
        self.set_button_sound(3, 0, name, dk.instruments[name], 100)
        name = "ride:53"
        self.set_button_sound(4, 0, name, dk.instruments[name], 100)

        name = "lotom:43"
        self.set_button_sound(0, 1, name, dk.instruments[name], 100)
        name = "hitom:45"
        self.set_button_sound(1, 1, name, dk.instruments[name], 100)
        name = "kick:35"
        self.set_button_sound(0, 2, name, dk.instruments[name], 100)
        name = "kick:36"
        self.set_button_sound(1, 2, name, dk.instruments[name], 100)

        name = "hihat:42"
        self.set_button_sound(0, 3, name, dk.instruments[name], 100)
        name = "hihat:44"
        self.set_button_sound(1, 3, name, dk.instruments[name], 100)
        name = "hihat:46"
        self.set_button_sound(2, 3, name, dk.instruments[name], 100)

        name = "snare:37"
        self.set_button_sound(2, 1, name, dk.instruments[name], 100)
        name = "snare:38"
        self.set_button_sound(3, 1, name, dk.instruments[name], 100)
        name = "snare:39"
        self.set_button_sound(4, 1, name, dk.instruments[name], 100)
        name = "snare:40"
        self.set_button_sound(2, 2, name, dk.instruments[name], 100)
        name = "snare:41"
        self.set_button_sound(3, 2, name, dk.instruments[name], 100)

        name = "crashesfx:47"
        self.set_button_sound(5, 0, name, dk.instruments[name], 100)
        name = "crashesfx:64"
        self.set_button_sound(5, 1, name, dk.instruments[name], 100)
        name = "crashesfx:55"
        self.set_button_sound(4, 2, name, dk.instruments[name], 100)
        name = "crashesfx:63"
        self.set_button_sound(5, 2, name, dk.instruments[name], 100)
        name = "crashesfx:62"
        self.set_button_sound(3, 3, name, dk.instruments[name], 100)
        name = "crashesfx:60"
        self.set_button_sound(4, 3, name, dk.instruments[name], 100)
        name = "crashesfx:59"
        self.set_button_sound(5, 3, name, dk.instruments[name], 100)


class StdoutAdapter(io.TextIOBase):
    def __init__(self, messages):
        self.messages = messages

    def write(self, s: str) -> int:
        self.messages.insert(tkinter.END, s)
        self.messages.see(tkinter.END)
        return len(s)

    def flush(self) -> None:
        pass

    def close(self):
        pass
