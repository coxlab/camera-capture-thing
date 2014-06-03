import prosilica_cpp
from prosilica_cpp import *
import time


if __name__ == '__main__':

    PvUnInitialize()
    PvInitialize()
    time.sleep(1)

    print("%d cameras available" % PvCameraCount())

    camlist = getCameraList()
    print("Cam list:")
    print camlist

    cam = ProsilicaCamera(camlist[0])

    cam.startContinuousCapture()

    last_time = time.time()

    for i in range(0, 100):
        frame = cam.getAndLockCurrentFrame()
        cam.releaseCurrentFrame()
        t = time.time()
        print 'delta: %f' % (t - last_time)
        last_time = t

    cam.endCapture()

    # PvUnInitialize()