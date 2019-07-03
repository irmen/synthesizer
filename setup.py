import sys
from setuptools import setup, find_packages

if sys.version_info < (3, 5):
    raise SystemExit("Synthplayer requires Python 3.5 or newer")

setup(
    packages=find_packages()
)
