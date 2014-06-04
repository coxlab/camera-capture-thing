from flask import Flask 
from flask_sockets import Sockets

app = Flask(__name__) 
sockets = Sockets(app)

@sockets.route('/image_src') 
def image_socket(ws): 
    while True: 
        message = ws.receive() 
        ws.send(message)

@app.route('/') 
def hello(): 
    return 'Hello World!'



if __name__ == '__main__':
	app.run(port=2664, debug=True)