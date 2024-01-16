import datetime
import json
import os
import ssl
import time
import jwt
import paho.mqtt.client as mqtt
import numpy as np
import configparser

config = configparser.ConfigParser()
config.read('config.ini')
gwConfig = config['gateway']
gcpConfig = config['gcp']

### Common Variables
jwt_alg = str(gwConfig['jwt_alg'])         
ca_certs = str(gwConfig['ca_certs'])
gw_DEVID = str(gwConfig['gw_DEVID'])
GWYID = str(gwConfig['GWYID'])
dev_keyDir = str(gwConfig['dev_keyDir'])
dev_metaDir = str(gwConfig['dev_metaDir'])
sampling_freq = int(gwConfig['sampling_freq'])
max_live_log = int(gwConfig['max_live_log'])

fdate = ''
num = 1
fname = ''
attachedDev = {}
live_log = []
keep_gcp_connect = False
LAMP = False

### Variables for GCP connection
project_id = str(gcpConfig['project_id'])
gw_private = str(gcpConfig['gw_private'])
gcp_region = str(gcpConfig['gcp_region'])
gcp_hostname = str(gcpConfig['gcp_hostname'])
gcp_port = int(gcpConfig['gcp_port'])
gw_registryID = str(gcpConfig['gw_registryID'])
gateway_id = str(gcpConfig['gateway_id'])

### Variables for Local MQTT Connection
local_hostname = str(gwConfig['local_hostname'])
local_port = int(gwConfig['local_port'])
local_data_topic = str(gwConfig['local_data_topic'])
local_state_topic = str(gwConfig['local_state_topic'])
internal_topic = str(gwConfig['internal_topic'])

### Common functions
def renew_filename():
    # Create new filename for logging
    # log/[date]_[number]_test1_log.txt
    global fdate
    global num
    global fname
    now = datetime.datetime.now()
    fdate = now.strftime("%Y%m%d")
    num = 1
    if not os.path.exists('log'):
        os.makedirs('log')
    for file in os.listdir('log/'):
        if file.endswith('_test1_log.txt') and file.startswith(fdate):
            fnum = file.split('_')[1]
            num = int(fnum) + 1
    fname = 'log/' + fdate + '_' + str(num) + '_test1_log.txt'
renew_filename()

def create_jwt(project_id, private_key_file, algorithm):
    # Create a JWT to establish an MQTT connection.
    token = {
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(minutes=60),
        'aud': project_id
    }
    with open(private_key_file, 'r') as f:
        private_key = f.read()
    return jwt.encode(token, private_key, algorithm=algorithm)

def error_str(rc):
    # Convert a Paho error to a human readable string.
    return '{}: {}'.format(rc, mqtt.error_string(rc))

def add_log(msg):
    # Add log history
    # Display it on terminal and save to the logfile
    now = datetime.datetime.now()
    date_time = now.strftime("%d-%m-%Y, %H:%M:%S")
    logStr = date_time + '\n'
    logStr = logStr + str(msg) + '\n'
    print(logStr)
    fdate_new = now.strftime("%Y%m%d")
    if fdate_new != fdate:
        renew_filename()
    with open(fname, "a") as f:
        f.write(logStr + '\n')

    live_log.append(logStr + '\n')
    if len(live_log) > max_live_log:
        live_log.pop(0)
    reporting()

def reporting():
    # Create live report text file to handle HTTP request
    # The live report includes list of attached devices and last several logs
    # Save it to live_log.txt so it can be accessed by the web server
    msg = ''
    msg += 'LIVE REPORT OF ' + GWYID + '\n\n'
    msg += 'Attached devices:\n'
    for key,val in zip(attachedDev.keys(),attachedDev.values()):
        msg += key + ' : ' + val + '\n'
    msg += '\n'
    msg += 'Latest log:\n'
    for i,log in enumerate(live_log):
        msg += f'[{i+1}] ' + str(log)
    with open('live_log.txt','w') as f:
        f.write(msg)

