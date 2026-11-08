"""Render the actual CXM Klipper Jinja guard with simulated live status."""
from pathlib import Path
import unittest
import jinja2

SOURCE=Path(__file__).resolve().parents[1]/"vendor"/"cxm"/"cxm_fast_guard.cfg"
MOTORS=("stepper_x","stepper_y","stepper_z","stepper_z1","stepper_z2","stepper_z3")

def make_macro():
    raw=SOURCE.read_text("utf-8")
    body=raw.split("gcode:\n",1)[1]
    # Same nonstandard Klipper delimiters in klippy/extras/gcode_macro.py
    env=jinja2.Environment('{%','%}','{','}')
    return env.from_string(body)

def good_status():
    return {
        "toolhead":{"homed_axes":"xyz","position":[306.79,109.99,20.0,0.0]},
        "stepper_enable":{"steppers":{name:True for name in MOTORS}},
        "gcode_move":{"position":{"x":306.79,"y":109.99},
                      "gcode_position":{"x":306.79,"y":109.99}},
        "gcode_button cxm_tool_detect":{"state":"RELEASED"},
        "virtual_sdcard":{"is_active":False},
        "pause_resume":{"is_paused":False},
        "print_stats":{"state":None},
    }

def evaluate(status,expect="RELEASED",**params):
    data={"EXPECT":expect}
    data.update(params)
    def fail(message):
        raise RuntimeError(message)
    return make_macro().render(printer=status,params=data,
                               action_raise_error=fail)

class MacroTests(unittest.TestCase):
    def test_gate_accepts_live_expected_empty_and_mounted_with_correct_park(self):
        status=good_status()
        evaluate(status,MIN_Y="109.0",X="306.79",Y="109.99")
        status["gcode_button cxm_tool_detect"]["state"]="PRESSED"
        evaluate(status,"PRESSED",X="306.79",Y="109.99")

    def test_sensor_disagreement_or_unavailable_fails_closed(self):
        status=good_status()
        with self.assertRaisesRegex(RuntimeError,"not PRESSED"):
            evaluate(status,"PRESSED")
        status["gcode_button cxm_tool_detect"]["state"]="UNKNOWN"
        with self.assertRaisesRegex(RuntimeError,"carriage not"):
            evaluate(status)
        status.pop("gcode_button cxm_tool_detect")
        with self.assertRaises(Exception):
            evaluate(status)

    def test_wrong_coordinates_active_xy_offset_and_clearance_fail(self):
        status=good_status()
        with self.assertRaisesRegex(RuntimeError,"safe Y"):
            evaluate(status,MIN_Y="110.40")
        with self.assertRaisesRegex(RuntimeError,"staging X"):
            evaluate(status,X="310")
        with self.assertRaisesRegex(RuntimeError,"staging Y"):
            evaluate(status,Y="114")
        status["toolhead"]["position"][2]=19.9
        with self.assertRaisesRegex(RuntimeError,"below 20"):
            evaluate(status)
        status["toolhead"]["position"][2]=20
        status["gcode_move"]["gcode_position"]["x"]=300
        with self.assertRaisesRegex(RuntimeError,"XY origin"):
            evaluate(status)
        status["gcode_move"]["gcode_position"]["x"]=306.79
        status["gcode_move"]["gcode_position"]["y"]=106.79
        with self.assertRaisesRegex(RuntimeError,"XY origin"):
            evaluate(status)

    def test_active_print_pause_unhomed_and_powered_down_motor_fail(self):
        status=good_status()
        status["toolhead"]["homed_axes"]=""
        with self.assertRaisesRegex(RuntimeError,"XYZ are not homed"):
            evaluate(status)
        status["toolhead"]["homed_axes"]="xyz"
        status["stepper_enable"]["steppers"]["stepper_z3"]=False
        with self.assertRaisesRegex(RuntimeError,"motor not powered"):
            evaluate(status)
        status["stepper_enable"]["steppers"]["stepper_z3"]=True
        status["pause_resume"]["is_paused"]=True
        with self.assertRaisesRegex(RuntimeError,"printer is paused"):
            evaluate(status)
        status["pause_resume"]["is_paused"]=False
        status["virtual_sdcard"]["is_active"]=True
        with self.assertRaisesRegex(RuntimeError,"virtual SD printing"):
            evaluate(status)
        status["virtual_sdcard"]["is_active"]=False
        status["print_stats"]["state"]="printing"
        with self.assertRaisesRegex(RuntimeError,"active print"):
            evaluate(status)

    def test_unregistered_optional_print_objects_do_not_block_manual_gcode(self):
        status=good_status()
        for name in ("virtual_sdcard","pause_resume","print_stats"):
            status.pop(name)
        evaluate(status)

if __name__=='__main__':unittest.main()
