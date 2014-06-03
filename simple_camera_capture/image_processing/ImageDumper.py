from FeatureFinder import FeatureFinder
import cPickle as pkl
import os.path
import os
import uuid
import time
import numpy as np


class ImageDumper:

    def __init__(self, path):
        self.session_key = time.strftime('%Y-%m-%d-%H%M-%S',time.localtime(time.time())) + '_' + str(uuid.uuid1())
        self.n_frames = 0
        self.frames_per_dir = 1000

        self.base_path = os.path.expanduser(path)
        self.base_path += '/' + self.session_key

        os.makedirs(self.base_path)

        self.current_path = None

        self.im_array = None


    def save_image(self, image, timestamp):

        if (self.n_frames % self.frames_per_dir == 0 or
            self.current_path is None):

            # make a new directory
            self.current_path = (self.base_path + '/' +
                                '%.10d' % (self.n_frames /
                                           self.frames_per_dir))
            os.mkdir(self.current_path)

        fname = '%s/%i.pkl' % (self.current_path,
                               int(timestamp * 1000.))

        with open(fname, 'w') as f:
            self.n_frames += 1
            pkl.dump(image.astype('>u1'), f)


