#
#  ProsilicaCameraDevice.py
#  CaptureStageDriver
#
#  Created by David Cox on 7/29/08.
#  Copyright (c) 2008 __MyCompanyName__. All rights reserved.
#

#
#  SimulatedCameraDevice.py
#  CaptureStageDriver
#
#  Created by David Cox on 5/26/08.
#  Copyright (c) 2008 __MyCompanyName__. All rights reserved.
#

import prosilica as p
from numpy import *
#import matplotlib.pylab as pylab

import os
import time

import PIL.Image

import threading

import time



class ProsilicaCameraDevice:

    def __init__(self, **kwargs):

        self.frame_number = 0


        # low level camera interface
        self.camera = None

        self.image_center = array([0, 0])

        self.nframes_done = 0

        self.acquire_continuously = 0
        self.acquisition_thread = None

        self.last_timestamp = None

        #os.system('/sbin/route -n add 255.255.255.255 169.254.42.97')
        p.PvUnInitialize()
        p.PvInitialize()

        print "Finding valid cameras..."
        time.sleep(1)
        camera_list = p.getCameraList()

        if(len(camera_list) <= 0):
            raise Exception("Couldn't find a valid camera")

        try:
            print "Trying..."
            self.camera = p.ProsilicaCamera(camera_list[0])
            print "Did it"
        except:
            print "No good"
            raise Exception("Couldn't instantiate camera")


        self.camera.setAttribute("BinningX", 1)
        self.camera.setAttribute("BinningY", 1)
        try:
            self.timestampFrequency = self.camera.getUint32Attribute("TimeStampFrequency")
            print "Found TimestampFrequency of: %f" % self.timestampFrequency
        except:
            self.timestampFrequency = 1
            print "attribute: TimestampFrequency not found for camera, defaulting to 1"
        self.camera.startContinuousCapture()

    def shutdown(self):
        print "Deleting camera (in python)"
        if(self.camera != None):
            print "ending camera capture in ProsilicaCameraDevice"
            self.camera.endCapture()

    def __del__(self):
        print "Deleting camera (in python)"
        if(self.camera != None):
            self.camera.endCapture()


    def acquire_image(self):

        if(self.camera == None):
            raise Exception, "No valid low-level prosilica camera interface is in place"

        im_array = None

        found_new_frame = False

        frame = self.camera.getAndLockCurrentFrame()

        timestamp = frame.timestamp # / float(self.timestampFrequency)
        im_array = (asarray(frame)).copy()

        self.camera.releaseCurrentFrame()


        if timestamp != self.last_timestamp:
            self.frame_number += 1        
            self.last_timestamp = timestamp


        return {'im_array': im_array, 'timestamp': timestamp, 'frame_number': self.frame_number }



