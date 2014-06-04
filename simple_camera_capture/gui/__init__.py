#!/usr/bin/env python
# -*- coding: utf-8 -*-

from tracker_view import *
import glumpy
import glumpy.atb as atb
from ctypes import *
import os
import sys
import re
from simple_camera_capture.settings import global_settings
import numpy as np
import time

import OpenGL.GL as gl
import OpenGL.GLUT as glut

import logging


try:
    from collections import OrderedDict
except:
    from ordereddict import OrderedDict


# Utility functions for use with atb

def binding_getter(o, key):

    def get_wrapper():
        if hasattr(o, 'get_property'):
            val = o.get_property(key)
        else:
            val = getattr(o, key)


        if val is None:
            val = 0
        if type(val) == np.float64:
            val = float(val)
        if type(val) == np.int32 or type(val) == np.int64:
            val = int(val)
        return val

    return get_wrapper


def binding_setter(o, key):

    def ff_wrapper(val):
        o.set_property(key, val)
        #setattr(o, key, val)
        o.update_parameters(key)

    def regular_wrapper(val):
        #setattr(o, key, val)
        print 'regular wrapper setter'
        o.set_property(key, val)

    if hasattr(o, 'update_parameters') and callable(getattr(o,
            'update_parameters')):
        return ff_wrapper
    else:
        return regular_wrapper


# Do a tiny bit of trickiness to make glumpy.atb less tiresome

def new_add_var(self, name=None, value=None, **kwargs):
    t = kwargs.pop('target', None)
    p = kwargs.pop('attr', None)

    if t is not None and p is not None:
        kwargs['getter'] = binding_getter(t, p)
        kwargs['setter'] = binding_setter(t, p)
    return self.old_add_var(name, value, **kwargs)


atb.Bar.old_add_var = atb.Bar.add_var
atb.Bar.add_var = new_add_var


