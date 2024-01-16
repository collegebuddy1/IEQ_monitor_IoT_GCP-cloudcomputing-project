from http.server import HTTPServer
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse
from urllib.parse import parse_qs
import socketserver
import paho.mqtt.client as mqtt
import time
import configparser
import json

config = configparser.ConfigParser()
config.read('config.ini')
gwConfig = config['gateway']
local_hostname = str(gwConfig['local_hostname'])
local_port = int(gwConfig['local_port'])
internal_topic = str(gwConfig['internal_topic'])

def error_str(rc):
    # Convert a Paho error to a human readable string.
    return '{}: {}'.format(rc, mqtt.error_string(rc))

### Handling local MQTT
class mqtt_local():
    def __init__(self):
        self.isConnect = False

        # Set local MQTT Client
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        print('Connection to Local MQTT Initiated')

    def connect(self):
        # Connect to local MQTT
        self.client.connect(local_hostname,local_port)
        print('Trying to connect to Local MQTT')
        self.client.loop_start()
        time.sleep(3)

    def wait_connect(self,timeout = 10):
        # Wait until the gateway connected to the broker
        total_time = 0
        while not self.isConnect and total_time < timeout:
            time.sleep(1)
            total_time += 1
        if not self.isConnect:
            logMsg = 'Cannot connect to Local MQTT' 
            print(logMsg)
            return False
        else:
            return True

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        # Function when the gateway connected to local broker
        logMsg = 'Connected to Local MQTT: \n' + error_str(rc) 
        self.isConnect = True
        print(logMsg)

    def on_disconnect(self, unused_client, unused_userdata, rc):
        # Function when the gateway disconnected from the brokeer
        self.isConnect = False
        logMsg = 'Disconnected from Local MQTT: \n' + error_str(rc)
        print(logMsg)
    
    def on_publish(self, unused_client, unused_userdata, mid):
        # Function when receive PUBACK
        logMsg = f'Publish to local network (ID {mid}) successful'
        print(logMsg)

    def publish_command(self,msg):
        # Function to send device config to the device's config topic
        res = self.client.publish(internal_topic,msg,1)
        logMsg = f'Publishing to local network {internal_topic} (ID {res.mid}) : \n' + str(msg)
        print(logMsg)
mqttloc = mqtt_local()
mqttloc.connect()

### Handling HTTP Request
class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/lamp':
            self.lamp_handler()
        else:
            self.basic_return()

    def lamp_handler(self):
        url = urlparse(self.path)
        qd = parse_qs(url.query)
        if ('devid' in qd) and ('light' in qd):
            msg = f'Accepted command {qd["light"][0]} for {qd["devid"][0]}'
            msgd = {
                'devID':qd["devid"][0],
                'light':qd["light"][0]
            }
            msg = json.dumps(msgd)
            mqttloc.publish_command(msg)

        else:
            msg = 'Unknown command'

        self.send_response(200)
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))

    def basic_return(self):
        with open('live_log.txt','r') as f:
            msg = f.read()
        self.send_response(200)
        self.send_header('Content-Type','text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(msg.encode('utf-8'))

PORT = 8080
webServer = HTTPServer(('',8080),WebHandler)
webServer.serve_forever()