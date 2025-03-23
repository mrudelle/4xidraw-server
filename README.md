# 4xidraw server

CLI and server to plot SVG and G-Code on a 4xidraw pen plotter. Or any other GRBL driver.

## Usage

```
python3 -m venv .venv
.venv/bin/activate
pip3 install -r requirements.txt

# A cli exposes the base functions
python3 src/cli.py gen_gcode test_data/triangulate-1.svg
python3 src/cli.py plot_file test_data/triangulate-1.gcode
python3 src/cli.py serial  # start an interactive serial session
python3 src/cli.py query $$
python3 src/cli.py send_command "X100 Y50 F1000"


# start plotter server
FLASK_APP=./src/server.py flask run --debug

A simple web ui is available at http://127.0.0.1:5000/

# test plotter server
curl -X POST http://127.0.0.1:5000/plot \
    -F "file=@./test_data/triangulate-1.svg" \
    -F "page_size=29.7x21cm"
```