class CaptureGUI:

    def __init__(self, c):

        self.controller = c
        self.tracker_view = TrackerView()

        self.gui_frame_rate = 0.0

        self.n_frames = 0
        self.frame_count = 0
        self.frame_rate_accum = 0.0
        self.frame_rates = []
        self.start_time = None
        self.last_time = 0
        self.last_update_time = time.time()
        self.update_interval = 1 / 10000.

        atb.init()
        self.window = glumpy.Window(900, 600)

        # ---------------------------------------------------------------------
        #   STAGE CONTROLS
        # ---------------------------------------------------------------------

        self.stages_bar = atb.Bar(
            name='stages',
            label='Stage Controls',
            iconified='true',
            help='Controls for adjusting stages',
            position=(10, 10),
            size=(200, 300),
            )

        self.stages_bar.add_var('X/x_set', label='set value', target=c,
                                attr='x_set')
        self.stages_bar.add_button('go_rel_x', lambda: c.go_rel_x(), group='X',
                                   label='move relative')
        self.stages_bar.add_button('go_abs_x', lambda: c.go_x(), group='X',
                                   label='move absolute')

        self.stages_bar.add_var('Y/y_set', label='set value', target=c,
                                attr='y_set')
        self.stages_bar.add_button('go_rel_y', lambda: c.go_rel_y(), group='Y',
                                   label='move relative')
        self.stages_bar.add_button('go_abs_y', lambda: c.go_y(), group='Y',
                                   label='move absolute')

        self.stages_bar.add_var('R/r_set', label='set value', target=c,
                                attr='r_set')
        self.stages_bar.add_button('go_rel_r', lambda: c.go_rel_r(), group='R',
                                   label='move relative')
        self.stages_bar.add_button('go_abs_r', lambda: c.go_r(), group='R',
                                   label='move absolute')

        self.stages_bar.add_button('up', lambda: c.up(), group='Jog',
                                   label='up')
        self.stages_bar.add_button('down', lambda: c.down(), group='Jog',
                                   label='down')
        self.stages_bar.add_button('left', lambda: c.left(), group='Jog',
                                   label='left')

        self.stages_bar.add_button('right', lambda: c.right(), group='Jog',
                                   label='right')

        # ---------------------------------------------------------------------
        #   FOCUS AND ZOOM CONTROLS
        # ---------------------------------------------------------------------

        self.focus_zoom_bar = atb.Bar(
            name='focus_and_zoom',
            label='Focus/Zoom Controls',
            iconified='true',
            help='Controls for adjusting power focus and zoom',
            position=(10, 10),
            size=(200, 300),
            )

        self.focus_zoom_bar.add_var('Focus/focus_step', label='focus step',
                                    target=c, attr='focus_step')
        self.focus_zoom_bar.add_button('focus_plus', lambda: c.focus_plus(),
                                       group='Focus', label='focus plus')
        self.focus_zoom_bar.add_button('focus_minus', lambda: c.focus_minus(),
                                       group='Focus', label='focus minus')

        self.focus_zoom_bar.add_var('Zoom/zoom_step', label='zoom step',
                                    target=c, attr='zoom_step')
        self.focus_zoom_bar.add_button('zoom_plus', lambda: c.zoom_plus(),
                                       group='Zoom', label='zoom plus')
        self.focus_zoom_bar.add_button('zoom_minus', lambda: c.zoom_minus(),
                                       group='Zoom', label='zoom minus')

        # ---------------------------------------------------------------------
        #   LED CONTROLS
        # ---------------------------------------------------------------------

        self.led_bar = atb.Bar(
            name='leds',
            label='LED Controls',
            iconified='true',
            help='Controls for adjusting illumination',
            position=(20, 20),
            size=(200, 180),
            )


        self.led_bar.add_var(
            'Side/Ch1_mA',
            #target=c,
            #attr='IsetCh1',
            label='I Ch1 (mA)',
            vtype=atb.TW_TYPE_UINT32,
            setter=lambda x: c.led_set_current(1, x),
            getter=lambda: c.led_soft_current(1),
            min=0,
            max=1000,
            )

        self.led_bar.add_var('Side/Ch1_status', label='Ch1 status',
                             vtype=atb.TW_TYPE_BOOL8,
                             getter=lambda: c.led_soft_status(1),
                             setter=lambda x: c.led_set_status(1, x))

        self.led_bar.add_var(
            'Top/Ch2_mA',
            #target=c,
            #attr='IsetCh2',
            label='I Ch2 (mA)',
            vtype=atb.TW_TYPE_UINT32,
            setter=lambda x: c.led_set_current(2, x),
            getter=lambda: c.led_soft_current(2),
            min=0,
            max=1000,
            )
        self.led_bar.add_var('Top/Ch2_status', vtype=atb.TW_TYPE_BOOL8,
                             getter=lambda: c.led_soft_status(2),
                             setter=lambda x: c.led_set_status(2, x))


        # --------------------------------------------------------------------
        #   GUI
        # --------------------------------------------------------------------

        self.gui_bar = atb.Bar(
            name='GUI',
            label='GUI',
            iconified='true',
            help='GUI Status',
            position=(60, 60),
            size=(200, 180),
            )


        self.gui_bar.add_var(
            'gui_framerate',
            label='gui frame rate',
            vtype=atb.TW_TYPE_FLOAT,
            min=1,
            max=200,
            step=0.1,
            readonly=True,
            getter=lambda: float(self.gui_frame_rate)
        )        


        # --------------------------------------------------------------------
        #   CAMERA
        # --------------------------------------------------------------------

        self.cam_bar = atb.Bar(
            name='Camera',
            label='Camera',
            iconified='true',
            help='Camera acquisition parameters',
            position=(60, 60),
            size=(200, 180),
            )


        self.cam_bar.add_var(
            'framerate',
            label='frame rate',
            vtype=atb.TW_TYPE_FLOAT,
            min=1,
            max=200,
            step=0.1,
            readonly=True,
            getter=lambda: float(c.get_frame_rate())
        )        

        self.cam_bar.add_var(
            'Binning/binningx',
            label='binning X',
            vtype=atb.TW_TYPE_UINT32,
            min=1,
            max=16,
            step=1,
            getter=lambda: c.get_camera_attribute('BinningX'),
            setter=lambda x: c.set_camera_attribute('BinningX', int(x)),
            )

        self.cam_bar.add_var(
            'Binning/binningy',
            label='binning Y',
            vtype=atb.TW_TYPE_UINT32,
            min=1,
            max=16,
            step=1,
            getter=lambda: c.get_camera_attribute('BinningY'),
            setter=lambda x: c.set_camera_attribute('BinningY', int(x)),
            )



        # ExposureMode = atb.enum('ExposureMode', {'manual': 0,
        #                             'auto_once': 1, 'auto': 2})
        # self.cam_bar.add_var('Exposure/mode', label='mode',
        #                        vtype=ExposureMode,
        #                        getter=lambda: c.get_camera_attribute('ExposureMode'),
        #                        setter=lambda x: c.set_camera_attribute('ExposureMode', int(x)))


        # self.cam_bar.add_var(
        #     'Exposure/value',
        #     label='time (ms)',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=1,
        #     max=1000,
        #     step=1,
        #     getter=lambda: c.get_camera_attribute('ExposureValue'),
        #     setter=lambda x: c.set_camera_attribute('ExposureValue', int(x)),
        #     )

        # self.cam_bar.add_var(
        #     'gain',
        #     label='gain',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=1,
        #     max=16,
        #     step=1,
        #     target=c,
        #     attr='gain',
        #     )

        # self.cam_bar.add_var(
        #     'exposure',
        #     label='exposure',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=5000,
        #     max=30000,
        #     step=1000,
        #     target=c,
        #     attr='exposure',
        #     )

        # self.cam_bar.add_var(
        #     'ROI/roi_width',
        #     label='width',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=1,
        #     max=800,
        #     step=1,
        #     target=c,
        #     attr='roi_width',
        #     )

        # self.cam_bar.add_var(
        #     'ROI/roi_height',
        #     label='height',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=1,
        #     max=800,
        #     step=1,
        #     target=c,
        #     attr='roi_height',
        #     )

        # self.cam_bar.add_var(
        #     'ROI/roi_offset_x',
        #     label='offset x',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=0,
        #     max=800,
        #     step=1,
        #     target=c,
        #     attr='roi_offset_x',
        #     )

        # self.cam_bar.add_var(
        #     'ROI/roi_offset_y',
        #     label='offset y',
        #     vtype=atb.TW_TYPE_UINT32,
        #     min=0,
        #     max=800,
        #     step=1,
        #     target=c,
        #     attr='roi_offset_y',
        #     )

        # Event Handlers
        def on_init():
            self.tracker_view.prepare_opengl()

        def on_draw():
            self.tracker_view.draw((self.window.width, self.window.height))

        def on_idle(dt):
            self.update_tracker_view()
            # time.sleep(0.05)

        def on_key_press(symbol, modifiers):
            if symbol == glumpy.key.ESCAPE:
                c.stop_continuous_acquisition()
                print "Controller has %i refs" % sys.getrefcount(c)
                c.release()
                self.controller = None
                print "Controller has %i refs" % sys.getrefcount(c)
                c.shutdown()
                #print "Shutting down controller..."
                #print "Shut down controller", c.shutdown()
                #c.continuously_acquiring = False
                #c.acq_thread.join()
                sys.exit()

        self.window.push_handlers(atb.glumpy.Handlers(self.window))
        self.window.push_handlers(on_init, on_draw, on_key_press, on_idle)
        self.window.draw()

    def __del__(self):
        print "GUI __del__ called"
        self.controller.stop_continuous_acquisition()
        self.controller.release()
        self.controller.shutdown()
        self.controller = None

    def mainloop(self):
        self.window.mainloop()


    def update_tracker_view(self):
        if self.controller is None:
            return

        now = time.time()

        try:
            features = self.controller.ui_queue_get()
        except Exception as e:
            print e
            print("Broken queue, quitting...")
            exit(0)

        if features is None:
            return

        self.gui_frame_rate = 1.0 / (now - self.last_update_time)

        self.last_update_time = now


        self.tracker_view.im_array = features['im_array']

        self.window.draw()

