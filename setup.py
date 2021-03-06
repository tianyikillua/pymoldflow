import os

from setuptools import find_packages, setup

# https://packaging.python.org/single_source_version/
base_dir = os.path.abspath(os.path.dirname(__file__))
about = {}
with open(os.path.join(base_dir, "pymoldflow", "__about__.py"), "rb") as f:
    exec(f.read(), about)


setup(
    name="pymoldflow",
    version=about["__version__"],
    packages=find_packages(),
    url="https://github.com/tianyikillua/pymoldflow",
    author=about["__author__"],
    author_email=about["__email__"],
    install_requires=["numpy", "meshio", "lxml", "pyyaml"],
    description="Automation tools for Autodesk Moldflow",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license=about["__license__"],
    classifiers=[
        about["__license__"],
        about["__status__"],
        # See <https://pypi.org/classifiers/> for all classifiers.
        "Operating System :: Microsoft :: Windows",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Topic :: Scientific/Engineering :: Physics",
    ],
)
