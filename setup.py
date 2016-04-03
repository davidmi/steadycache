# -*- encoding: utf-8 -*-
import io
import steadycache
from os.path import dirname
from os.path import join
from setuptools import setup

def read(*names, **kwargs):
    return io.open(
        join(dirname(__file__), *names),
        encoding=kwargs.get("encoding", "utf8")
    ).read()


setup(
    name="steadycache",
    version=steadycache.VERSION,
    #license="BSD",
    description="A decorator to cache function results in Redis",
    long_description="%s" % (read("README.md")),
    author="David Iserovich",
    author_email="diserovich@appnexus.com",
    url="git@git.corp.appnexus.com:user/diserovich/cache",
    #py_modules=[splitext(basename(path))[0] for path in glob("src/*.py")],
    packages=['steadycache'],
    include_package_data=True,
    zip_safe=False,
    classifiers=[
        # complete classifier list: http://pypi.python.org/pypi?%3Aaction=list_classifiers
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: Unix",
        "Operating System :: POSIX",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: Implementation :: CPython",
        "Topic :: Software Development :: Libraries",
    ],
    keywords=[
        "cache", "redis", "decorator",
    ],
    install_requires=[
        "redis>=2.10.0"
    ],
    entry_points={
        "console_scripts": [
            "nameless = nameless.__main__:main"
        ]
    },
)
