from flask import Flask, render_template, redirect, url_for
from flask.ext import restful
from flask.ext.restful import reqparse
from collections import OrderedDict
from flask_sockets import Sockets
from functools import partial
import uuid
import logging
import numpy as np

#  constants
NUMERIC = 'numeric'
ENUM = 'enum'
SEPARATOR = 'separator'
BUTTON = 'button'


class Variable:

    def __init__(self, name):
        self.name = name
        self.vtype = None

    def value(self):
        if hasattr(self, 'getter') and self.getter is not None:
            return self.getter()
        else:
            return None

    def set(self, val):

        if self.vtype is not None and val is not None:
            val = self.vtype(val)

        if hasattr(self, 'setter') and self.setter is not None:
            self.setter(val)
        else:
            # raise
            return


class NumericVariable (Variable):

    def __init__(self, name, label=None,
                        min=None, max=None, step=None, getter=None, setter=None,
                        target=None, prop=None, default=None,
                        readonly=False, update_interval=None, vtype=None):

        Variable.__init__(self, name)

        if label is None:
            label = name

        self.label = label

        self.default = default
        self.min = min
        self.max = max
        self.step = step

        if prop is None:
            prop = name

        if getter is None:
            if target is None:
                raise ValueError('either target or getter must be set')

            self.getter = lambda: target.get_property(prop)
            # self.getter = lambda: getattr(target, prop)
        else:
            self.getter = getter

        if setter is None:
            if target is None:
                raise ValueError('either target or setter must be set')
            def setter(x):
                logging.info('SETTER')
                target.set_property(prop, x)
                logging.info('it is set')
                # setattr(target, prop, x)
            self.setter = setter
        else:
            self.setter = setter
        self.readonly = readonly
        self.update_interval = update_interval
        self.eltype = NUMERIC

        if vtype is None:
            vtype = float
        self.vtype = vtype



class Separator:

    def __init__(self):
        self.name = uuid.uuid1()
        self.eltype = SEPARATOR


class UIPanel:

    def __init__(self, name, label=None):
        self.name = name
        if label is None:
            self.label = name
        else:
            self.label = label

        self.elements = OrderedDict()


    def add_element(self, el):
        self.elements[el.name] = el

    def add_variable(self, name, **kwargs):
        v = NumericVariable(name, **kwargs)
        self.add_element(v)

    def add_separator(self):
        self.add_element(Separator())


class ImageSource:

    def __init__(self, name, label=None, getter=None):
        self.name = name

        if label is None:
            label = name

        self.label = label
        self.getter = getter

    def get_image(self):
        return self.getter()



# add UI elements
# auto-build REST api to match -- get+set @ /<panel>/<var>
# add named image sources 
# expose image streams on websockets @ /imagesrc/<name>
# should image source push or pull?

class WebUI:

    def __init__(self, name, label=None):

        restful.Resource.__init__(self)

        self.app = None

        self.image_sources = OrderedDict()
        self.panels = OrderedDict()

        self.name = name

        if label is None:
            self.label = name
        else:
            self.label = label

    def add_panel(self, panel):
        self.panels[panel.name] = panel

    def add_image_source(self, name, label=None, getter=None):
        
        if label is None:
            label = name

        self.image_sources[name] = ImageSource(name=name, label=label, getter=getter)

    # ReST API
    def get(self, panel_name, variable_name):
        panel = self.panels[panel_name]
        variable = panel.elements[variable_name]

        return variable.value()

    def put(self, panel_name, variable_name, value):
        panel = self.panels[panel_name]
        variable = panel.elements[variable_name]

        logging.info('variable put: %s' % variable_name)

        # to do: validate
        variable.set(value)


    def build_flask_app(self):

        # create flask app
        if self.app is None:
            self.app = Flask(self.name)

        # create a rest api for the parameters
        self.rest_api = restful.Api(self.app)

        webui = self

        class RestResource (restful.Resource):
            def __init__(self):
                self.parser = reqparse.RequestParser()
                self.parser.add_argument('value', help='New value for parameter')

            def get(self, panel_name, variable_name):
                return webui.get(panel_name, variable_name)

            def put(self, panel_name, variable_name):
                args = self.parser.parse_args()

                logging.info('rest put')

                return webui.put(panel_name, variable_name, args['value'])


        self.rest_api.add_resource(RestResource, '/%s' % self.name, '/%s/<string:panel_name>/<string:variable_name>' % self.name, endpoint='rest-' + self.name)

        # create websockets for the image sources
        self.sockets = Sockets(self.app)

        for i, name in enumerate(self.image_sources):

            img_src = self.image_sources[name]

            def image_socket(ws): 
                while True: 

                    # this will block until the image arrives
                    im_array = img_src.get_image()

                    arr = im_array.astype(np.uint8).transpose()

                    rgba_tmp = np.array((arr, arr, arr, 255*np.ones_like(arr)))
                    rgba = np.reshape(rgba_tmp, (np.prod(rgba_tmp.shape),), (2, 1, 0) )
         
                    ws.send(rgba.tostring(), binary=True)

            ws_address = '/%s/image_source/%s' % (self.name, name)
            self.sockets.add_url_rule(ws_address, name, image_socket)

            logging.info('Image WebSocket broadcasting at %s' % ws_address)


        def index():
            return render_template('index.html', ui=self)

        self.app.add_url_rule('/', 'index', index)

        def static_route(base, path):
            return redirect(url_for('static', filename='%s/%s'%(base, path)))

        self.app.add_url_rule('/kendo/<path:path>', 'kendo', partial(static_route, base='kendo'))
        self.app.add_url_rule('/js/<path:path>', 'js', partial(static_route, base='js'))
        self.app.add_url_rule('/css/<path:path>', 'css', partial(static_route, base='css'))

        return self.app


