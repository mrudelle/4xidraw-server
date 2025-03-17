from dataclasses import dataclass
import re
import math
import sys

@dataclass
class GrblSettings:
    max_rate_x: float = 3000.0  # mm/min
    max_rate_y: float = 3000.0  # mm/min
    acceleration_x: float = 800.0  # mm/s^2
    acceleration_y: float = 800.0  # mm/s^2

@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0

@dataclass
class Velocity:
    x: float = 0.0
    y: float = 0.0

@dataclass
class Bounds:
    min_x: float = float('inf')
    max_x: float = float('-inf')
    min_y: float = float('inf')
    max_y: float = float('-inf')

    def update(self, point: Point):
        self.min_x = min(self.min_x, point.x)
        self.max_x = max(self.max_x, point.x)
        self.min_y = min(self.min_y, point.y)
        self.max_y = max(self.max_y, point.y)

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

class GCodeSimulator:
    def __init__(self, settings: GrblSettings):
        self.settings = settings
        self.current_pos = Point()
        self.current_vel = Velocity()
        self.current_feed = 0.0
        self.total_time = 0.0
        self.bounds = Bounds()
        self.debug = False
        
    def _parse_coord(self, line: str):
        new_pos = Point(self.current_pos.x, self.current_pos.y)
        feed = self.current_feed
        
        x_match = re.search(r'X([-\d.]+)', line)
        y_match = re.search(r'Y([-\d.]+)', line)
        f_match = re.search(r'F([-\d.]+)', line)
        
        if x_match: new_pos.x = float(x_match.group(1))
        if y_match: new_pos.y = float(y_match.group(1))
        if f_match: feed = float(f_match.group(1))
            
        return new_pos, feed

    def _parse_dwell(self, line: str) -> float:
        p_match = re.search(r'P([-\d.]+)', line)
        s_match = re.search(r'S([-\d.]+)', line)
        
        if p_match:  # P is in milliseconds
            return float(p_match.group(1)) / 1000
        elif s_match:  # S is in seconds
            return float(s_match.group(1))
        return 0

    def _calculate_axis_move(self, start: float, end: float, start_vel: float, 
                           max_feed: float, acceleration: float) -> tuple[float, float]:
        distance = abs(end - start)
        direction = 1 if end > start else -1
        
        if distance == 0:
            return 0.0, start_vel

        # Convert target velocity to mm/s
        max_vel = min(max_feed, self.current_feed) / 60.0
        
        # If we're changing direction, we need to stop first
        if math.copysign(1, start_vel) != direction and start_vel != 0:
            decel_time = abs(start_vel) / acceleration
            if self.debug:
                print(f"Direction change: stopping from {start_vel:.2f} mm/s takes {decel_time:.3f}s")
            self.current_vel.x = 0
            self.current_vel.y = 0
            return decel_time, 0.0
            
        # Calculate max reachable velocity given the distance
        # v² = u² + 2as
        max_reachable = math.sqrt(abs(start_vel * start_vel + 2 * acceleration * distance))
        target_vel = min(max_vel, max_reachable) * direction
        
        if abs(target_vel) < abs(start_vel):
            # Need to decelerate
            t = (abs(start_vel) - abs(target_vel)) / acceleration
            if self.debug:
                print(f"Decel: {abs(start_vel):.2f} to {abs(target_vel):.2f} mm/s in {t:.3f}s")
            return t, target_vel
        else:
            # Need to accelerate
            t = (abs(target_vel) - abs(start_vel)) / acceleration
            if self.debug:
                print(f"Accel: {abs(start_vel):.2f} to {abs(target_vel):.2f} mm/s in {t:.3f}s")
            return t, target_vel

    def _calculate_move_time(self, start: Point, end: Point, feed: float) -> float:
        if feed == 0:
            feed = self.current_feed
        
        # Calculate time for each axis
        time_x, end_vel_x = self._calculate_axis_move(
            start.x, end.x, self.current_vel.x,
            self.settings.max_rate_x, self.settings.acceleration_x
        )
        
        time_y, end_vel_y = self._calculate_axis_move(
            start.y, end.y, self.current_vel.y,
            self.settings.max_rate_y, self.settings.acceleration_y
        )
        
        # Total time is the max of the two axis times
        total_time = max(time_x, time_y)
        
        # Update velocities
        self.current_vel.x = end_vel_x
        self.current_vel.y = end_vel_y
        
        if self.debug:
            dx = end.x - start.x
            dy = end.y - start.y
            distance = math.sqrt(dx*dx + dy*dy)
            print(f"Move: ({start.x:.1f},{start.y:.1f}) -> ({end.x:.1f},{end.y:.1f})")
            print(f"Distance: {distance:.1f}mm, Time: {total_time:.3f}s")
            print(f"End velocity: {self.current_vel.x:.1f}, {self.current_vel.y:.1f} mm/s\n")
        
        return total_time

    def estimate_time(self, gcode: str) -> tuple[float, Bounds]:
        """Estimate the time to execute the G-code and return time and bounds"""
        BLOCK_PROCESSING_TIME = 0.020  # 20ms per block overhead
        ACCELERATION_PLANNING_TIME = 0.015  # 15ms for acceleration planning
        SERIAL_DELAY = 0.010  # 10ms serial communication overhead
        SPINDLE_CHANGE_TIME = 0.000  # 500ms for pen up/down
        MIN_MOVE_TIME = 0.050  # 50ms minimum for any movement
        
        lines = gcode.strip().split('\n')
        self.bounds.update(self.current_pos)
        
        for line in lines:
            line = line.strip().upper()
            
            if not line or line.startswith(';') or line.startswith('('):
                continue
                
            # Add serial and processing overhead for each non-comment line
            self.total_time += BLOCK_PROCESSING_TIME + SERIAL_DELAY
                
            if any(cmd in line for cmd in ['G0', 'G1']):
                target_pos, feed = self._parse_coord(line)
                
                if 'G0' in line:
                    feed = max(self.settings.max_rate_x, self.settings.max_rate_y)
                
                if feed == 0:
                    feed = self.current_feed if self.current_feed > 0 else self.settings.max_rate_x
                
                move_time = self._calculate_move_time(self.current_pos, target_pos, feed)
                self.total_time += max(move_time, MIN_MOVE_TIME) + ACCELERATION_PLANNING_TIME
                
                self.current_pos = target_pos
                self.current_feed = feed
                self.bounds.update(self.current_pos)
            
            elif 'G4' in line:
                self.current_vel = Velocity()  # Full stop
                self.total_time += self._parse_dwell(line)
            elif line.startswith('M3'):
                self.total_time += SPINDLE_CHANGE_TIME  # Pen up/down time
                    
        return self.total_time, self.bounds

if __name__ == '__main__':
    # Example usage
    settings = GrblSettings(
        max_rate_x=3000,      # mm/min
        max_rate_y=3000,      # mm/min
        acceleration_x=800,   # mm/s^2
        acceleration_y=800    # mm/s^2
    )
    
    simulator = GCodeSimulator(settings)
    simulator.debug = True
    
    test_gcode = sys.stdin.read()
    
    time, bounds = simulator.estimate_time(test_gcode)
    print(f"Estimated time: {time:.2f} seconds")
    print(f"Bounds:")
    print(f"  X: {bounds.min_x:.1f} to {bounds.max_x:.1f} (width: {bounds.width:.1f}mm)")
    print(f"  Y: {bounds.min_y:.1f} to {bounds.max_y:.1f} (height: {bounds.height:.1f}mm)")