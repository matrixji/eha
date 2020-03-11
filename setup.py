"""
setup for eha
"""

from setuptools import setup, find_packages

VERSION=0.4

setup(
    name='eha',
    version=VERSION,
    description='A High Availability service framework based on etcd.',
    long_description=(
      "eha is a framework for build High Availability application based etcd."
    ),
    author='Ji Bin',
    author_email='matrixji@live.com',
    url='https://github.com/matrixji/eha',
    license='MIT',
    packages = find_packages(),
    platforms=['linux'],
    python_requires='>=3.6',
    install_requires=[
        'pyzmq>=19.0.0',
        'PyYAML>=5.1.2',
        'aioetcd3>=1.10',
        'sdnotify>=0.3.2'
    ],
    entry_points={
        'console_scripts': [
            'eha-agent=eha:server_main',
            'eha-proxy=eha:proxy_main',
        ]
    },
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Topic :: Software Development',
    ],
)
