"""
Sample mixer and sequencer meant to create rhythms. Inspired by the Roland TR-909.
Sample mix rate is configured at 44.1 khz. You may want to change this if most of
the samples you're using are of a different sample rate (such as 48Khz), to avoid
the slight loss of quality due to resampling.

Written by Irmen de Jong (irmen@razorvine.net) - License: MIT open-source.
"""

import os
import cmd
from configparser import ConfigParser
from .sample import Sample
from .playback import Output

__all__ = ["Mixer", "Song", "Repl"]


class Mixer:
    """
    Mixes a set of ascii-bar tracks using the given sample instruments, into a resulting big sample.
    """
    def __init__(self, patterns, bpm, ticks, instruments):
        for p in patterns:
            bar_length = 0
            for instrument, bars in p.items():
                if instrument not in instruments:
                    raise ValueError("instrument '{:s}' not defined".format(instrument))
                if len(bars) % ticks != 0:
                    raise ValueError("bar length must be multiple of the number of ticks")
                if 0 < bar_length != len(bars):
                    raise ValueError("all bars must be of equal length in the same pattern")
                bar_length = len(bars)
        self.patterns = patterns
        self.instruments = instruments
        self.bpm = bpm
        self.ticks = ticks

    def mix(self, verbose=True):
        """
        Mix all the patterns into a single result sample.
        """
        if not self.patterns:
            if verbose:
                print("No patterns to mix, output is empty.")
            return Sample()
        total_seconds = 0.0
        for p in self.patterns:
            bar = next(iter(p.values()))
            total_seconds += len(bar) * 60.0 / self.bpm / self.ticks
        if verbose:
            print("Mixing {:d} patterns...".format(len(self.patterns)))
        mixed = Sample().make_32bit()
        for index, timestamp, sample in self.mixed_samples(tracker=False):
            if verbose:
                print("\r{:3.0f} % ".format(timestamp/total_seconds*100), end="")
            mixed.mix_at(timestamp, sample)
        # chop/extend to get to the precise total duration (in case of silence in the last bars etc)
        missing = total_seconds-mixed.duration
        if missing > 0:
            mixed.add_silence(missing)
        elif missing < 0:
            mixed.clip(0, total_seconds)
        if verbose:
            print("\rMix done.")
        return mixed

    def mix_generator(self):
        """
        Returns a generator that produces samples that are the chronological
        chunks of the final output mix. This avoids having to mix it into one big
        output mix sample.
        """
        if not self.patterns:
            yield Sample()
            return
        total_seconds = 0.0
        for p in self.patterns:
            bar = next(iter(p.values()))
            total_seconds += len(bar) * 60.0 / self.bpm / self.ticks
        mixed_duration = 0.0
        samples = self.mixed_samples()
        # get the first sample
        index, previous_timestamp, sample = next(samples)
        mixed = Sample().make_32bit()
        mixed.mix_at(previous_timestamp, sample)
        # continue mixing the following samples
        for index, timestamp, sample in samples:
            trigger_duration = timestamp-previous_timestamp
            overflow = None
            if mixed.duration < trigger_duration:
                # fill with some silence to reach the next sample position
                mixed.add_silence(trigger_duration - mixed.duration)
            elif mixed.duration > trigger_duration:
                # chop off the sound that extends into the next sample position
                # keep this overflow and mix it later!
                overflow = mixed.split(trigger_duration)
            mixed_duration += mixed.duration
            yield mixed
            mixed = overflow if overflow else Sample().make_32bit()
            mixed.mix(sample)
            previous_timestamp = timestamp
        # output the last remaining sample and extend it to the end of the duration if needed
        timestamp = total_seconds
        trigger_duration = timestamp-previous_timestamp
        if mixed.duration < trigger_duration:
            mixed.add_silence(trigger_duration - mixed.duration)
        elif mixed.duration > trigger_duration:
            mixed.clip(0, trigger_duration)
        mixed_duration += mixed.duration
        yield mixed

    def mixed_triggers(self, tracker):
        """
        Generator for all triggers in chronological sequence.
        Every element is a tuple: (trigger index, time offset (seconds), list of (instrumentname, sample tuples)
        """
        time_per_index = 60.0 / self.bpm / self.ticks
        index = 0
        for pattern_nr, pattern in enumerate(self.patterns, start=1):
            pattern = list(pattern.items())
            num_triggers = len(pattern[0][1])
            for i in range(num_triggers):
                triggers = []
                triggered_instruments = set()
                for instrument, bars in pattern:
                    if bars[i] not in ". ":
                        sample = self.instruments[instrument]
                        triggers.append((instrument, sample))
                        triggered_instruments.add(instrument)
                if triggers:
                    if tracker:
                        triggerdots = ['#' if instr in triggered_instruments else '.' for instr in self.instruments]
                        print("\r{:3d} [{:3d}] ".format(index, pattern_nr), "".join(triggerdots), end="   ", flush=True)
                    yield index, time_per_index*index, triggers
                index += 1

    def mixed_samples(self, tracker=True):
        """
        Generator for all samples-to-mix.
        Every element is a tuple: (trigger index, time offset (seconds), sample)
        """
        mix_cache = {}  # we cache stuff to avoid repeated mixes of the same instruments
        for index, timestamp, triggers in self.mixed_triggers(tracker):
            if len(triggers) > 1:
                # sort the samples to have the longest one as the first
                # this allows us to allocate the target mix buffer efficiently
                triggers = sorted(triggers, key=lambda t: t[1].duration, reverse=True)
                instruments_key = tuple(instrument for instrument, _ in triggers)
                if instruments_key in mix_cache:
                    yield index, timestamp, mix_cache[instruments_key]
                    continue
                # duplicate the longest sample as target mix buffer, then mix the remaining samples into it
                mixed = triggers[0][1].copy()
                for _, sample in triggers[1:]:
                    mixed.mix(sample)
                mixed.lock()
                mix_cache[instruments_key] = mixed   # cache the mixed instruments sample
                yield index, timestamp, mixed
            else:
                # simply yield the unmixed sample from the single trigger
                yield index, timestamp, triggers[0][1]


