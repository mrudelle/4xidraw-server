from dataclasses import dataclass
import datetime
import re
import math
import sys

@dataclass
class GrblSettings:
    max_rate_x: float = 3000.0  # mm/min ($110)
    max_rate_y: float = 3000.0  # mm/min ($111)
    max_accel_x: float = 800.0  # mm/s^2 ($120)
    max_accel_y: float = 800.0  # mm/s^2 ($121)
    junction_deviation: float = 0.01  # mm ($11)
    grbl_version: str = '0.9i'  # Version of GRBL used

@dataclass
class Point:
    x: float = 0.0
    y: float = 0.0

    def __sub__(self, other: 'Point') -> 'Point':
        return Point(self.x - other.x, self.y - other.y)
    
    def __add__(self, other: 'Point') -> 'Point':
        return Point(self.x + other.x, self.y + other.y)
    
    def length(self) -> float:
        return math.sqrt(self.x**2 + self.y**2)
    
    def normalize(self) -> 'Point':
        length = self.length()
        if length == 0:
            return Point(0, 0)
        return Point(self.x / length, self.y / length)
    
    def dot_product(self, other: 'Point') -> float:
        return self.x * other.x + self.y * other.y
    
    def abs(self) -> 'Point':
        return Point(abs(self.x), abs(self.y))

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

def is_motion_command(line: str) -> bool:
    return line.startswith('G0 ') or line.startswith('G1 ') or line.startswith('G00 ') or line.startswith('G01 ')

def is_rapid_motion_command(line: str) -> bool:
    return line.startswith('G0 ') or line.startswith('G00 ')

def is_go_home_command(line: str) -> bool:
    command = line.split(' ')
    command.sort()
    return command == ['G0', 'X0', 'Y0'] or command == ['G00', 'X0', 'Y0']

