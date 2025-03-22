import queue
import sys
import threading
import time
from serial import Serial

class XidrawDevice():

    timeout = 100 # in seconds
    status_command = '?'

    def __init__(self, port: Serial):
        self.port = port
        self.serial_lock = threading.Lock()
        self.command_queue = queue.Queue()

        # Pauses sending commands the grbl buffer reaches this size
        self.buffer_nice_size = 14

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

            if not self._is_planning_buffer_free():
                # Buffer is full, wait before checking again
                time.sleep(0.1)
                continue

            command = self.command_queue.get(block=False)
            self.command(command)
            self.command_queue.task_done()

    def _ensure_buffer_report_enabled(self):

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
    
    def _is_planning_buffer_free(self):
        message = self.query(self.status_command + '\n')
        chunks = message.strip('<>').split(',')

        for chunk in chunks:
            if chunk.startswith('Buf:'):
                buffer_size = int(chunk[4:])
                
                return buffer_size < self.buffer_nice_size
        
        raise Exception(f'Buffer size not found in status message: {message}')

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
        while not self._is_planning_buffer_free():
            time.sleep(0.1)
    
    def stop_and_join(self):
        self.running = False
        self.sender_thread.join()