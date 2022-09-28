"""Setup file for installing dependencies for mibilib.
Copyright (C) 2022 Ionpath, Inc.  All rights reserved."""

from setuptools import setup

setup(name='mibilib',
      author='IONpath, Inc.',
      author_email='support@ionpath.com',
      version='1.7.0',
      url='https://github.com/ionpath/icb-client',
      description='Python helper for controlling MIBIScope using websockets and RESTful APIs',
      license='MIT',
      python_requires='~=3.7.3',
      install_requires=[
        'requests==2.21.0',
        'rx==1.6.1'
        'websocket-client==0.54.0'
      ]
     )