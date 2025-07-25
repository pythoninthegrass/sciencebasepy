import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name='sciencebasepy',
    version='2.0.20',
    author="USGS ScienceBase Development Team",
    author_email="sciencebase@usgs.gov",
    description="Python ScienceBase Utilities",
    long_description='This Python module provides functionality for interacting with the USGS ScienceBase platform.',
    long_description_content_type="text/markdown",
    url='https://code.usgs.gov/sas/sdm/sciencebasepy',
    packages=setuptools.find_packages(),
    classifiers=[
        "License :: Public Domain",
        "Operating System :: OS Independent",
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11'
    ],
    install_requires=[
        "requests",
        "requests-mock",
        "progress",
        "pytest",
        "charset-normalizer"
    ]
)
