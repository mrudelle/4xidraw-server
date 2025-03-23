import queue
import sys
import threading
import time
from serial import Serial

GRBL_BUFFER_SIZE_REFRESH_RATE = 0.05 # assumes motions are mostly 50ms long or more
GRBL_BUFFER_NICE_SIZE = 16 # max acceptable occupancy for the planner buffer
GRBL_BUFFER_NICE_SIZE_BLOCKING = 2 # for blocking commands like M3, empty most of the buffer first


class XidrawDevice():

    timeout = 100 # in seconds
    status_command = '?'

    def __init__(self, port: Serial):
        self.port = port
        self.serial_lock = threading.Lock()
        self.command_queue = queue.Queue()

    def command(self, command):
        """ 
        command is a \n terminated string 
        expects 'ok' from the board
        """
        
        try:

            with self.serial_lock:
            
                self.write(command)

                for _ in range(self.timeout * 5):
                    message = self.port.readline().decode().strip()
                    
                    if message == 'ok':
                        return
                    
                    if message != '':
                        print('Unexpected response from GRBL.') 
                        print(f'    Command: {command.strip()}')
                        print(f'    Response: {message}')
                
                print(f'GRBL serial Timeout')
                print(f'    Command: {command.strip()}')
                sys.exit()

        except Exception as e:
                print(f'Failed after command: {command.strip()}')
                print(e)
                sys.exit()
    
    def pipe_to(self, file, stop_signal: threading.Event = None):
        """ Pipe the output from the serial port to a file (eg. sys.stdout) """
        while stop_signal is None or not stop_signal.is_set():
            message = self.port.readline().decode().strip()
            if message.strip() != '':
                file.write(message + '\n')
                file.flush()

    def add_command(self, command):
        self.command_queue.put(command)

    def _grbl_sender_loop(self):

        self._ensure_buffer_report_enabled()

        while self.running:
            if self.command_queue.empty():
                # Nothing to send, short wait
                time.sleep(0.01)
                continue

            command = self.command_queue.get(block=False)
            buffer_nice_size = self.buffer_nice_size_for_command(command)

            # Wait for a free spot in the buffer
            while self.running:
                
                planning_buffer_occupancy = self.planning_buffer_occupancy()
                # print(f'Buffer occupancy: {planning_buffer_occupancy}')

                if planning_buffer_occupancy <= buffer_nice_size:
                    break

                time.sleep(GRBL_BUFFER_SIZE_REFRESH_RATE)

            # print(f'Sending command: {command.strip()}')
            self.command(command)
            self.command_queue.task_done()

    def _ensure_buffer_report_enabled(self):
        # Note: Only tested against GRBL 0.9
        message = self.query('$$\n')
        for line in message.split('\n'):
            if line.startswith('$10='):
                report_mask = int(line[4:].split(' ')[0])

                # Check if the buffer report mask is set
                if report_mask & 0b00000100 == 0:
                    new_report_mask = report_mask | 0b00000100
                    self.command(f'$10={new_report_mask}\n')
                    return
            
                return
        
        raise Exception(f'Buffer report mask not found in response to "$$": {message}')
    
    def planning_buffer_occupancy(self):
        # Note: Only tested against GRBL 0.9
        message = self.query(self.status_command + '\n')
        chunks = message.strip('<>').split(',')

        for chunk in chunks:
            if chunk.startswith('Buf:'):
                return int(chunk[4:])
        
        raise Exception(f'Buffer size not found in status message: {message}')
    
    def buffer_nice_size_for_command(self, command: str):
        # M3 commands are blocking
        # So we want want to wait until the buffer is almost empty
        if command.strip().startswith('M3'):
            return GRBL_BUFFER_NICE_SIZE_BLOCKING
        else:
            return GRBL_BUFFER_NICE_SIZE

    def query(self, command: str):
        try:

            with self.serial_lock:
                
                self.write(command)

                message = []

                # consume everything until 'ok'
                for _ in range(self.timeout * 5):
                    chunk = self.port.readline().decode().strip()

                    if chunk == 'ok':
                        return '\n'.join(message)
                    else:
                        message.append(chunk)

        except Exception as e:
            print(f'Failed after query: {command.strip()}')
            print(e)
            sys.exit()
    
    def write(self, command: str):
        self.port.write(command.encode('utf-8'))

    def close(self):
        self.port.close()
    
    def start(self):
        # Start the gcode sender thread
        self.running = True
        self.sender_thread = threading.Thread(target=self._grbl_sender_loop)
        self.sender_thread.daemon = True
        self.sender_thread.start()

    def wait_for_empty_queue(self):
        self.command_queue.join()

    def wait_for_empty_planner_buffer(self):
        while self.planning_buffer_occupancy() > 0:
            time.sleep(GRBL_BUFFER_SIZE_REFRESH_RATE)
    
    def stop_and_join(self):
        self.running = False
        self.sender_thread.join()