import time
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

               synth.Sine,
               synth.Triangle,
               synth.Square,
               synth.SquareH,
               synth.Sawtooth,
               synth.SawtoothH,
               synth.Pulse,
               # synth.Harmonics,   # used by sawtoothH and squareH already
               synth.WhiteNoise,
               synth.Linear]


for osctype in oscillators:
    osc = osctype(frequency, samplerate=samplerate)
    if hasattr(osc, "generator2"):
        osc=osc.generator2()
    else:
        osc=osc.generator()
    print("testing {:20.20s}... ".format(osctype.__name__), end="")
    start = time.time()
    for _ in range(num_samples):
        next(osc)
    duration = time.time()-start
    sample_duration = num_samples/samplerate
    print("{:6.0f} K iterations/sec ({:.1f} x realtime @ {:d} hz)".format(num_samples/duration/1000, sample_duration/duration, samplerate))
