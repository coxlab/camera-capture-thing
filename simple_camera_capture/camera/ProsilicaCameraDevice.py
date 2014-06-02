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


def acquire_continuously(camera, ff):
    while(1):
        frame = camera.getAndLockCurrentFrame()
        timestamp = frame.timestamp / float(self.timestampFrequency)

        if camera.last_timestamp != timestamp:
            im_array = (asarray(frame)).copy()
            camera.frame_number += 1

            ff.analyzeImage(im_array)
            camera.last_timestamp = timestamp
        
        camera.releaseCurrentFrame()


class ProsilicaCameraDevice:

    def __init__(self, _feature_finder, **kwargs):

        self.frame_number = 0

        self.camera = None

        self.im_array = None
        self.image_center = array([0, 0])
        self.pupil_position = array([0., 0.])
        self.cr_position = array([0., 0.])

        self.nframes_done = 0

        self.acquire_continuously = 0
        self.acquisition_thread = None

        self.last_timestamp = None

        self.feature_finder = _feature_finder
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

        if(self.acquire_continuously):
            self.acquisition_thread = threading.Thread(target=acquireContinuously, args=[self.camera, self.feature_finder])
            self.acquisition_thread.start()

    def shutdown(self):
        print "Deleting camera (in python)"
        if(self.acquire_continuously):
            print "Terminating acquisition thread in ProsilicaCameraDevice"
            self.acquisition_thread.terminate()
        if(self.camera != None):
            print "ending camera capture in ProsilicaCameraDevice"
            self.camera.endCapture()

    def __del__(self):
        print "Deleting camera (in python)"
        if(self.acquire_continuously):
            self.acquisition_thread.terminate()
        if(self.camera != None):
            self.camera.endCapture()


    def acquire_image(self):

        if(self.acquire_continuously):
            return

        if(self.camera == None):
            raise Exception, "No valid prosilica camera is in place"


        found_new_frame = False

        while not found_new_frame:

            frame = self.camera.getAndLockCurrentFrame()
            # We could convert the timestamp from clock cycles to seconds by dividing by the available timestampFrequency
            # However, this could result in rounding errors. It might be easier to account for this in analysis scripts
            # or pass along timestampFrequency
            timestamp = frame.timestamp # / float(self.timestampFrequency)
            print timestamp

            if timestamp != self.last_timestamp:


                self.im_array = (asarray(frame)).copy()

                
                #timestamp = frame.timestamp
                #print "Timestamp: ", timestamp
                self.frame_number += 1

                # start the analysis process

                #self.feature_finder.analyze_image(self.im_array.copy(), None)

                # push the image to the feature analyzer
                self.feature_finder.analyze_image(self.im_array.astype(float32), { "frame_number" : self.frame_number, "timestamp" : timestamp})
            
                self.last_timestamp = timestamp

                found_new_frame = True
            else:

                print 'skipping repeat frame'

        self.camera.releaseCurrentFrame()

        return



    def get_processed_image(self, guess = None):

        time.sleep(0.016)

        features = self.feature_finder.get_result()

        if(features == None):
            return features

        self.nframes_done += 1
        #features["frame_number"] = self.frame_number
        return features


