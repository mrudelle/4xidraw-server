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


def gen_gcode(svg_file, split_layers, page_size, output_file):
    if not output_file:
        path = Path(svg_file)
        output_file = str(path.parent / path.stem) 
    
    process_svg_to_gcode(svg_file, output_file, target_page_size=page_size, split_layers=split_layers)


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

    args = parser.parse_args()

    if args.action == 'send_command':
        send_command(args.command)

    elif args.action == 'plot_file':
        plot_gcode(args.gcode_file)

    elif args.action == 'gen_gcode':
        gen_gcode(args.svg_file, args.split_layers, args.target_page_size, args.output)

    else:
        print(f'Unrecognized command {args.action}')