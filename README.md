# 4xidraw server

## Usage

```
python3 -m venv .venv
.venv/bin/activate
pip3 install -r requirements.txt

# A cli exposes the base functions
python3 src/cli.py gen_gcode test_data/triangulate-1.svg
python3 src/cli.py plot_file test_data/triangulate-1.gcode

# start plotter server
python3 src/server.py

# test plotter server
curl -X POST http://127.0.0.1:5000/plot \
    -F "file=@./test_data/triangulate-1.svg" \
    -F "page_size=29.7x21cm"
```