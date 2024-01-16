//Upload IEQ data to Gateway 
//Parameters: Suhu, RH, Iluminansi, SPL, CO2

#include <ESP8266WiFi.h>
#include <WiFiClient.h>
#include <PubSubClient.h>
#include <TaskScheduler.h>
#include <ArduinoJson.h>
#include "genData.h"

void startCon();
void mqttCon(int maxTry);
void callback(char* topic, byte* payload, unsigned int length);
void callback_command(byte* payload, unsigned int length);
void callback_config(byte* payload, unsigned int length);
void publishState(int sampling);
void publishLamp();
void uploadData();

const char* ssid = "SCADA_GWY001";
const char* password = "123sampai8";
const char* mqtt_server = "192.168.200.1";

const int mqtt_port = 1883;
String mqttID = "DEV002";
const char* TOPIC_DATA = "GWY/data";
const char* TOPIC_CONFIG = "DEV002/config";
const char* TOPIC_COMMAND = "DEV002/commands";
const char* TOPIC_STATE = "GWY/state";

int f_sampling = 15 * 1000;
bool lamp = false;
String postData;
int nowTime;

Task publishTask(f_sampling, TASK_FOREVER, &publishData);
Scheduler sendLoop;

WiFiClient wificlient;
PubSubClient client(wificlient);
DynamicJsonDocument jsonData(1024);

void setup() {
  Serial.begin(9600);
  delay(10000);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  startCon();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
  mqttCon(5);

  sendLoop.addTask(publishTask);
  publishTask.enable();
}

void loop() {
  sendLoop.execute();
  client.loop();
  if (WiFi.status() != WL_CONNECTED){
    startCon();
  }
}

void startCon(){
  Serial.println();
  Serial.println();
  Serial.print("Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, password);
  WiFi.mode(WIFI_STA);
  int i = 0;
  while (WiFi.status() != WL_CONNECTED && i<50) {
    delay(500);
    Serial.print(".");
    i++;
  }
  
  if (WiFi.status() == WL_CONNECTED){
    Serial.println();
    Serial.println("WiFi connected");
    Serial.print("IP address: ");
    Serial.println(WiFi.localIP());
    Serial.print("Gateway: ");
    Serial.println(WiFi.gatewayIP());
    Serial.print("SubnetMask: ");
    Serial.println(WiFi.subnetMask());
  }
  else {
    Serial.println();
    Serial.println("Failed to connect to AP");
  }
}

void mqttCon(int maxTry){
  int i = 1;
  while (!client.connected() && i<=maxTry){
    Serial.println("Attempting MQTT connection...");
    if(client.connect(mqttID.c_str())){
      Serial.println("connected");
      delay(1000);
      client.subscribe(TOPIC_CONFIG);
      client.subscribe(TOPIC_COMMAND);
      delay(5000);
    }else{
      Serial.println("Failed to connect");
      delay(5000); 
    }
    i = i + 1;
  }
}

void callback(char* topic, byte* payload, unsigned int length){
  Serial.println();
  Serial.println("----New Message----");
  Serial.print("channel:");
  Serial.println(topic);
  Serial.print("data:");
  Serial.write(payload,length);
  Serial.println();
  
  if(strcmp(topic, TOPIC_CONFIG) == 0){
    callback_config(payload,length);
  }
  
  else if(strcmp(topic, TOPIC_COMMAND) == 0){
    callback_command(payload,length);
  }
}

void callback_command(byte* payload, unsigned int length){
  String msg_light;
  for (int i = 0; i < length; i++) {
    msg_light += (char)payload[i];
  }
  
  if(msg_light=="ON"){
    lamp = true;
    digitalWrite(LED_BUILTIN, LOW);
    Serial.println("LED turned on");
  }
  else if(msg_light=="OFF"){
    lamp = false;
    digitalWrite(LED_BUILTIN, HIGH);
    Serial.println("LED turned off");
  }
  else{
    Serial.println("Unknown command");
  }
  publishLamp();
}
  
void callback_config(byte* payload, unsigned int length){
  DeserializationError jsonError = deserializeJson(jsonData, payload);
  if (jsonError){
    Serial.print(F("Failed to deserialize JSON: "));
    Serial.println(jsonError.f_str());
  } else if(!jsonData.containsKey("sampling")){
    Serial.println("No sampling information");   
  } else{
    f_sampling = int(jsonData["sampling"]);
    f_sampling = f_sampling * 1000;
    if (f_sampling < 1000){
      f_sampling = 1000;
    }
    publishTask.setInterval(f_sampling);
    Serial.print("Sampling interval changed to (ms) ");
    Serial.println(f_sampling);
  }
  publishState(f_sampling/1000);
}

void publishState(int sampling){
  String msg = "{\"devID\":\"" + mqttID + "\",";
  msg += "\"sampling\":" + String(sampling) + "}";
  int str_len = msg.length()+1;
  char postDataChar[str_len];
  msg.toCharArray(postDataChar,str_len);
  Serial.println();
  if (WiFi.status() == WL_CONNECTED){
    mqttCon(5);
    client.publish(TOPIC_STATE,postDataChar);
    Serial.print("Sending to topic ");
    Serial.println(TOPIC_STATE);
    Serial.println(msg);
  } else{
    Serial.println("Cannot connect to AP");
  }
}

void publishLamp(){
  int ledstat;
  if(lamp){
    ledstat = 1;
  }else{
    ledstat = 0;
  }
  String msg = "{\"devID\":\"" + mqttID + "\",";
  msg += "\"lamp\":" + String(ledstat) + "}";
  int str_len = msg.length()+1;
  char postDataChar[str_len];
  msg.toCharArray(postDataChar,str_len);
  Serial.println();
  if (WiFi.status() == WL_CONNECTED){
    mqttCon(5);
    client.publish(TOPIC_DATA,postDataChar);
    Serial.print("Sending to topic ");
    Serial.println(TOPIC_DATA);
    Serial.println(msg);
  } else{
    Serial.println("Cannot connect to AP");
  }
}

void publishData(){
  nowTime = millis()/1000;
  postData = formatData(nowTime, mqttID);
  int str_len = postData.length()+1;
  char postDataChar[str_len];
  postData.toCharArray(postDataChar,str_len);
  Serial.println();
  if (WiFi.status() == WL_CONNECTED){
    mqttCon(5);
    client.publish(TOPIC_DATA,postDataChar);
    Serial.print("Sending to topic ");
    Serial.println(TOPIC_DATA);
    Serial.println(postDataChar);
  } else{
    Serial.println("Cannot connect to AP");
  }
}
