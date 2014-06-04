#
#  SimulatedCameraDevice.py
#  CaptureStageDriver
#
#  Created by David Cox on 5/26/08.
#  Copyright (c) 2008 __MyCompanyName__. All rights reserved.
#


from numpy import *
import os
import PIL.Image as Image
import time
import cPickle as pkl
import sys

import threading
from Queue import Queue



class FakeCameraDevice:

    def __init__(self, _filename = None):

        self.filename = None
        self.im_array = None

        self.filename = _filename

        self.frame_number = 0

        if(self.filename != None):
            ext = os.path.splitext(self.filename)[-1]
            print ext
            if ext == '.pkl':
                im = pkl.load(open(self.filename))
            else:
                im = Image.open(self.filename)

            self.im_array = array(im).astype(double)

            if(self.im_array.ndim == 3):
                self.im_array = mean(self.im_array, 2)
        else:
            self.im_array = None


    def acquire_image(self):
        self.frame_number += 1
        noise = 0.1 * random.rand(self.im_array.shape[0], self.im_array.shape[1])
        im_array = self.im_array + noise

        # time.sleep(1.0 / 100.)

        sys.stdout.write('\r [ fake camera | %d ] ' % self.frame_number)

        return {'im_array': im_array, 'timestamp': time.time(), 'frame_number': self.frame_number }



    def shutdown(self):
        return