class Song:
    """
    Represents a set of instruments, patterns and bars that make up a 'song'.
    """
    def __init__(self):
        self.instruments = {}
        self.sample_path = None
        self.bpm = 128
        self.ticks = 4
        self.pattern_sequence = []
        self.patterns = {}

    def read(self, song_file, discard_unused_instruments=True):
        """Read a song from a saved file."""
        with open(song_file):
            pass    # test for file existence
        print("Loading song...")
        cp = ConfigParser()
        cp.read(song_file)
        self.sample_path = cp["paths"]["samples"]
        self.read_samples(cp["samples"], self.sample_path)
        if "song" in cp:
            self.bpm = cp["song"].getint("bpm")
            self.ticks = cp["song"].getint("ticks")
            self.read_patterns(cp, cp["song"]["patterns"].split())
        print("Done; {:d} instruments and {:d} patterns.".format(len(self.instruments), len(self.patterns)))
        unused_instruments = self.instruments.keys()
        for pattern_name in self.pattern_sequence:
            unused_instruments -= self.patterns[pattern_name].keys()
        if unused_instruments and discard_unused_instruments:
            for instrument in list(unused_instruments):
                del self.instruments[instrument]
            print("Warning: there are unused instruments. They have been unloaded to save memory, and can safely be removed from the song file.")
            print("The unused instruments are:", ", ".join(sorted(unused_instruments)))

    def read_samples(self, instruments, samples_path):
        """Reads the sample files for the instruments."""
        self.instruments = {}
        for name, file in sorted(instruments.items()):
            self.instruments[name] = Sample(wave_file=os.path.join(samples_path, file)).normalize().make_32bit(scale_amplitude=False).lock()

    def read_patterns(self, songdef, names):
        """Reads and parses the pattern specs from the song."""
        self.pattern_sequence = []
        self.patterns = {}
        for name in names:
            if "pattern."+name not in songdef:
                raise ValueError("pattern definition not found: "+name)
            bar_length = 0
            self.patterns[name] = {}
            for instrument, bars in songdef["pattern."+name].items():
                if instrument not in self.instruments:
                    raise ValueError("instrument '{instr:s}' not defined (pattern: {pattern:s})".format(instr=instrument, pattern=name))
                bars = bars.replace(' ', '')
                if len(bars) % self.ticks != 0:
                    raise ValueError("all patterns must be multiple of song ticks (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                self.patterns[name][instrument] = bars
                if 0 < bar_length != len(bars):
                    raise ValueError("all bars must be of equal length in the same pattern (pattern: {pattern:s}.{instr:s})".format(pattern=name, instr=instrument))
                bar_length = len(bars)
            self.pattern_sequence.append(name)

    def write(self, output_filename):
        """Save the song definitions to an output file."""
        import collections
        cp = ConfigParser(dict_type=collections.OrderedDict)
        cp["paths"] = {"samples": self.sample_path}
        cp["song"] = {"bpm": self.bpm, "ticks": self.ticks, "patterns": " ".join(self.pattern_sequence)}
        cp["samples"] = {}
        for name, sample in sorted(self.instruments.items()):
            cp["samples"][name] = os.path.basename(sample.filename)
        for name, pattern in sorted(self.patterns.items()):
            # Note: the layout of the patterns is not optimized for human viewing. You may want to edit it afterwards.
            cp["pattern."+name] = collections.OrderedDict(sorted(pattern.items()))
        with open(output_filename, 'w') as f:
            cp.write(f)
        print("Saved to '{:s}'.".format(output_filename))

    def mix(self, output_filename):
        """Mix the song into a resulting mix sample."""
        if not self.pattern_sequence:
            raise ValueError("There's nothing to be mixed; no song loaded or song has no patterns.")
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        result = mixer.mix()
        result.make_16bit()
        result.write_wav(output_filename)
        print("Output is {:.2f} seconds, written to: {:s}".format(result.duration, output_filename))
        return result

    def mixed_triggers(self):
        """
        Generator that produces all the instrument triggers needed to mix/stream the song.
        Shortcut for Mixer.mixed_triggers, see there for more details.
        """
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        return mixer.mixed_triggers(False)

    def mix_generator(self):
        """
        Generator that produces samples that together form the mixed song.
        Shortcut for Mixer.mix_generator(), see there for more details.
        """
        patterns = [self.patterns[name] for name in self.pattern_sequence]
        mixer = Mixer(patterns, self.bpm, self.ticks, self.instruments)
        return mixer.mix_generator()


class Repl(cmd.Cmd):
    """
    Interactive command line interface to load/record/save and play samples, patterns and whole tracks.
    Currently it has no way of defining and loading samples manually. This means you need to initialize
    it with a track file containing at least the instruments (samples) that you will be using.
    """
    def __init__(self, discard_unused_instruments=False):
        self.song = Song()
        self.discard_unused_instruments = discard_unused_instruments
        self.out = Output()
        super(Repl, self).__init__()

    def do_quit(self, args):
        """quits the session"""
        print("Bye.", args)
        self.out.close()
        return True

    def do_bpm(self, bpm):
        """set the playback BPM (such as 174 for some drum'n'bass)"""
        try:
            self.song.bpm = int(bpm)
        except ValueError as x:
            print("ERROR:", x)

    def do_ticks(self, ticks):
        """set the number of pattern ticks per beat (usually 4 or 8)"""
        try:
            self.song.ticks = int(ticks)
        except ValueError as x:
            print("ERROR:", x)

    def do_samples(self, args):
        """show the loaded samples"""
        print("Samples:")
        print(",  ".join(self.song.instruments))

    def do_patterns(self, args):
        """show the loaded patterns"""
        print("Patterns:")
        for name, pattern in sorted(self.song.patterns.items()):
            self.print_pattern(name, pattern)

    def print_pattern(self, name, pattern):
        print("PATTERN {:s}".format(name))
        for instrument, bars in pattern.items():
            print("   {:>15s} = {:s}".format(instrument, bars))

    def do_pattern(self, names):
        """play the pattern with the given name(s)"""
        names = names.split()
        for name in sorted(set(names)):
            try:
                pat = self.song.patterns[name]
                self.print_pattern(name, pat)
            except KeyError:
                print("no such pattern '{:s}'".format(name))
                return
        patterns = [self.song.patterns[name] for name in names]
        try:
            m = Mixer(patterns, self.song.bpm, self.song.ticks, self.song.instruments)
            result = m.mix(verbose=len(patterns) > 1).make_16bit()
            self.out.play_sample(result)
        except ValueError as x:
            print("ERROR:", x)

    def do_play(self, args):
        """play a single sample by giving its name, add a bar (xx..x.. etc) to play it in a bar"""
        if ' ' in args:
            instrument, pattern = args.split(maxsplit=1)
            pattern = pattern.replace(' ', '')
        else:
            instrument = args
            pattern = None
        instrument = instrument.strip()
        try:
            sample = self.song.instruments[instrument]
        except KeyError:
            print("unknown sample")
            return
        if pattern:
            self.play_single_bar(sample, pattern)
        else:
            sample = sample.copy().make_16bit()
            self.out.play_sample(sample)
            self.out.wait_all_played()

    def play_single_bar(self, sample, pattern):
        try:
            m = Mixer([{"sample": pattern}], self.song.bpm, self.song.ticks, {"sample": sample})
            result = m.mix(verbose=False).make_16bit()
            self.out.play_sample(result)
        except ValueError as x:
            print("ERROR:", x)

    def do_mix(self, args):
        """mix and play all patterns of the song"""
        if not self.song.pattern_sequence:
            print("Nothing to be mixed.")
            return
        output = "__temp_mix.wav"
        self.song.mix(output)
        mix = Sample(wave_file=output)
        print("Playing sound...")
        self.out.play_sample(mix)
        os.remove(output)

    def do_stream(self, args):
        """
        mix all patterns of the song and stream the output to your speakers in real-time,
        or to an output file if you give a filename argument.
        This is the fastest and most efficient way of generating the output mix because
        it uses very little memory and avoids large buffer copying.
        """
        if not self.song.pattern_sequence:
            print("Nothing to be mixed.")
            return
        if args:
            filename = args.strip()
            print("Mixing and streaming to output file '{0}'...".format(filename))
            self.out.stream_to_file(filename, self.song.mix_generator())
            print("\r                          ")
            return
        print("Mixing and streaming to speakers...")
        try:
            self.out.play_samples(self.song.mix_generator())
            print("\r                          ")
            self.out.wait_all_played()
        except KeyboardInterrupt:
            print("Stopped.")

    def do_rec(self, args):
        """Record (or overwrite) a new sample (instrument) bar in a pattern.
Args: [pattern name] [sample] [bar(s)].
Omit bars to remove the sample from the pattern.
If a pattern with the name doesn't exist yet it will be added."""
        args = args.split(maxsplit=2)
        if len(args) not in (2, 3):
            print("Wrong arguments. Use: patternname sample bar(s)")
            return
        if len(args) == 2:
            args.append(None)   # no bars
        pattern_name, instrument, bars = args
        if instrument not in self.song.instruments:
            print("Unknown sample '{:s}'.".format(instrument))
            return
        if pattern_name not in self.song.patterns:
            self.song.patterns[pattern_name] = {}
        pattern = self.song.patterns[pattern_name]
        if bars:
            bars = bars.replace(' ', '')
            if len(bars) % self.song.ticks != 0:
                print("Bar length must be multiple of the number of ticks.")
                return
            pattern[instrument] = bars
        else:
            if instrument in pattern:
                del pattern[instrument]
        if pattern_name in self.song.patterns:
            if not self.song.patterns[pattern_name]:
                del self.song.patterns[pattern_name]
                print("Pattern was empty and has been removed.")
            else:
                self.print_pattern(pattern_name, self.song.patterns[pattern_name])

    def do_seq(self, names):
        """
        Print the sequence of patterns that form the current track,
        or if you give a list of names: use that as the new pattern sequence.
        """
        if not names:
            print("  ".join(self.song.pattern_sequence))
            return
        names = names.split()
        for name in names:
            if name not in self.song.patterns:
                print("Unknown pattern '{:s}'.".format(name))
                return
        self.song.pattern_sequence = names

    def do_load(self, filename):
        """Load a new song file"""
        song = Song()
        try:
            song.read(filename, self.discard_unused_instruments)
            self.song = song
        except IOError as x:
            print("ERROR:", x)

    def do_save(self, filename):
        """Save current song to file"""
        if not filename:
            print("Give filename to save song to.")
            return
        if not filename.endswith(".ini"):
            filename += ".ini"
        if os.path.exists(filename):
            if input("File exists: '{:s}'. Overwrite y/n? ".format(filename)) not in ('y', 'yes'):
                return
        self.song.write(filename)
