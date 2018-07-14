import time
import itertools
from synthesizer import synth


samplerate = 44100
frequency = 880
num_samples = samplerate*10

oscillators = [synth.Linear,        # baseline
               synth.FastSine,
               synth.FastPulse,
               synth.FastSawtooth,
               synth.FastSquare,
               synth.FastTriangle,
               synth.FastSemicircle,
               synth.FastPointy,

               synth.Sine,
               synth.Triangle,
               synth.Square,
               synth.SquareH,
               synth.Sawtooth,
               synth.SawtoothH,
               synth.Pulse,
               # synth.Harmonics,   # used by sawtoothH and squareH already
               synth.WhiteNoise,
               synth.Semicircle,
               synth.Pointy]


for osctype in oscillators:
    osc = osctype(frequency, samplerate=samplerate)
    if hasattr(osc, "generator2"):
        osc = osc.generator2()
    else:
        osc = osc.generator()
    print("testing {:20.20s}... ".format(osctype.__name__), end="")
    start = time.time()
    dummy = list(itertools.islice(osc, num_samples))
    duration = time.time()-start
    sample_duration = num_samples/samplerate
    print("{:6.0f} K iterations/sec ({:.1f} x realtime @ {:d} hz)".format(num_samples/duration/1000, sample_duration/duration, samplerate))
