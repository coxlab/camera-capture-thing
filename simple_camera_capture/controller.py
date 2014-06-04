#!/usr/bin/env python
# -*- coding: utf-8 -*-

from ctypes import *
import logging
import sys

import time
import httplib

import numpy as np
from numpy import *
from scipy import *

from simple_camera_capture.util import *

from simple_camera_capture.image_processing import ImageDumper
from simple_camera_capture.camera import *
from simple_camera_capture.led import *
from simple_camera_capture.motion import *
from settings import global_settings

try:
    import queue
except ImportError:
    import Queue as queue

# load settings
loaded_config = load_config_file('~/.simple_camera_capture/config.ini')
global_settings.update(loaded_config)

# boost.python wrapper for a MWorks interprocess conduit, if you're into
# that sort of thing
mw_enabled = False

if global_settings.get('enable_mw_conduit', True):

    try:
        sys.path.append('/Library/Application Support/MWorks/Scripting/Python')
        import mworks.conduit as mw_conduit
        GAZE_INFO = 100
        TRACKER_INFO = 101
        mw_enabled = True
    except Exception, e:
        logging.warning('Unable to load MW conduit: %s' % e)



# A catch-all class for controlling the eyetracking hardware

class CaptureController(object):

    def __init__(self):

        # motion control settings
        self.x_set = 0.5
        self.y_set = 0.5
        self.r_set = 0.5

        self.zoom_step = 20.
        self.focus_step = 20.
        self.no_powerzoom = False

        self.x_current = 0.0
        self.y_current = 0.0
        self.r_current = 0.0
        self.d_current = 0.0
        self.rp_current = 0.0
        self.pixels_per_mm_current = 0.0
        self.zoom_current = 0.0
        self.focus_current = 0.0

        # led settings
        self.IsetCh1 = 0.0
        self.IsetCh2 = 0.0
        self.IsetCh3 = 0.0
        self.IsetCh4 = 0.0

        # camera settings
        self.test_binning = 3
        self.binning_factor = 1
        self.gain_factor = 1.

        self.camera_device = None

        self.camera_locked = 0
        self.continuously_acquiring = 0
        self.frame_rate = 0


        # MWorks communication, if available
        self.mw_conduit = None


        # UI
        self.canvas_update_timer = None
        self.ui_queue = queue.Queue(5)

        self.target_ui_update_interval = 1 / 30.
        self.last_ui_get_time = time.time()
        self.last_ui_put_time = time.time()

        self.enable_save_to_disk = global_settings.get('enable_save_to_disk', False)
        logging.info("Save to disk?: %d" % self.enable_save_to_disk)
        self.image_save_dir = global_settings.get('data_dir', None)

        self.use_simulated = global_settings.get('use_simulated', False)
        self.use_file_for_cam = global_settings.get('use_file_for_camera',
                                                    False)


    def initialize(self):

        # -------------------------------------------------------------
        # LED Controller
        # -------------------------------------------------------------
        logging.info('Initializing LED Control Subsystem')

        if not self.use_simulated:
            try:
                self.leds = MightexLEDController('169.254.0.9', 8006)
                self.leds.connect()
            except:
                self.leds = None

        if self.use_simulated or self.leds is None:
            self.leds = SimulatedLEDController(4)

        # -------------------------------------------------------------
        # Camera
        # -------------------------------------------------------------

        logging.info('Initializing Camera')

        try:
            if not self.use_file_for_cam:
                logging.info('Connecting to Camera...')
                self.camera_device = ProsilicaCameraDevice()

                self.binning = 4
                self.gain = 1

        except Exception, e:
                logging.warning("Error connecting to camera: %s" % e.message)
                self.camera_device = None

        # if that didn't work, build a fake device
        if self.use_file_for_cam or self.camera_device is None:
            fake_file = global_settings.get('fake_cam_file', None)
            if fake_file is None:
                logging.error('No valid fake camera file specified')

            self.camera_device = FakeCameraDevice(fake_file)
            self.camera_device.acquire_image()


        logging.info('Starting continuous camera acquisition')

        self.start_continuous_acquisition()

        self.ui_interval = 1. / 10000.
        self.start_time = time.time()
        self.last_time = self.start_time
        self.conduit_fps = 0.


        # -------------------------------------------------------------
        # Image "dumper" (put images to file system)
        # -------------------------------------------------------------

        if self.image_save_dir:
            self.image_dumper = ImageDumper(self.image_save_dir)
        else:
            self.image_dumper = None


        # -------------------------------------------------------------
        # Set up the MW communications
        # -------------------------------------------------------------

        if mw_enabled:
            logging.info('Instantiating mw conduit')
            self.mw_conduit = mw_conduit.IPCServerConduit('cobra1')
            # print 'conduit = %s' % self.mw_conduit
        else:
            self.mw_conduit = None

        if self.mw_conduit != None:
            logging.info('Initializing conduit...')
            initialized = self.mw_conduit.initialize()
            # print initialized
            if not initialized:
                logging.warning('Failed to initialize conduit')

            logging.info('Sending dummy data (-1000,-1000,-1000)')
            self.mw_conduit.send_data(GAZE_INFO, (-1000, -1000, -1000))
            logging.info('Finished testing conduit')
        else:
            logging.warning('No conduit')

    def release(self):
        return

    def __del__(self):
        print "controller.__del__ called"
        sys.stdout.flush()

    def shutdown(self):

        # Put on the brakes

        if self.leds is not None:
            logging.info('Turning off LEDs')
            for i in xrange(4):
                self.leds.turn_off(i)
            self.leds = None

        self.continuously_acquiring = False
        self.stop_continuous_acquisition()

        #self.camera_update_timer.invalidate()

        time.sleep(1)

        self.camera_device.shutdown()

        self.calibrator = None
        # self.camera = None
        self.camera_device = None

        return True

    def simple_alert(self, title, message):
        logging.info(message)

    def dump_info_to_conduit(self):

        # TODO
        print("Dumping info to conduit")
        try:
            if not mw_enabled:
                return

            # info = {'stages': self.stages.info,
            #         'calibration': self.calibrator.info}

            # self.mw_conduit.send_data(TRACKER_INFO, info)
        except Exception as e:
            # these are all "nice-to-haves" at this point
            # so don't risk crashing, just yet
            logging.warning("Failed to dump info: %s" % e)
            return


    def start_continuous_acquisition(self):
        self.dump_info_to_conduit()

        logging.info('Starting continuous acquisition')
        self.continuously_acquiring = 1

        # Run an infinite camera acquisition loop in another thread
        t = lambda: self.continuously_acquire_images()
        self.acq_thread = threading.Thread(target=t)
        self.acq_thread.start()

    def stop_continuous_acquisition(self):
        logging.info('Stopping continuous acquisition')
        self.continuously_acquiring = 0
        self.acq_thread.join()

    def ui_queue_put(self, item):

        now = time.time()
        interval = now - self.last_ui_put_time

        if interval < self.target_ui_update_interval:
            return
        else:
            pass

        # if self.ui_queue.full():
        #     try:
        #         self.ui_queue.get_nowait()
        #     except Empty:
        #         return
        try:
            self.ui_queue.put(item)
            self.last_ui_put_time = now
        except queue.Full:
            return

    def ui_queue_get(self):

        # now = time.time()
        # interval = now - self.last_ui_get_time

        # if interval < self.target_ui_update_interval:
        #     return None

        # try:
        #     f = self.ui_queue.get_nowait()
        #     self.last_ui_get_time = now
        #     return f
        # except queue.Empty:
        #     return None

        try:
            return self.ui_queue.get()
        except queue.Empty:
            return None

    # for pyro invocation

    def get_property(self, p):
        v = self
        for k in p.split('.'):
            if getattr(v, k):
                v = hasattr(v, k)
            # if k in v.__dict__:
            #     v = v.__dict__[k]
            else:
                return None

        return v

    def set_property(self, p, val):
        print 'setting prop ' + p
        v = self
        keys = p.split('.')

        for k in keys[0:-1]:
            v = getattr(v, k)        
        # for k in keys[0:-1]:
        #     v = v.__dict__[k]

        # if keys[-1] in v.__dict__:
        #     print 'val was: ', v.__dict__[keys[-1]]
        print 'val now is: ', val

        # v.__dict__[keys[-1]] = val
        setattr(v, keys[-1], val)

    def update_parameters(self, p):
        o = p.split('.')[0]
        try:
            o.update_parameters()
        except:
            pass

    def get_frame_rate(self):
        return self.frame_rate

    # a method to actually run the camera
    # it will push images into a Queue object (in a non-blocking fashion)
    # so that the UI can have at them
    def continuously_acquire_images(self):

        logging.info('Started continuously acquiring...')

        self.frame_rate = -1.
        frame_number = 0
        tic = time.time()
        features = None
        gaze_azimuth = 0.0
        gaze_elevation = 0.0
        calibration_status = 0

        self.last_conduit_time = time.time()

        check_interval = 100

        while self.continuously_acquiring:
            self.camera_locked = 1

            try:

                new_features = self.camera_device.acquire_image()

                # if (new_features.__class__ == dict and
                #     features.__class__ == dict and
                #     'frame_number' in new_features and
                #     'frame_number' in features and
                #     new_features['frame_number'] != features['frame_number']):
                #     frame_number += 1
                # else:
                #     next

                frame_number += 1

                features = new_features

                if frame_number % check_interval == 0:
                    toc = time.time() - tic
                    self.frame_rate = check_interval / toc
                    # logging.info('Real frame rate: %f' % (check_interval / toc))
                    # logging.info('Real frame time: %f' % (toc / check_interval))
                    # if features.__class__ == dict and 'frame_number' in features:
                    #     logging.info('frame number = %d'
                    #                  % features['frame_number'])

                    tic = time.time()

                sys.stdout.write('frame rate: %f' % self.frame_rate)

                if features == None:
                    logging.error('No features found... sleeping')
                    time.sleep(0.004)
                    continue

                # if (features['pupil_position'] != None and
                #     features['cr_position'] != None):

                #     timestamp = features.get('timestamp', 0)

                #     pupil_position = features['pupil_position']
                #     cr_position = features['cr_position']

                #     pupil_radius = 0.0
                #     # get pupil radius in mm
                #     if 'pupil_radius' in features and features['pupil_radius'] \
                #         != None and self.calibrator is not None:

                #         if self.calibrator.pixels_per_mm is not None:
                #             pupil_radius = features['pupil_radius'] \
                #                 / self.calibrator.pixels_per_mm
                #         else:
                #             pupil_radius = -1 * features['pupil_radius']

                #     if self.calibrator is not None:

                #         if not self.pupil_only:

                #             (gaze_elevation, gaze_azimuth,
                #              calibration_status) = \
                #                 self.calibrator.transform(pupil_position,
                #                     cr_position)
                #         else:

                #             (gaze_elevation, gaze_azimuth,
                #              calibration_status) = \
                #                 self.calibrator.transform(pupil_position, None)

                #         if self.mw_conduit != None:
                #             #print self.leds.soft_status
                #             #print "Side:", self.calibrator.side_led, self.leds.soft_status(self.calibrator.side_led)
                #             #print "Top :", self.calibrator.top_led, self.leds.soft_status(self.calibrator.top_led)
                #             # TODO: add calibration status
                #             self.mw_conduit.send_data(GAZE_INFO,
                #                 (float(gaze_azimuth),
                #                  float(gaze_elevation),
                #                  float(pupil_radius),
                #                  float(timestamp),
                #                  float(calibration_status),
                #                  float(pupil_position[1]),
                #                  float(pupil_position[0]),
                #                  float(cr_position[1]),
                #                  float(cr_position[0]),
                #                  float(self.leds.soft_status(self.calibrator.top_led)),
                #                  float(self.leds.soft_status(self.calibrator.side_led))
                #                  ))
                #             dt = time.time() - self.last_conduit_time
                #             if dt:
                #                 self.conduit_fps = 0.01 / dt + 0.99 * self.conduit_fps
                #             self.last_conduit_time = time.time()
                #     else:

                #         if self.mw_conduit != None:
                #             pass


                    # FIXME I cannot do this here as it will fubar the serial communication with the ESP
                    #if frame_number % info_interval == 0:
                    #    if mw_conduit != None:
                    #        self.dump_info_to_conduit()
            except Exception:

                print self.camera_device
                formatted = formatted_exception()
                print formatted[0], ': '
                for f in formatted[2]:
                    print f

            self.ui_queue_put(features)
                
                

        self.camera_locked = 0

        logging.info('Stopped continuous acquiring')
        return

    def get_camera_attribute(self, a):
        if self.camera_device != None and getattr(self.camera_device, 'camera',
                None) is not None and self.camera_device.camera != None:
            return self.camera_device.camera.getUint32Attribute(a)
        else:
            return 0

    def set_camera_attribute(self, a, value):
        if getattr(self.camera_device, 'camera', None) is None:
            return

        self.camera_device.camera.setAttribute(a, int(value))
        # Why is this being set twice??
        self.camera_device.camera.setAttribute(a, int(value))

    @property
    def exposure(self):
        return self.get_camera_attribute('ExposureValue')

    @exposure.setter
    def exposure(self, value):
        self.set_camera_attribute('ExposureValue', int(value))

    @property
    def binning(self):
        return self.get_camera_attribute('BinningX')

    @binning.setter
    def binning(self, value):
        self.set_camera_attribute('BinningX', int(value))
        self.set_camera_attribute('BinningY', int(value))

        time.sleep(0.1)

    @property
    def gain(self):
        return self.get_camera_attribute('GainValue')

    @gain.setter
    def gain(self, value):
        self.gain_factor = value
        self.set_camera_attribute('GainValue', int(value))

    @property
    def roi_width(self):
        return self.get_camera_attribute('Width')

    @roi_width.setter
    def roi_width(self, value):
        self.set_camera_attribute('Width', int(value))

    @property
    def roi_height(self):
        return self.get_camera_attribute('Height')

    @roi_height.setter
    def roi_height(self, value):
        self.set_camera_attribute('Height', int(value))

    @property
    def roi_offset_x(self):
        return self.get_camera_attribute('RegionX')

    @roi_offset_x.setter
    def roi_offset_x(self, value):
        self.set_camera_attribute('RegionX', int(value))

    @property
    def roi_offset_y(self):
        return self.get_camera_attribute('RegionY')

    @roi_offset_y.setter
    def roi_offset_y(self, value):
        self.set_camera_attribute('RegionY', int(value))


    def go_r(self):
        self.stages.move_absolute(self.stages.r_axis, self.r_set)
        return

    def go_rel_all(self):
        try:
            x_set = float(self.x_set)
            y_set = float(self.y_set)
            r_set = float(self.r_set)

            self.stages.move_composite_relative((self.stages.x_axis,
                    self.stages.y_axis, self.stages.r_axis),
                    (x_set, y_set, r_set))
        except:
            pass

        return

    def go_rel_r(self):
        try:
            r_set = float(self.r_set)

            self.stages.move_relative(self.stages.r_axis, r_set)
        except:
            pass

        return

    def go_rel_x(self):
        try:
            x_set = float(self.x_set)

            self.stages.move_relative(self.stages.x_axis, x_set)
        except:
            pass
        return

    def go_rel_y(self):
        try:
            y_set = float(self.y_set)

            self.stages.move_relative(self.stages.y_axis, y_set)
        except:
            pass

        return

    def go_x(self):
        try:
            x_set = float(self.x_set)

            self.stages.move_absolute(self.stages.x_axis, x_set)
        except:
            pass
        return

    def go_y(self):
        try:
            y_set = float(self.y_set)

            self.stages.move_absolute(self.stages.y_axis, y_set)
        except:
            pass
        return

    def home_all(self):
        self.stages.home(self.stages.x_axis)
        self.stages.home(self.stages.y_axis)
        self.stages.home(self.stages.r_axis)
        return

    def home_r(self):
        self.stages.home(self.stages.r_axis)
        return

    def home_x(self):
        self.stages.home(self.stages.x_axis)
        return

    def home_y(self):
        self.stages.home(self.stages.y_axis)
        return

    def focus_plus(self):
        self.zoom_and_focus.focus_relative(self.focus_step)

    def focus_minus(self):
        self.zoom_and_focus.focus_relative(-float(self.focus_step))

    def zoom_plus(self):
        self.zoom_and_focus.zoom_relative(self.zoom_step)

    def zoom_minus(self):
        self.zoom_and_focus.zoom_relative(-float(self.zoom_step))


    def led_set_current(self, *args):
        return self.leds.set_current(*args)

    def led_soft_current(self, *args):
        return self.leds.soft_current(*args)

    def led_soft_status(self, *args):
        return self.leds.soft_status(*args)

    def led_set_status(self, *args):
        return self.leds.set_status(*args)

    # def off_ch1(self):
    #     self.leds.turn_off(self.leds.channel1)
    #     return
    #
    # def off_ch2(self):
    #     self.leds.turn_off(self.leds.channel2)
    #     return
    #
    # def off_ch3(self):
    #     self.leds.turn_off(self.leds.channel3)
    #     return
    #
    # def off_ch4(self):
    #     self.leds.turn_off(self.leds.channel4)
    #     return
    #
    # def on_ch1(self):
    #     self.leds.turn_on(self.leds.channel1, float(self.IsetCh1))
    #     return
    #
    #
    # def on_ch2(self):
    #     self.leds.turn_on(self.leds.channel2, float(self.IsetCh2))
    #     return
    #
    #
    # def on_ch3(self):
    #     self.leds.turn_on(self.leds.channel3, float(self.IsetCh3))
    #     return
    #
    #
    # def on_ch4(self):
    #     self.leds.turn_on(self.leds.channel4, float(self.IsetCh4))
    #     return



    def read_pos(self):
        self.x_current = self.stages.current_position(self.stages.x_axis)
        self.y_current = self.stages.current_position(self.stages.y_axis)
        self.r_current = self.stages.current_position(self.stages.r_axis)

        self.focus_current = self.zoom_and_focus.current_focus()
        self.zoom_current = self.zoom_and_focus.current_zoom()
