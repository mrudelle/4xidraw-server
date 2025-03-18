import sys
import serial
import serial.tools.list_ports
from serial.tools.list_ports_common import ListPortInfo

from serial_device.xidraw_device import XidrawDevice

def open_4xidraw_port(port, baudrate=115200):

    try:
        ser = serial.Serial(
            port, 
            baudrate=baudrate,
            timeout=.2, 
            dsrdtr=True, 
            rtscts=False
        )

        for _ in range(15): # give 3s for the board to init
            message = ser.readline().decode().strip()
            if message.startswith('Grbl '):
                print(message)
                return ser

        # trigger a soft reset
        print('Soft reset')
        ser.write(b'\x18')

        for _ in range(15): # give 3s for the board to init
            message = ser.readline().decode().strip()
            if message.startswith('Grbl '):
                print(message)
                return ser

    except (OSError, serial.SerialException):
        pass
    
    ser.close()
    return None


def is_compatible_device(port: ListPortInfo):
    description = port.description.lower()
    device = port.device.lower()
    return (
        'usb' in description or 
        'arduino' in description or
        'arduino' in device or 
        'ttyUSB' in device
    )


def find_4xidraw_port():
    """
    Finds the serial port connected to a 4xidraw device.
    """
    xidraw_ports = [
        p.device
        for p in serial.tools.list_ports.comports()
        if is_compatible_device(p)
    ]

    for port in xidraw_ports:
        xidraw_port = open_4xidraw_port(port)
        if xidraw_port:
            return XidrawDevice(xidraw_port)
    
    print("No compatible device found. Available ports:")

    for p in serial.tools.list_ports.comports():
        reason ='invalid response' if p in xidraw_ports else 'not a match'
        print(f"\t{p.device}: {p.description} [{reason}]")
    
    return None


if __name__ == '__main__':
    
    xidraw = find_4xidraw_port()
    if not xidraw:
        print("No 4xidraw port found.")
        sys.exit()

    print(f"4xidraw device found on port: {xidraw.port.name}")

    xidraw.command('G90\n')

    xidraw.command('M3 S80;\n')
    
    xidraw.close()