# 4xidraw server

## Usage

```
python3 -m venv .venv
.venv/bin/activate
pip3 install -r requirements.txt

python3 src/cli.py gen_gcode test_data/triangulate-1.svg
python3 src/cli.py plot_file test_data/triangulate-1.gcode
```