#        if(self.calibrator.calibrated):
        self.d_current = self.calibrator.d
        self.pixels_per_mm_current = self.calibrator.pixels_per_mm
        if self.calibrator.Rp is not None and self.calibrator.pixels_per_mm \
            is not None:
            self.rp_current = self.calibrator.Rp / self.calibrator.pixels_per_mm
        self.pupil_cr_diff = self.calibrator.pupil_cr_diff

        return

    def rot_about_abs(self):
        self.stages.composite_rotation_absolute(self.d_cntr_set,
                self.r_cntr_set)
        return

    def rot_about_rel_(self):
        self.stages.composite_rotation_relative(self.d_cntr_set,
                self.r_cntr_set)
        return

    def go_all(self):
        self.stages.move_composite_absolute((self.stages.x_axis,
                self.stages.y_axis, self.stages.r_axis), (self.x_set,
                self.y_set, self.r_set))

    def up(self):
        try:
            y_set = float(self.y_set)
        except:
            return

        self.stages.move_relative(self.stages.y_axis, -y_set)

    def down(self):
        try:
            y_set = float(self.y_set)
        except:
            return

        self.stages.move_relative(self.stages.y_axis, y_set)

    def left(self):
        try:
            x_set = float(self.x_set)
        except:
            return

        self.stages.move_relative(self.stages.x_axis, x_set)

    def right(self):
        try:
            x_set = float(self.x_set)
        except:
            return

        self.stages.move_relative(self.stages.x_axis, -x_set)

    def clockwise(self):
        try:
            r_set = float(self.r_set)
        except:
            return

        self.stages.move_relative(self.stages.r_axis, r_set)

    def counterclockwise(self):
        try:
            r_set = float(self.r_set)
        except:
            return

        self.stages.move_relative(self.stages.r_axis, -r_set)


    def auto_validate(self):
        vs = linspace(-15., 15., 3)
        hs = vs

        for v in vs:
            for h in hs:
                self.camera_device.move_eye(array([v, h, 0.0]))
                self.report_gaze(h, v)
