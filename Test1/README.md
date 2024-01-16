# Before You Begin

*These codes are made based on Python 3.7*

*These codes have been tested for 24 hours operation. The resulting log files and SQL data for this test can be seen inside `testresults/20201107_24hrs`*

*When we say 'device', it means a device that collects the data directly from sensors just like a microprocessor. However, a gateway device like raspberry pi also can be used to collect data. In this case, the raspberry pi will also act as 'device'.*

*Instruction provided here are the steps required to run our codes. For details about how the codes work, you can check the comments written in each code.*

*The codes are made for functional demo purposes only. Of course, if you want to implement it somewhere you might need to add more functions to make the system more practical*

# Prepare Everything

## Preparing the GCP Services

First of all, you need to prepare some services in GCP. For more details about each service configuration, we recommend you to read the documentation of the service.

### Cloud SQL

In our case, we use MySQL as our database and we will only use one table to store all of the data sent to GCP. In `sql_statements.sql`, we have listed several SQL queries that might be useful for operating the database. As stated in the first query, the database (namely `ieq_data`) will contains a table (namely `ieq_table`) that will store these data: temperature, relative humidity, illuminance, CO2 concentration, noise level (SPL), date-time when the data was taken, the ID of the device that captured the data, and the ID of the gateway that sent the data to GCP. After you have initiated an instance in Cloud SQL, create a database (namely `ieq_data`) in that instance and then execute the first query in `sql_statements.sql`. To check whether the table has been created in the right way, you can execute `DEFINE ieq_table;` to check the details of the table. Make sure it has all the fields we mentioned before.

### Pub/Sub

Create a new topic in GCP Pub/Sub, don't check the CMEK option because we do not use it in this case as the authentication will be handled by IoT core. This topic will be used as the main topic for the telemetry data stream. 

### IoT Core

Create a new registry in GCP IoT Core. After that, create two new devices in the registry. We will use our own encryption keys for these devices. So first, you need to [create two pairs of public-private RSA256 keys](https://cloud.google.com/iot/docs/how-tos/credentials/keys), one for each device. After the keys have been created, upload the public key to the 'Authentication' menu in the device setting. After the devices are ready, create a new gateway in IoT Core. Create one more RSA256 key pair and upload the public key to the 'Authentication' menu of the gateway. Set the 'Device authentication method' of the gateway to 'Both association and device credentials' as we assume that we want to use the most secure authentication method. At last, bound the two devices that you have created to the gateway. 

### Cloud Function

We use Cloud Function to move the data received by Pub/Sub to the SQL storage. Create a new function and set the trigger to the Pub/Sub topic that you have created before. Then, import two files in the `cloud_function` folder to the function's source and set the entry point to `insert` function. Don't forget to fill the `connection_name` and `password` variables in the code with the ones that you own. You're ready to deploy the function.

## Preparing Local System

We are going to test the system with one gateway and two devices. For our case, we set gateway name to 'GWY001' and the device name to 'DEV001' and 'DEV002'. DEV001 is the device name for the gateway itself, since the gateway will also generate data. DEV002 is another additional device which can be a microprocessor or any device that you want to use for testing. 

First, create these folders in the same directory as `gateway.py`

#### `device_key`

Move all of the public and private key files. Rename the key files to `{DEV001/DEV002}_rsa_{public/public}.pem` (change the `{...}` accordingly). Since we will have two devices and each one has one public and one private key, we will have four files in this folder

#### `device_list`

This folder will contain information required to connect your devices to GCP. Create one txt file for each device and name it `{DEV001/DEV002}_meta.txt`. Each file will contains information about the device's GCP ID name written in JSON like this (replace `[GCP_ID]` with your device's GCP ID)

```
{
	"ID":"[GCP_ID]"
}
```

Save the public key and private key of the gateway in the same directory as `gateway.py`, then name them `rsa_public.pem` and `rsa_private.pem` respectively. Also save the [google MQTT root CA certificate](https://pki.goog/roots.pem) `roots.pem` in the same directory. One more, you also need to create a text file named `projectid.txt`. Fill the file with one line text of your GCP's project ID.

You also need to install mosquitto in your gateway, which is a program that will be used to start a local MQTT broker in your gateway. We will use the local MQTT network for the communication between gateway and devices

# Testing the System

To start the system, first start the local MQTT broker by running mosquitto (click [here](https://mosquitto.org/download/) to download mosquitto). Then, run the `gateway.py`. By running this program, your gateway will establish connections to both GCP and musquitto. Then, it will generate dummy IEQ data as DEV001 each 15 seconds and send them to GCP. As the `gateway.py` is running, it will automatically create a txt log file inside `log` folder. 

## Sending data from other device

As what we have described, we have another device, DEV002, that will be able to send data to the gateway through the local MQTT connection. To send the data from the device to the gateway, first connect to the mosquitto broker. The address of the broker will be the same as your gateway IP address and the port by default is 1883. To send the data, publish the JSON formatted to topic `GWY/data`. The gateway has been set to subscribe to that topic so that any message sent to the topic will be forwarded to the gateway. The complete format example of the data sent from the device (DEV002) should be like this

```
{"temp": 27.73, "rh": 71, "lux": 286, "co2": 436, "spl": 34.22, "date": "2020-11-07", "time": "16:14:58", "devID": "DEV002"}

```

Except the `"devID"`, you can omit the other fields as you need. After the gateway receives the message, it will check whether the `devID` has been listed in folder `device_list` and the key is available in `device_key`. Once it has verified the device, the gateway will send the data to GCP.

## Configuring the device

Note that GCP IoT core provides a configuration function which can be used to configure some settings of the device. In the code that we provide here, for now the configuration that can be set from GCP is only the sampling period (by default it is 15 seconds). To send a configuration message, access the IoT core and open the page of the device that you want to configure. Then, click `UPDATE CONFIG` and fill the configuration message. To change the sampling period to, for example, 1 minute (60 seconds), the configuration message should be like this

```
{"sampling": 60}

```

The message will be sent to the gateway first and if it is not for the gateway (DEV001), the gateway will forward the message to topic '{devID}/config' (for DEV002, it is DEV002/config). After the device changes its configuration, it will send a state message back to GCP that contains information of the new `sampling` period and `devID` in JSON format. For DEV002, it has to send the state message to topic 'GWY/state' that has been subscribed by the gateway. The state message can be seen from IoT Core in the 'CONFIGURATION & STATE' menu of the device's page. Note that the latest configuration message will be automatically sent to the device each time the device reconnects to the GCP

## Access the gateway's live Log from local network

To make the gateway information accessible from local, you can start a simple HTTP server by running `web_server.py`. The server can be accessed from the local network by sending a GET request to the gateway's IP address with port 8080, or simply type {getewayIP}:8080 in your browser's address bar. The program will read the request and send 20 latest log messages and a list of connected devices as the response.
