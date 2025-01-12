import sys
import serial
import serial.tools.list_ports

def open_4xidraw_port(port):

    try:
        ser = serial.Serial(
            port, 
            baudrate=115200, 
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

def find_4xidraw_port():
    """
    Finds the serial port connected to a 4xidraw device.

    Returns:
        str: The port name if found, otherwise None.
    """
    xidraw_ports = [
        p.device
        for p in serial.tools.list_ports.comports()
        if 'usb' in p.description.lower() or 'arduino' in p.device.lower() or 'ttyUSB' in p.device
    ]

    if not xidraw_ports:
        print("No 4xidraw device found.")
        return None
    
    for port in xidraw_ports:
        xidraw_port = open_4xidraw_port(port)
        if xidraw_port:
            return Xidraw(xidraw_port)

    print("4xidraw device could not be identified.")
    return None


class Xidraw():

    def __init__(self, port):
        self.port = port

    def command(self, command):
        """ 
        command is a \n terminated string 
        expects 'ok' from the board
        """
        
        try:
            self.port.write(command.encode('utf-8'))

            for _ in range(500): # give 100s for the board to respond
                message = self.port.readline().decode().strip()
                
                if message.strip() == 'ok':
                    return
                
                if message != '':
                    print('Unexpected response from GRBL.') 
                    print(f'    Command: {command.strip()}')
                    print(f'    Response: {message.strip()}')
            
            print(f'GRBL serial Timeout')
            print(f'    Command: {command.strip()}')
            sys.exit()

        except Exception as e:
                print(f'Failed after command: {command.strip()}')
                print(e)
                sys.exit()
    
    def query(self, command):
        """ TODO """
        pass

    def close(self):
        self.port.close()


if __name__ == '__main__':
    
    xidraw = find_4xidraw_port()
    if not xidraw:
        print("No 4xidraw port found.")
        sys.exit()

    print(f"4xidraw device found on port: {xidraw.port.name}")

    xidraw.command('G90\n')

    xidraw.command('M3 S80;\n')
    
    xidraw.close()