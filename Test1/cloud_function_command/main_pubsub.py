import json
import base64
import configparser
from google.cloud import iot_v1

config = configparser.ConfigParser()
config.read('config.ini')
cfg = config['main']

project_id = str(cfg['project_id']) 
cloud_region = str(cfg['cloud_region'])
registry_id = str(cfg['registry_id'])
client = iot_v1.DeviceManagerClient()

def command(event,context):
    if 'data' in event:
        jsonStr = base64.b64decode(event['data']).decode('utf-8')
        jsonDict = json.loads(jsonStr)
        if 'devID' not in jsonDict:
            return None
        device_id = 'tugas_scada_tim7_' + str(jsonDict['devID'])
        if 'light' in jsonDict:
            send(device_id,str(jsonDict['light']))
        return None

def send(device_id,com):
    data = com.encode("utf-8")
    device_path = client.device_path(project_id, cloud_region, registry_id, device_id)
    return client.send_command_to_device(
        request={"name": device_path, "binary_data": data}
    )