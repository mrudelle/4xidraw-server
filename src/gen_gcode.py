from pathlib import Path
import tempfile
import vpype
from vpype_cli import execute

def process_svg_to_gcode(input_svg, output_gcode, *, 
    target_page_size='297x210mm', 
    split_layers=False,
    pen_speed='2000',
    pen_up_delay='0.1',
    pen_down_delay='0.2',
):

    target_page_width, target_page_height = vpype.convert_page_size(target_page_size)

    doc = vpype.read_multilayer_svg(input_svg, 1)

    # Get the size of the svg document
    page_size = doc.page_size
    width = 0 if not page_size else page_size[0]
    height = 0 if not page_size else page_size[1]

    scale_factor = min(target_page_width / width, target_page_height / height)
    
    print(f"SVG scale factor: {scale_factor}")

    # Apply transformations to fit the page
    doc.scale(scale_factor)
    
    execute("linesimplify -t 0.1mm", doc)

    execute("linesort", doc)

    #for lid, l in doc.layers.items():
    #    print(l)

    config = Path('config/vpype-gcode.toml').read_text()

    config = config.replace('{{pen_speed}}', pen_speed) \
        .replace('{{pen_up_delay}}', pen_up_delay) \
        .replace('{{pen_down_delay}}', pen_down_delay)

    with tempfile.NamedTemporaryFile(mode='w', suffix='.toml') as tmp_config:
        tmp_config.write(config)
        tmp_config.flush()

        vpype.config_manager.load_config_file(tmp_config.name)

        if split_layers:
            execute(f"forlayer gwrite --profile 4xidraw {output_gcode}%_lid%.gcode end", doc)
        else:
            execute(f"gwrite --profile 4xidraw {output_gcode}.gcode", doc)

    return width, height

if __name__ == "__main__":
    
    input_svg = 'spiro-2.svg'
    output_gcode = 'spiro-2-2.gcode'
    canvas_width, canvas_height = process_svg_to_gcode(input_svg, output_gcode)

    print(f"Canvas size: {canvas_width} x {canvas_height}")