from flask import Flask, render_template, redirect, url_for
from flask_sockets import Sockets
import numpy as np
import time
import sys
import logging
import Pyro4
from webui import WebUI, UIPanel

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def build_app(port):

    # controller = {}
    controller = connect_camera_controller(port)

    ui = WebUI('ws', label="Camera Thing")

    camera_controls = UIPanel('camera', 'Camera Controls')
    camera_controls.add_variable('binningx', label='binning (x)',
                                 vtype=int, default=4, min=1, max=8, step=1,
                                 target=controller)

    camera_controls.add_variable('binningy', label='binning (y)',
                                 vtype=int, default=4, min=1, max=8, step=1,
                                 target=controller)

    ui.add_panel(camera_controls)

    def get_image():
        features = controller.ui_queue_get()
        return features['im_array']

    ui.add_image_source('camera_view', 'Camera View', getter=get_image)

    app = ui.build_flask_app()

    return app



def connect_camera_controller(port):
    n_retries = 10
    retry_wait = 0.5

    ns = None
    for i in range(0, n_retries):
        try:
            ns = Pyro4.locateNS(port=port)
            break
        except Pyro4.errors.NamingError:
            # retry
            logging.info('Looking for name server...')
            time.sleep(retry_wait)

    if ns is None:
        logging.error('Unable to connect to name server...')
        exit(0)

    pyro_uri = None
    for i in range(0, n_retries):
        try:
            pyro_uri = ns.lookup('org.coxlab.camera_capture.controller')
            break
        except Pyro4.errors.NamingError:
            # retry
            logging.info('Looking for capture controller...')
            time.sleep(retry_wait)

    if pyro_uri is None:
        logging.error('Unable to find camera controller process')
        exit(0)

    controller = Pyro4.Proxy(pyro_uri)

    return controller



if __name__ == '__main__':
    build_app(port=59604).run(port=8000, debug=True)