### IEQ Data generator
class ieq_sim():
    def __init__(self):
        # Initialize IEQ simulator parameter
        self.temp_sim = {'min':23.00,'max':30.00,'stdev':0.20}
        self.rh_sim = {'min':50.00,'max':80.00,'stdev':2.00}
        self.lux_sim = {'min':200,'max':300,'stdev':15}
        self.co2_sim = {'min':250,'max':500,'stdev':40}
        self.spl_sim = {'min':25,'max':45,'stdev':2}
        self.f = 2 * np.pi * 1/86400

    def calc(self,sim):
        # Calculate the new IEQ parameter
        now = datetime.datetime.now()
        midnight = now.replace(hour=0,minute=0,second=0,microsecond=0)
        today_second = (now - midnight).seconds
        val = (sim['max']+sim['min'])/2 - np.cos(self.f*today_second)*(sim['max']-sim['min'])/2
        val = np.random.normal(val,sim['stdev'])
        return val

    def gen_json(self):
        # Create JSON string that contains all data
        now = datetime.datetime.now()
        nowDate = now.strftime("%Y-%m-%d")
        nowTime = now.strftime("%H:%M:%S")
        ieq_dict = {
            'temp': round(self.calc(self.temp_sim),2),
            'rh': round(self.calc(self.rh_sim)),
            'lux': int(self.calc(self.lux_sim)),
            'co2': int(self.calc(self.co2_sim)),
            'spl': round(self.calc(self.spl_sim),2),
            'date': nowDate,
            'time': nowTime,
            'devID': gw_DEVID
        }
        jsonStr = json.dumps(ieq_dict)
        return jsonStr

