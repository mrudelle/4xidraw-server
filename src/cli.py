#!/usr/bin/env python3

import re
import argparse
from pathlib import Path
from gen_gcode import process_svg_to_gcode
from xidraw_finder import find_4xidraw_port
from wakepy import keep

def send_command(command):
    try:
        serial_port = find_4xidraw_port()

        if not serial_port:
            print('Could not initialize connection')
            exit(1)
        
        print(serial_port.query(command + '\n'))

        serial_port.close()
    except Exception as e:
        print(f"Error sending command: {e}")
        if serial_port:
            serial_port.close()



def plot_gcode(file):
    try:
        serial_port = find_4xidraw_port()

        if not serial_port:
            print('Could not initialize connection')
            exit(1)
        
        def send_g_code_file(file):

            with open(file, 'r') as f:
                for l in f.readlines():
                    # remove comments
                    l = re.sub(r';.+$', '', l)

                    if l.strip() == '':
                        continue

                    serial_port.command(l)

        with keep.running():
            send_g_code_file(file)

        serial_port.close()

    except Exception as e:
        print(f"Error plotting file: {e}")
        if serial_port:
            serial_port.close()


def gen_gcode(svg_file, split_layers, page_size, output_file, *, 
    pen_speed='2000',
    pen_up_delay='0.1', 
    pen_down_delay='0.2',
    exclude_layers=[],
    line_simplify_tolerance='0.1mm',
    line_sort=True
):
    if not output_file:
        path = Path(svg_file)
        output_file = str(path.parent / path.stem)
    
    process_svg_to_gcode(
        svg_file, 
        output_file, 
        target_page_size=page_size,
        split_layers=split_layers,
        pen_speed=pen_speed,
        pen_up_delay=pen_up_delay,
        pen_down_delay=pen_down_delay,
        exclude_layers=exclude_layers,
        line_simplify_tolerance=line_simplify_tolerance,
        line_sort=line_sort
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='G-code Utility CLI')

    subparsers = parser.add_subparsers(dest='action')

    # send_command sub-command
    parser_send = subparsers.add_parser('send_command', help='Query grbl interface')
    parser_send.add_argument('command', type=str, help='Command to send')

    # plot_file sub-command
    parser_plot = subparsers.add_parser('plot_file', help='Plot a G-code file')
    parser_plot.add_argument('gcode_file', type=str, help='G-code file to plot')

    # gen_gcode sub-command
    parser_gen = subparsers.add_parser('gen_gcode', help='Generate G-code from SVG file')
    parser_gen.add_argument('svg_file', type=str, help='SVG file to convert')
    parser_gen.add_argument('--split-layers', action='store_true', help='Split into separate layers')
    parser_gen.add_argument('--target-page-size', type=str, default='297x210mm', help='Target page size (default: horizontal A4)')
    parser_gen.add_argument('--output', type=str, help='Output file base name')
    parser_gen.add_argument('--pen-speed', type=str, default='2000', help='Pen movement speed')
    parser_gen.add_argument('--pen-up-delay', type=str, default='0.1', help='Delay after pen up movement')
    parser_gen.add_argument('--pen-down-delay', type=str, default='0.2', help='Delay after pen down movement')
    parser_gen.add_argument('--exclude-layers', type=str, default='', help='Layer IDs to exclude (comma separated)')
    parser_gen.add_argument('--line-simplify-tolerance', type=str, default='0.1mm', help='Line simplification tolerance')
    parser_gen.add_argument('--no-line-sort', action='store_false', dest='line_sort', help='Disable line sorting')
    parser_gen.set_defaults(line_sort=True)

    args = parser.parse_args()

    if args.action == 'send_command':
        send_command(args.command)

    elif args.action == 'plot_file':
        plot_gcode(args.gcode_file)

    elif args.action == 'gen_gcode':
        exclude_layers = args.exclude_layers.split(',') if args.exclude_layers else []
        gen_gcode(
            args.svg_file, 
            args.split_layers, 
            args.target_page_size, 
            args.output,
            pen_speed=args.pen_speed,
            pen_up_delay=args.pen_up_delay,
            pen_down_delay=args.pen_down_delay,
            exclude_layers=exclude_layers,
            line_simplify_tolerance=args.line_simplify_tolerance,
            line_sort=args.line_sort
        )

    else:
        print(f'Unrecognized command {args.action}')