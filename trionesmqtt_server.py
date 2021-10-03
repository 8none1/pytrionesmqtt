#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import json
import logging

logging.basicConfig(level=logging.DEBUG)

# This is just the server.  It listens to MQTT and then sends messages out to the registered workers to ask them to do the work.

mqtt_server = None
mqtt_server_ip = "mqtt" # Change to the IP address of your MQTT server.  If you need an MQTT server, look at Mosquitto.
mqtt_subscription_topic = "triones/control" # Where we will listen for messages to act on.
mqtt_reporting_topic = "triones/status" # Where we will send status messages

WORKERS = []

def mqtt_on_connect(client, userdata, flags, rc):
    logging.info(f"MQTT Connected, subscribing to {mqtt_subscription_topic}")
    client.subscribe(mqtt_subscription_topic)

#def send_mqtt(mqtt_client,value):
#    logging("MQTT: Sending value: %s to topic %s" % (value, mqtt_reporting_topic))
#    mqtt_client.publish(mqtt_reporting_topic, value)

def mqtt_message_received(client, userdata, message):
    if message.topic == mqtt_subscription_topic:
        # get status
        # set mode
        # set speed
        
        try:
            json_request = json.loads(message.payload)
            logging.info("MQTT message received. Trying to parse payload...")
            logging.info(json.dumps(json_request, indent=4, sort_keys=True))

            if "mac" in json_request.keys():
                mac = json_request["mac"]
                logging.info(f"Received Triones request for device: {mac}")
                # Need to do more actual work in here.
            elif "register" in json_request.keys():
                worker_hostname = json_request["hostname"]
                logging.info(f"Received registration request from {worker_hostname}.")
                if worker_hostname not in WORKERS:
                    logging.info(f"Adding {worker_hostname} to list of workers.")
                    WORKERS.append(worker_hostname)
                    payload = json.dumps({"ack":True})
                    logging.info(f"Sending ack to {worker_hostname}.")
                    client.publish(mqtt_subscription_topic+"/"+worker_hostname,payload)
                    client.loop_write()
            else:
                logging.info("Received unhandled request.  Doing nothing.")
                return False
        except:
            logging.info("Failed to parse payload JSON.  Giving up")
            return False



if mqtt_server_ip is not None:
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_message = mqtt_message_received
    mqtt_client.connect(mqtt_server_ip, 1883, 60)
else:
    raise NameError("No MQTT Server configured")

while True:
    mqtt_client.loop()

