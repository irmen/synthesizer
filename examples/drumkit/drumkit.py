import sys
import glob
import os
import random
import itertools
from synthplayer.sample import Sample
from typing import Dict, Optional, List


class Group:
    def __init__(self):
        self.volume = 0.0
        self.amp_veltrack = 0
        self.ampeg_release = 0.0
        self.key = 0
        self.group = 0
        self.lo_vel = 0
        self.hi_vel = 0
        self.seq_length = 0
        self.regions = []        # type: List[Region]
        self._seq = 0
        self._uses_random = True

    def initialize(self):
        self._seq = 0
        self._uses_random = self.seq_length == 0
        self.regions = list(sorted(self.regions, key=lambda r: r.seq or 0))

    def get_sample(self) -> (float, Sample):
        """return one of the samples from the regions, as appropriate"""
        rnd = random.random()
        if self._uses_random:
            for r in self.regions:
                if r.lo_rand is None and r.hi_rand is None and len(self.regions) == 1:
                    return self.volume, r.sample
                if r.lo_rand <= rnd <= r.hi_rand:
                    return self.volume, r.sample
            raise LookupError("no sample found to play")
        else:
            r = self.regions[self._seq]
            self._seq = (self._seq + 1) % self.seq_length
            return self.volume, r.sample


class Region:
    def __init__(self):
        self.sample = None       # type: Sample
        self.lo_rand = None      # type: Optional[float]
        self.hi_rand = None      # type: Optional[float]
        self.seq = None          # type: Optional[int]


class Instrument:
    def __init__(self, name: str) -> None:
        self.name = name
        self._samples_location = ""
        self.groups = []        # type: List[Group]
        self.total_sample_memory = 0

    def group(self, line: str) -> Group:
        group = Group()
        pairs = line.split()
        while pairs:
            variable, value = pairs[0].split("=")
            del pairs[0]
            if variable == "volume":
                group.volume = float(value)
            elif variable == "key":
                group.key = int(value)
            elif variable == "amp_veltrack":
                group.amp_veltrack = int(value)
            elif variable == "ampeg_release":
                group.ampeg_release = float(value)
            elif variable == "lovel":
                group.lo_vel = int(value)
            elif variable == "hivel":
                group.hi_vel = int(value)
            elif variable == "group":
                group.group = int(value)
            elif variable == "seq_length":
                group.seq_length = int(value)
            elif variable in ("loop_mode", "off_mode", "off_by", "locc64", "hicc64",
                              "amp_veltrack", "ampeg_release"):
                pass
            else:
                raise IOError("invalid variable in group: "+variable)
        return group

    def region(self, line: str) -> Optional[Region]:
        region = Region()
        pairs = line.split()
        while pairs:
            variable, value = pairs[0].split("=")
            del pairs[0]
            if variable == "seq_position":
                region.seq = int(value)
            elif variable == "sample":
                if "\\" in value:
                    value = value.replace("\\", os.path.sep)
                if value:
                    filename = os.path.join(self._samples_location, value)
                    if not os.path.isfile(filename):
                        print("Warning: sample not found:", filename, file=sys.stderr)
                        return None
                    region.sample = Sample(filename, value)
                    region.sample.amplify(0.7)    # adjust base volume down to avoid clipping issues when mixing
                    region.sample.normalize()
                    self.total_sample_memory += len(region.sample) * region.sample.samplewidth * region.sample.nchannels
            elif variable == "lorand":
                if value.endswith("s"):
                    value = value[:-1]
                region.lo_rand = float(value)
            elif variable == "hirand":
                if value.endswith("s"):
                    value = value[:-1]
                region.hi_rand = float(value)
            else:
                raise IOError("invalid variable in region: "+variable)
        return region

    def get_group(self, velocity: int) -> Group:
        for g in self.groups:
            if g.lo_vel <= velocity <= g.hi_vel:
                return g
        # *shrug*, just return the first, if no match is found
        return self.groups[0]

    @classmethod
    def from_name_and_groups(cls, name: str, groups: List[Group]) -> "Instrument":
        instr = cls(name)
        instr.groups = groups
        instr.total_sample_memory = 0
        for g in groups:
            for r in g.regions:
                instr.total_sample_memory += len(r.sample) * r.sample.nchannels * r.sample.samplewidth
        return instr

    def load_sfz(self, filename: str, samples_location: str) -> None:
        self._samples_location = samples_location
        current_group = Group()
        has_group = False
        print(" ", self.name, end=" ")
        with open(os.path.expanduser(filename), "rt") as inf:
            lines = inf.readlines()
        for line in lines:
            line = line.split("//")[0].strip()
            if not line or line.startswith("//"):
                continue  # empty or comment line, ignore
            if line.startswith("<group>"):
                if has_group:
                    current_group.initialize()
                    print(".", end="", flush=True)
                    self.groups.append(current_group)
                current_group = self.group(line[7:])
                has_group = True
            elif line.startswith("<region>"):
                region = self.region(line[8:])
                if has_group and region is not None:
                    current_group.regions.append(region)
            else:
                raise IOError("invalid line in sfz: " + line[:20], filename)
        if has_group:
            current_group.initialize()
            self.groups.append(current_group)
        # print(len(self.groups), "groups", sum(len(g.regions) for g in self.groups), "regions")


class DrumKit:
    def __init__(self) -> None:
        self.instruments = {}       # type: Dict[str, Instrument]

    def load(self, samples_location: str) -> None:
        print("Loading instruments from '{}': ".format(samples_location), end="", flush=True)
        for filename in glob.glob(os.path.normpath(samples_location + "/*.sfz")):
            onlyfile = os.path.split(filename)[1]
            if onlyfile.lower() != "all.sfz" and onlyfile.lower() != "salamander drumkit.sfz":
                name = os.path.splitext(onlyfile)[0].lower()
                instr = Instrument(name)
                instr.load_sfz(filename, samples_location)
                # instruments can be a collection of several related instruments.
                # they're distinguished by the 'key' property of the groups.
                for key, groups in itertools.groupby(instr.groups, lambda g: g.key):
                    fullname = name+":"+str(key)
                    instr = Instrument.from_name_and_groups(fullname, list(groups))
                    self.instruments[fullname] = instr
        total_sample_memory = sum(instr.total_sample_memory for instr in self.instruments.values())
        print("\nLoaded {} instruments using {} Mb of sample memory.".format(
            len(self.instruments), total_sample_memory // 1024 // 1024))
