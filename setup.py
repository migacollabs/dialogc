import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.md')).read()
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = []

with open('requirements.txt') as f:
    requires = f.read().splitlines()

requires = [r for r in requires if r and r.startswith("#")==False and r.startswith("-e")==False]

setup(name='DialogC',
      version='0.5,
      description='DialogC',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
        "Programming Language :: Python"
        ],
      author='Mat Mathews',
      author_email='mat@miga.me',
      url='http://miga.io',
      keywords='gamedev dialog script',
      packages=find_packages(),
      include_package_data=True,
      package_data={'':[
          '*.mako', '*.yaml', '*.csv',
          '*.sql', '*.css', '*.sass',
          '*.js', '*.rb', '*.txt', '*.plr'
      ]},
      data_files = [
      ],
      zip_safe=False,
      install_requires=requires,
      tests_require=requires,
      test_suite="dialogc"
      )
