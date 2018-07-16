import sys
from setuptools import setup

if sys.version_info < (3, 5):
    raise SystemExit("Synthplayer requires Python 3.5 or newer")

setup()
