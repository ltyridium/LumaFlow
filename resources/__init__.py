"""LumaFlow runtime resources package.

This file exists so that ``setuptools`` treats ``resources/`` as a real
Python package and installs it (together with all of its data files) into
``<site-packages>/resources/``.  That keeps ``core.resource_paths`` working
unchanged after a ``pip install .`` because it resolves resources via
``Path(__file__).resolve().parent.parent`` which points at the site-packages
root in installed mode.
"""

