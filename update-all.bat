for %%f in (update-*.py) do (%%f)

python -m pip install -U pip
pip install -U setuptools packaging requests pywin32
