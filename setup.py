from setuptools import setup, find_packages

   setup(
       name="genesis-lib",
       version="0.1.0",
       packages=find_packages(),
       install_requires=[
           "rti-connext-dds",
           "flask",
           "flask-socketio",
           "tabulate",
           "curses",
           "anthropic",
           "openai",
       ],
       entry_points={
           'console_scripts': [
               'genesis-monitor=genesis_lib.monitoring.console:main',
               'genesis-web-monitor=genesis_lib.monitoring.web:main',
           ],
       },
   )
