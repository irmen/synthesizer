from synthplayer.oscillators import *
from synthplayer import params


class MySine(Sine):
    def blocks(self):
        yield [1] * params.norm_osc_blocksize
        yield [2] * params.norm_osc_blocksize
        yield [3] * params.norm_osc_blocksize


class MyLinear(Linear):
    def blocks(self):
        yield [10] * params.norm_osc_blocksize
        yield [200] * params.norm_osc_blocksize


so = Sine(20, samplerate=1000)
lo = MyLinear(0.0, 0.5, max_value=1000, samplerate=1000)

# mf = DelayFilter(lo, 0.01).blocks()
mf = DelayFilter(lo, -0.01).blocks()

while True:
    print(len(next(mf)))