class GCodeSimulator:
    def __init__(self, settings: GrblSettings):
        self.settings = settings
        self.current_pos = Point()
        self.current_feed = 0.0
        self.total_time = 0.0
        self.bounds = Bounds()
        self.debug = False
        
    def _parse_coord(self, line: str, current_pos: Point, previous_feed) -> tuple[Point, float]:
        new_pos = Point(current_pos.x, current_pos.y)
        feed = previous_feed
        
        x_match = re.search(r'X([-\d.]+)', line)
        y_match = re.search(r'Y([-\d.]+)', line)


        f_match = re.search(r'F([-\d.]+)', line)
        
        if x_match: 
          new_pos.x = float(x_match.group(1))
        if y_match: 
          new_pos.y = float(y_match.group(1))
        if f_match: 
          feed = float(f_match.group(1))
            
        return new_pos, feed

    def _parse_dwell(self, line: str) -> float:
        p_match = re.search(r'P([-\d.]+)', line)
        s_match = re.search(r'S([-\d.]+)', line)
        
        if p_match:  
            # in grbl 9.9, P is in seconds
            if self.settings.grbl_version.startswith('0.9'):
                return float(p_match.group(1))

            # P is in milliseconds
            return float(p_match.group(1)) / 1000
        
        elif s_match:  # S is in seconds
            return float(s_match.group(1))
        
        return 0
    
    def calculate_junction_vmax(self, motion1, motion2):
        """
        Calculate the maximum junction speed for a CNC machine.

        Parameters:
        - unit_vector1: List representing the unit vector of the first segment.
        - unit_vector2: List representing the unit vector of the second segment.

        Returns:
        - vmax: Maximum junction speed (mm/min).
        """

        if (motion1.length() == 0) or (motion2.length() == 0):
            return 0

        motion1 = motion1.normalize()
        motion2 = motion2.normalize()

        # angle of the junction
        theta = math.acos(motion1.dot_product(motion2))

        # If the angle is very small, the head can pass the junction at max speed
        if abs(theta) < 1e-6:
          return max(self.settings.max_rate_x, self.settings.max_rate_y)

        junction_radius = self.settings.junction_deviation / math.sin(theta / 2)

        max_centripetal_acceleration = min(self.settings.max_accel_x, self.settings.max_accel_y)

        vmax_mm_s = math.sqrt(max_centripetal_acceleration * junction_radius)

        return vmax_mm_s * 60.0
    
    def max_speed_along_motion(self, motion: Point) -> float:
        """ Calculate the maximum feed rate reachable along motion vector """
        abs_motion_dir = motion.normalize().abs()

        return Point(
            self.settings.max_rate_x * abs_motion_dir.x / max(abs_motion_dir.x, abs_motion_dir.y),
            self.settings.max_rate_y * abs_motion_dir.y / max(abs_motion_dir.x, abs_motion_dir.y)
        ).length()
    
    def max_accel_along_motion(self, motion: Point) -> float:
        """ Calculate the maximum acceleration reachable along motion vector """
        abs_motion_dir = motion.normalize().abs()

        return Point(
            self.settings.max_accel_x * abs_motion_dir.x / max(abs_motion_dir.x, abs_motion_dir.y),
            self.settings.max_accel_y * abs_motion_dir.y / max(abs_motion_dir.x, abs_motion_dir.y)
        ).length()
    
    def _calculate_motion_time(
            self, 
            motion: Point, 
            start_velocity: float, 
            end_velocity: float, 
            max_velocity: float, 
            max_accel: float
        ) -> tuple[float, float]:
        """
        Calculate the minimum time required for a motion while respecting 
        max acceleration and max speed.

        It may happen that the end velocity cannot be reached so the real end_velocity is returned.

        Parameters:
        - motion: The motion vector (Point).
        - start_velocity: The starting velocity along the motion vector (float, mm/min).
        - end_velocity: The target velocity at the end of the motion (float, mm/min).
        - max_velocity: The feed rate for the motion (float, mm/min).
        - max_accel: The maximum acceleration for the motion (float, mm/s^2).

        Returns:
        - motion_time: The time required for the motion (float, seconds).
        - final_velocity: The final velocity (float, mm/min) at the end of the motion.
        """
        # Convert velocities from mm/min to mm/s
        start_velocity /= 60.0
        end_velocity /= 60.0
        max_velocity /= 60.0

        # total distance of the motion
        distance = motion.length()

        # Case 1: Can reach max velocity
        accel_distance = (max_velocity**2 - start_velocity**2) / (2 * max_accel)
        decel_distance = (max_velocity**2 - end_velocity**2) / (2 * max_accel)

        if accel_distance + decel_distance <= distance:
            # Accelerate to max velocity, cruise, then decelerate
            accel_time = (max_velocity - start_velocity) / max_accel
            decel_time = (max_velocity - end_velocity) / max_accel
            cruise_distance = distance - (accel_distance + decel_distance)
            cruise_time = cruise_distance / max_velocity
            total_time = accel_time + cruise_time + decel_time
            return total_time, end_velocity * 60.0  # Convert back to mm/min

        # Case 2: Cannot reach max velocity
        # Solve for the peak velocity achievable within the distance
        peak_velocity_squared = (
            (start_velocity**2 + end_velocity**2) / 2 +
            max_accel * distance
        )
        if peak_velocity_squared < 0:
            peak_velocity = 0
        else:
            peak_velocity = math.sqrt(peak_velocity_squared)

        if peak_velocity > max_velocity:
            peak_velocity = max_velocity

        # Recalculate distances for acceleration and deceleration
        accel_distance = (peak_velocity**2 - start_velocity**2) / (2 * max_accel)
        decel_distance = (peak_velocity**2 - end_velocity**2) / (2 * max_accel)

        if abs(accel_distance + decel_distance - distance) < 1e-6: # account for floating point errors
            # Accelerate to peak velocity, then decelerate
            accel_time = (peak_velocity - start_velocity) / max_accel
            decel_time = (peak_velocity - end_velocity) / max_accel
            total_time = accel_time + decel_time
            return total_time, end_velocity * 60.0  # Convert back to mm/min

        # Case 3: Constant deceleration, cannot reach end velocity
        if accel_distance + decel_distance > distance and start_velocity > end_velocity:
            # Solve for the achievable end velocity
            achievable_end_velocity_squared = (
                start_velocity**2 - 2 * max_accel * distance
            )
            achievable_end_velocity = math.sqrt(max(0, achievable_end_velocity_squared))
            decel_time = (start_velocity - achievable_end_velocity) / max_accel
            return decel_time, achievable_end_velocity * 60.0  # Convert back to mm/min

        # Case 4: Constant acceleration, cannot reach end velocity
        if accel_distance + decel_distance > distance and start_velocity < end_velocity:
            # Solve for the achievable end velocity
            achievable_end_velocity_squared = (
                start_velocity**2 + 2 * max_accel * distance
            )
            achievable_end_velocity = math.sqrt(max(0, achievable_end_velocity_squared))
            accel_time = (achievable_end_velocity - start_velocity) / max_accel
            return accel_time, achievable_end_velocity * 60.0  # Convert back to mm/min

        # Default case (should not happen)
        #return 0.0, start_velocity * 60.0  # No motion
        raise ValueError("Cannot calculate motion time")
    
    def estimate_time(self, gcode: str) -> tuple[float, Bounds]:
        velocity = 0.0
        last_feed = min(self.settings.max_rate_x, self.settings.max_rate_y)
        position = Point()  # assume we start at 0,0

        lines = gcode.strip().split('\n')

        total_time = 0.0
        bounds = Bounds()

        for i in range(len(lines)):
            line = lines[i].strip().upper()
            next_line = lines[i + 1].strip().upper() if i + 1 < len(lines) else None

            # skip comment lines
            if not line or line.startswith(';') or line.startswith('('):
                continue

            if is_motion_command(line):
                target_pos, target_feed = self._parse_coord(line, position, last_feed)
                last_feed = target_feed
                next_pos, _ = self._parse_coord(next_line, target_pos, velocity) if next_line and is_motion_command(next_line) else (target_pos, None)

                # calculate the bounds of the drawing, but ignore the last G0 X0 Y0 (return to home) 
                if i != len(lines) - 1 or not is_go_home_command(line):
                    bounds.update(target_pos)

                motion = target_pos - position
                next_motion = next_pos - target_pos

                if motion.length() == 0:
                    continue

                max_target_feed = self.max_speed_along_motion(motion)
                max_target_accel = self.max_accel_along_motion(motion)

                if is_rapid_motion_command(line) or (target_feed <= 0):
                    target_feed = max_target_feed
                else:
                    target_feed = min(target_feed, max_target_feed)

                # max possible velocity at the end of this move
                junction_vmax = self.calculate_junction_vmax(motion, next_motion)

                # realistic target end velocity
                end_velocity = min(target_feed, junction_vmax)

                motion_time, real_end_velocity = self._calculate_motion_time(motion, velocity, end_velocity, target_feed, max_target_accel)

                if (real_end_velocity - end_velocity > 1e-6):
                    print(f"Warning: Could not reach target feed rate at line {i + 1} ({real_end_velocity:.2f} < {end_velocity:.2f})")
                elif (real_end_velocity - end_velocity < -1e-6):
                    print(f"Warning: Exceeded target feed rate at line {i + 1} ({real_end_velocity:.2f} > {end_velocity:.2f})")
                    real_end_velocity = end_velocity

                velocity = real_end_velocity
                position = target_pos
                total_time += motion_time

            elif 'G4' in line:
                dwell_time = self._parse_dwell(line)
                total_time += dwell_time

            elif line.startswith('M3'):
                pass # pen down and up are followed or preceded by dwell commands

        return total_time, bounds

if __name__ == '__main__':
    # Example usage
    settings = GrblSettings(
        max_rate_x=3000,      # mm/min
        max_rate_y=3000,      # mm/min
        max_accel_x=800,   # mm/s^2
        max_accel_y=800,    # mm/s^2
        junction_deviation=0.01,  # mm
    )
    
    simulator = GCodeSimulator(settings)
    simulator.debug = True
    
    test_gcode = sys.stdin.read()
    
    time, bounds = simulator.estimate_time(test_gcode)
    print(f"Estimated execution time: {datetime.timedelta(seconds=round(time))}")
    print(f"Bounds:")
    print(f"  X: {bounds.min_x:.1f} to {bounds.max_x:.1f} (width: {bounds.width:.1f}mm)")
    print(f"  Y: {bounds.min_y:.1f} to {bounds.max_y:.1f} (height: {bounds.height:.1f}mm)")