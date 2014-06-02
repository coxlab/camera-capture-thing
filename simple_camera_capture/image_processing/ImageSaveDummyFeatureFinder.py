from FeatureFinder import FeatureFinder
import cPickle as pkl
import os.path
import os
import uuid
import time
import numpy as np


class ImageSaveDummyFeatureFinder(FeatureFinder):

    def __init__(self, real_ff, path):
        self.real_ff = real_ff
        self.session_key = time.strftime('%Y-%m-%d-%H%M-%S',time.localtime(time.time())) + '_' + str(uuid.uuid1())
        self.n_frames = 0
        self.frames_per_dir = 1000

        self.base_path = os.path.expanduser(path)
        self.base_path += '/' + self.session_key

        os.makedirs(self.base_path)

        self.current_path = None

        self.im_array = None

    def analyze_image(self, image, guess=None, **kwargs):
        if guess is not None and 'timestamp' in guess:
            self.save_image(image, guess['timestamp'])
        else:
            print('Cannot save to disk without timestamp set')

        self.im_array = image

        if self.real_ff is None:
            return
        else:
            return self.real_ff.analyze_image(image, guess, **kwargs)

    def get_result(self):
        if self.real_ff is None:
            return {'im_array': self.im_array,'im_shape': self.im_array.shape}
        else:
            return self.real_ff.get_result()

    def stop_threads(self):
        if hasattr(self.real_ff, 'stop_threads'):
            self.real_ff.stop_threads()

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


