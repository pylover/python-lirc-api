''' LIRC Python API, provisionary. Includes a C extension. Requires lirc,
including header files, installed '''

import subprocess
from setuptools import setup, find_packages, Extension

from lirc.config import VERSION

flags =  subprocess.check_output(
    ["pkg-config", "--cflags",  "--libs", "lirc"]
).decode("ascii").strip().split()

c_module = Extension('_client',
                     sources=['lirc/_client.c'],
                     libraries=['lirc_client'],
                     extra_compile_args=flags)


setup(
    name = 'lirc',
    version = "0.9.5",
    author = "Alec Leamas",
    author_email = "leamas@nowhere.net",
    url = "http://sf.net/p/lirc",
    description = "LIRC python API",
    keywords = "lirc asyncio API",
    long_description = open('README.rst', encoding='utf-8').read(),
    license = "GPLv2+",
    packages = ['lirc'],
    ext_modules = [c_module],
    classifiers = [
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Development Status :: 4 - Beta',
        'License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Operating System :: Unix',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Hardware',
    ]
)
