#!/usr/bin/env python3
"""Run the unmodified Python engine in an isolated regression-test process."""
import runpy
import sys

sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
