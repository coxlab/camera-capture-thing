from flask import Flask 
from flask_sockets import Sockets

app = Flask(__name__) 
sockets = Sockets(app)


pyro_port = int(sys.argv[1])

logger = logging.getLogger()
logger.setLevel(logging.INFO)

controller = connect_camera_controller(pyro_port)

@sockets.route('/image_src') 
def image_socket(ws): 
    while True: 
        message = ws.receive() 
        ws.send(message)

@app.route('/') 
def hello(): 
    return 'Hello World!'


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
	app.run(port=2664, debug=True)