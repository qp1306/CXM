"""Pure math for CXM XY dock measurement: NO hardware, network or G-code.

Only accepts VERIFIED signed motor-step travel and verified endstop positions.
Never calls Klipper, moves steppers or saves configuration.
"""
from __future__ import annotations
from dataclasses import dataclass
import math


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _pair(value, name):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError(f"{name} must have two motor-step deltas")
    return (_number(value[0], name + ".A"), _number(value[1], name + ".B"))


@dataclass(frozen=True)
class CoreXYTransform:
    """Matrix [A_steps, B_steps] = [[ax,ay],[bx,by]] * [X_mm,Y_mm].

    Calibrate using known separate X-only and Y-only moves on a HOMED
    printer. Never assume fixed CoreXY motor direction or rotation distance.
    """
    ax: float
    ay: float
    bx: float
    by: float

    @classmethod
    def calibrate(cls, known_x_mm, x_motor_steps, known_y_mm, y_motor_steps):
        x = _number(known_x_mm, "known_x_mm")
        y = _number(known_y_mm, "known_y_mm")
        if abs(x) < 1.0 or abs(y) < 1.0:
            raise ValueError("Calibration moves must each be at least 1 mm")
        xa, xb = _pair(x_motor_steps, "x_motor_steps")
        ya, yb = _pair(y_motor_steps, "y_motor_steps")
        candidate = cls(xa/x, ya/y, xb/x, yb/y)
        candidate._validate()
        return candidate

    def _validate(self):
        nums=(self.ax,self.ay,self.bx,self.by)
        if not all(math.isfinite(x) for x in nums):
            raise ValueError("Non-finite CoreXY matrix")
        det=self.ax*self.by-self.ay*self.bx
        norm=max(abs(v) for v in nums)
        if norm<1.0 or abs(det)<1e-5*norm*norm:
            raise ValueError("Singular or badly conditioned CoreXY matrix")
        return det

    def cartesian_travel(self, motor_steps):
        a,b=_pair(motor_steps,"motor_steps")
        det=self._validate()
        x=(self.by*a-self.ay*b)/det
        y=(-self.bx*a+self.ax*b)/det
        if not all(math.isfinite(v) for v in (x,y)):
            raise ValueError("Computed travel is not finite")
        return x,y


@dataclass(frozen=True)
class DockXYResult:
    raw_x: float
    raw_y: float
    x_travel: float
    y_travel: float
    x_cross_axis: float
    y_cross_axis: float
    status: str = "PROVISIONAL_UNVERIFIED"


def infer_dock_xy(*, matrix, y_home_motor_steps, x_home_motor_steps,
                  x_endstop, y_endstop, x_bounds, y_bounds,
                  positive_x_home=True, positive_y_home=True,
                  cross_axis_tolerance_mm=0.15):
    """Infer manual starting XY from *verified* endstop-driven travel.

    Y-home runs first and must produce almost no X travel. X-home runs
    second and must produce almost no Y travel. This function assumes the
    two raw capture segments contain exactly those travel moves (not
    retracts, Z moves, park moves or extra homing operations).

    This is only candidate coordinate arithmetic, NOT an accepted dock
    calibration and NOT proof of a reliable tool pickup.
    """
    if not isinstance(matrix,CoreXYTransform):
        raise ValueError("matrix must be CoreXYTransform")
    xstop=_number(x_endstop,"x_endstop")
    ystop=_number(y_endstop,"y_endstop")
    if not isinstance(positive_x_home,bool) or not isinstance(positive_y_home,bool):
        raise ValueError("Homing directions must be explicit booleans")
    tolerance=_number(cross_axis_tolerance_mm,"cross_axis_tolerance_mm")
    if not (0.0<=tolerance<=1.0):
        raise ValueError("Invalid cross-axis tolerance")
    def bounds(v,name):
        if not isinstance(v,(tuple,list)) or len(v)!=2:
            raise ValueError(name+" must be a (min,max) pair")
        low,high=_number(v[0],name+".min"),_number(v[1],name+".max")
        if low>=high:
            raise ValueError(name+" limits are invalid")
        return low,high
    xl,xh=bounds(x_bounds,"x_bounds")
    yl,yh=bounds(y_bounds,"y_bounds")
    y_cross,dy=matrix.cartesian_travel(y_home_motor_steps)
    dx,x_cross=matrix.cartesian_travel(x_home_motor_steps)
    if abs(y_cross)>tolerance or abs(x_cross)>tolerance:
        raise ValueError("Cross-axis movement detected during homing: reject measurement")
    if (dx<=0 if positive_x_home else dx>=0):
        raise ValueError("X movement direction contradicts expected homing direction")
    if (dy<=0 if positive_y_home else dy>=0):
        raise ValueError("Y movement direction contradicts expected homing direction")
    x=xstop-dx
    y=ystop-dy
    if not (xl<=x<=xh and yl<=y<=yh):
        raise ValueError("Inferred dock is outside the verified mechanical envelope")
    return DockXYResult(raw_x=x,raw_y=y,x_travel=dx,y_travel=dy,
                        x_cross_axis=x_cross,y_cross_axis=y_cross)