### Handle connection to GCP MQTT
class mqtt_gcp():
    def __init__(self):
        self.local_handler = None
        self.isConnect = False
        self.keepConnect = True

        # Set GCP MQTT Client
        self.client = mqtt.Client(client_id = f'projects/{project_id}/locations/{gcp_region}/registries/{gw_registryID}/devices/{gateway_id}')
        self.client.tls_set(ca_certs=ca_certs, tls_version=ssl.PROTOCOL_TLSv1_2)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_publish = self.on_publish
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_unknown_msg
        add_log('Connection to GCP Initiated')

    def connect(self):
        # Connect to GCP
        self.client.username_pw_set(
            username = 'unused',
            password = create_jwt(project_id,gw_private,jwt_alg))
        self.client.connect(gcp_hostname,gcp_port)
        add_log('Trying to connect to GCP')
        self.client.loop_start()
        self.wait_connect()

        # Subscribe to the gateway config topic
        gw_config_topic = f'/devices/{gateway_id}/config'
        subs_id = self.client.subscribe(gw_config_topic,1)
        add_log('GCP subscription request sent for topic ' + gw_config_topic + ' ID ' + str(subs_id[1]))

        # Send each connected device's attachment request to GCP
        for key,val in zip(attachedDev.keys(),attachedDev.values()):
            keyName = f'{key}_rsa_private.pem'
            self.req_attachment(val,dev_keyDir+keyName)

    def wait_connect(self,timeout = 10):
        # Wait several seconds until connected to GCP
        total_time = 0
        while not self.isConnect and total_time < timeout:
            time.sleep(1)
            total_time += 1
        if not self.isConnect:
            logMsg = 'Cannot connect to GCP MQTT' 
            add_log(logMsg)
            return False
        else:
            return True

    def send_data(self,data):
        # Send data to GCP handle
        jsonData = json.loads(data)

        # Check whether device ID included in the payload
        if 'devID' in jsonData:
            dev_num = jsonData['devID']

            # Check whether the device ID is valid
            deviceID = self.auth_device(dev_num)
            if deviceID:
                # Add some missing data
                if not 'date' in jsonData:
                    jsonData['date'] = datetime.datetime.now().strftime("%Y-%m-%d")
                if not 'time' in jsonData:
                    jsonData['time'] = datetime.datetime.now().strftime("%H:%M:%S")
                jsonData['gwyID'] = GWYID
                new_data = json.dumps(jsonData)
                while not self.isConnect: self.connect()
                
                # Send the json payload
                sendTopic = f'/devices/{deviceID}/events'
                res = self.client.publish(sendTopic, new_data, qos=1)
                logMsg = f'Publishing to GCP (ID {res.mid}) : \n' + str(new_data)
                add_log(logMsg)
            else:
                add_log('Unknown source\n' + data)
        else:
            add_log('Device info is not included\n' + data)

    def auth_device(self,dev_num):
        # Check whether the device already attached to gateway
        if dev_num in attachedDev:
            return attachedDev[dev_num]
        
        # Check whether the gateway has information about the device
        metaName = f'{dev_num}_meta.txt'
        if metaName in os.listdir(dev_metaDir):
            with open(dev_metaDir+metaName,"r") as f:
                json_meta = json.load(f)
        else: 
            add_log('Meta file not found\n' + metaName)
            return ''

        # Check whether the gateway has the device's RSA key
        keyName = f'{dev_num}_rsa_private.pem'
        if not keyName in os.listdir(dev_keyDir):
            add_log('Private key not found\n' + keyName)
            return ''
        
        # Send attachment request to GCP
        self.req_attachment(json_meta['ID'],dev_keyDir+keyName)
        attachedDev[dev_num] = json_meta['ID']
        return attachedDev[dev_num]

    def req_attachment(self,ID, keyFile):
        # Send device attachment request to GCP
        token = create_jwt(project_id,keyFile,jwt_alg)
        token = str(token)[2:-1]
        payload = '{\"authorization\":\"'+ token +'\"}'
        topic = f'/devices/{ID}/attach'
        res = self.client.publish(topic,payload,1)
        logMsg = f'Sending GCP attachment request for {ID} with message ID {res.mid}'
        add_log(logMsg)
        time.sleep(3)

        # Subscribe to the device's config topic
        dev_config_topic = f'/devices/{ID}/config'
        subs_id = self.client.subscribe(dev_config_topic,1)
        self.client.message_callback_add(dev_config_topic,self.on_config_msg)
        add_log('GCP subscription request sent for topic ' + dev_config_topic + ' ID ' + str(subs_id[1]))

        # Subscribe to the device's config topic
        dev_command_topic = f'/devices/{ID}/commands'
        subs_id = self.client.subscribe(dev_command_topic+'/#',1)
        self.client.message_callback_add(dev_command_topic,self.on_command_msg)
        add_log('GCP subscription request sent for topic ' + dev_command_topic + '/# ID ' + str(subs_id[1]))

    def publish_state(self,num,state):
        # Send state message to GCP in response to config message
        if num in attachedDev:
            state_topic = f'/devices/{attachedDev[num]}/state'
            res = self.client.publish(state_topic,state,1)
            logMsg = f'Publishing to GCP (ID {res.mid}) topic {state_topic}: \n' + str(state)
            add_log(logMsg)    
        else:
            logMsg = f'Received state is from unknown device\n' + state
            add_log(logMsg)

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        # Function when the gateway connected to GCP
        logMsg = 'Connected to GCP MQTT: \n' + error_str(rc) 
        self.isConnect = True
        add_log(logMsg)
    
    def on_disconnect(self, unused_client, unused_userdata, rc):
        # Function when gateway disconnected from GCP
        global attachedDev
        self.isConnect = False
        logMsg = 'Disconnected from GCP MQTT: \n' + error_str(rc)
        add_log(logMsg)
        if self.keepConnect:
            self.connect()

    def on_publish(self, unused_client, unused_userdata, mid):
        # Function when receive PUBACK
        logMsg = f'Publish to GCP (ID {mid}) successful'
        add_log(logMsg)

    def on_subscribe(self,client, unused_userdata, mid, granted_qos):
         # Function when subscription request responded
        add_log('Respond for GCP subscription request ID ' + str(mid) + '\nQoS ' + str(granted_qos[0]))       

    def on_config_msg(self, unused_client, unused_userdata, message):
        # Function to handle config message from GCP
        global sampling_freq
        dev_config = message.topic.split('/')[2]
        logMsg = f'Received config message on GCP topic {message.topic}\n{message.payload}'
        for key,val in zip(attachedDev.keys(),attachedDev.values()):
            if val == dev_config:
                # Do the config instruction if the config is for the gateway
                if key == gw_DEVID:
                    cfg = json.loads(message.payload.decode('utf-8'))
                    # Change the sampling period
                    if 'sampling' in cfg:
                        sampling_freq = cfg['sampling']
                        logMsg = logMsg + f'\n{key} Sampling changed to {sampling_freq}'
                        state = {
                            'devID':key,
                            'sampling':sampling_freq
                        }
                        # Send a state message as response
                        self.publish_state(key,json.dumps(state))
                else:
                    # Forward the config message to local MQTT if it is not for the gateway
                    self.local_handler.publish_config(key,message.payload.decode('utf-8'))
                    logMsg = logMsg + f'\nConfig found for {key}'
        add_log(logMsg)

    def on_command_msg(self, unused_client, unused_userdata, message):
        # Function to handle command message from GCP
        global LAMP
        dev_config = message.topic.split('/')[2]
        logMsg = f'Received command message on GCP topic {message.topic}\n{message.payload}'
        for key,val in zip(attachedDev.keys(),attachedDev.values()):
            if val == dev_config:
                # Do the command instruction if the config is for the gateway
                if key == gw_DEVID:
                    msg = message.payload.decode('utf-8')
                    if msg == 'ON':
                        LAMP = True
                    elif msg =='OFF':
                        LAMP = False
                    else:
                        logMsg = logMsg + f'\nUnknown command for {key}'
                    if LAMP: lstat = 'ON' 
                    else: lstat = 'OFF'
                    logMsg = logMsg + f'\n{key} lamp status ' + str(lstat)
                    light_dict = {
                        "devID":str(key),
                        "lamp":int(LAMP)
                    }
                    self.send_data(json.dumps(light_dict))
                    
                else:
                    # Forward the command message to local MQTT if it is not for the gateway
                    self.local_handler.publish_command(key,message.payload.decode('utf-8'))
                    logMsg = logMsg + f'\nCommand found for {key}'
        add_log(logMsg) 

    def on_unknown_msg(self, unused_client, unused_userdata, message):
        # Function when a new publish occured in unknown topic
        logMsg = "An unknown message from GCP topic " + str(message.topic) + "\n"
        logMsg = logMsg + str(message.payload)
        add_log(logMsg)

    def stop(self):
        # Stop the GCP MQTT client
        add_log('Stopping GCP client')
        self.keepConnect = False
        self.client.disconnect()
        self.client.loop_stop()

### Handle connection to local MQTT
class mqtt_local():
    def __init__(self):
        self.cloud_handler = None
        self.isConnect = False

        # Set local MQTT Client
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_unknown_msg
        self.client.on_subscribe = self.on_subscribe
        self.client.message_callback_add(local_data_topic,self.on_gw1_pub_msg)
        self.client.message_callback_add(local_state_topic,self.on_state_msg)
        self.client.message_callback_add(internal_topic,self.on_internal_msg)
        add_log('Connection to Local MQTT Initiated')

    def connect(self):
        # Connect to local MQTT
        self.client.connect(local_hostname,local_port)
        add_log('Trying to connect to Local MQTT')
        self.client.loop_start()
        time.sleep(3)
        # Subscribe to inernal, local data and state topic 
        subs_id = self.client.subscribe(local_data_topic,1)
        add_log('Local subscription request sent for topic ' + local_data_topic + ' ID ' + str(subs_id[1]))
        subs_id = self.client.subscribe(local_state_topic,1)
        add_log('Local subscription request sent for topic ' + local_state_topic + ' ID ' + str(subs_id[1]))
        subs_id = self.client.subscribe(internal_topic,1)
        add_log('Local subscription request sent for topic ' + internal_topic + ' ID ' + str(subs_id[1]))
        self.wait_connect()

    def wait_connect(self,timeout = 10):
        # Wait until the gateway connected to the broker
        total_time = 0
        while not self.isConnect and total_time < timeout:
            time.sleep(1)
            total_time += 1
        if not self.isConnect:
            logMsg = 'Cannot connect to Local MQTT' 
            add_log(logMsg)
            return False
        else:
            return True

    def publish_config(self,devid,msg):
        # Function to send device config to the device's config topic
        config_topic = f'{devid}/config'
        res = self.client.publish(config_topic,msg,2)
        logMsg = f'Publishing to local network {config_topic} (ID {res.mid}) : \n' + str(msg)
        add_log(logMsg)

    def publish_command(self,devid,msg):
        # Function to send device command to the device's command topic
        command_topic = f'{devid}/commands'
        res = self.client.publish(command_topic,msg,2)
        logMsg = f'Publishing to local network {command_topic} (ID {res.mid}) : \n' + str(msg)
        add_log(logMsg)

    def on_connect(self, unused_client, unused_userdata, unused_flags, rc):
        # Function when the gateway connected to local broker
        logMsg = 'Connected to Local MQTT: \n' + error_str(rc) 
        self.isConnect = True
        add_log(logMsg)
    
    def on_subscribe(self,client, unused_userdata, mid, granted_qos):
        # Function when subscription request responded
        add_log('Respond for local MQTT subscription request ID ' + str(mid) + '\nQoS ' + str(granted_qos[0]))

    def on_disconnect(self, unused_client, unused_userdata, rc):
        # Function when the gateway disconnected from the brokeer
        self.isConnect = False
        logMsg = 'Disconnected from Local MQTT: \n' + error_str(rc)
        add_log(logMsg)

    def on_publish(self, unused_client, unused_userdata, mid):
        # Function when receive PUBACK
        logMsg = f'Publish to local network (ID {mid}) successful'
        add_log(logMsg)

    def on_gw1_pub_msg(self, unused_client, unused_userdata, message):
        # Function when a new publish occured in /gw1/pub
        logMsg = "A new publish on local topic " + str(message.topic) + "\n"
        msg = str(message.payload.decode('utf-8')).replace('\r\n','')
        logMsg = logMsg + str(message.payload)
        add_log(logMsg)

        # Send the payload to GCP via GCP client
        self.cloud_handler.send_data(msg)

    def on_state_msg(self, unused_client, unused_userdata, message):
        # Forward the state message to GCP via GCP client
        # when a new state message arrived from local device
        state = message.payload.decode('utf-8')
        statejson = json.loads(state)
        if 'devID' in statejson:
            logMsg = f'Received state from local MQTT\n{message.payload}'
            add_log(logMsg)
            self.cloud_handler.publish_state(statejson['devID'],state)
        else:
            logMsg = f'Received state without identity\n' + message.payload

    def on_internal_msg(self, unused_client, unused_userdata, message):
        # Function to handle command message from GCP
        global LAMP
        msgd = json.loads(message.payload.decode('utf-8'))
        dev_config = msgd['devID']
        print(dev_config)
        logMsg = f'Received command message on local topic {message.topic}\n{message.payload}'
        for key,val in zip(attachedDev.keys(),attachedDev.values()):
            if key == dev_config:
                # Do the command instruction if the config is for the gateway
                if key == gw_DEVID:
                    msg = msgd['light']
                    if msg == 'ON':
                        LAMP = True
                    elif msg =='OFF':
                        LAMP = False
                    else:
                        logMsg = logMsg + f'\nUnknown command for {key}'
                    if LAMP: lstat = 'ON' 
                    else: lstat = 'OFF'
                    logMsg = logMsg + f'\n{key} lamp status ' + str(lstat)
                    light_dict = {
                        "devID":str(key),
                        "lamp":int(LAMP)
                    }
                    self.cloud_handler.send_data(json.dumps(light_dict))
                    
                else:
                    # Forward the command message to local MQTT if it is not for the gateway
                    self.publish_command(key,msg['light'])
                    logMsg = logMsg + f'\nCommand found for {key}'
        add_log(logMsg)         

    def on_unknown_msg(self, unused_client, unused_userdata, message):
        # Function when a new publish occured in unknown topic
        logMsg = "An unknown message from local topic " + str(message.topic) + "\n"
        logMsg = logMsg + str(message.payload)
        add_log(logMsg)

    def stop(self):
        # Stop the local MQTT client
        add_log('Stopping Local MQTT client')
        self.client.disconnect()
        self.client.loop_stop()

### Main function
def main():
    # Initializa GCP MQTT client and local MQTT client
    gcp = mqtt_gcp()
    loc = mqtt_local()
    gcp.local_handler = loc
    loc.cloud_handler = gcp
    ieq = ieq_sim()

    try:
        gcp.connect()
        loc.connect()
        while True:
            # Generate data and send to GCP
            data = ieq.gen_json()
            gcp.send_data(data)
            time.sleep(sampling_freq)
    
    except Exception as er:
        add_log('Program terminated')
        add_log(er)

    finally:
        gcp.stop()
        loc.stop()

if __name__ == '__main__':
    main()
