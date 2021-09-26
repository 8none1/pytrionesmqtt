#!/usr/bin/env python3

'''
Talks to cheapo LED BTLE controllers, typically named Triones
Requires bluepy from pip or https://github.com/IanHarvey/bluepy


W Cooke - 2021
@8none1
https://github.com/8none1

Thanks to this page for the protocol: https://github.com/madhead/saberlight/blob/master/protocols/Triones/protocol.md
If you don't want to run this script as root you need to read: https://github.com/IanHarvey/bluepy/issues/313

'''

from bluepy.btle import *
import paho.mqtt.client as mqtt
import json
import sys
import colorsys


debug = True # Prints messages to stdout. Once things are working set this to False
mqtt_server = None
mqtt_server_ip = "mqtt" # Change to the IP address of your MQTT server.  If you need an MQTT server, look at Mosquitto.
mqtt_subscription_topic = "triones/control" # Where we will listen for messages to act on.
mqtt_reporting_topic = "triones/status" # Where we will send status messages

# Triones constants
MAIN_SERVICE         = 0xFFD5 # Service which provides the characteristics 
MAIN_CHARACTERISTIC  = 0xFFD9 # Where all our commeands go
GET_STATUS           = bytearray.fromhex("EF 01 77")
SET_POWER_ON         = bytearray.fromhex("CC 23 33")
SET_POWER_OFF        = bytearray.fromhex("CC 24 33")
SET_COLOUR_BASE      = bytearray.fromhex("56 ff ff ff 00 F0 AA")
SET_MODE             = bytearray.fromhex("BB 27 7F 44")
#  MODE from MODES_DICT ---------------------^ 
#  SPEED from 01 to FF ------------------------ ^ 

# Some other examples if you need them...
#SET_STATIC_COL_RED   = bytearray.fromhex("56 ff 00 00 00 F0 AA")
#SET_STATIC_COL_GREEN = bytearray.fromhex("56 00 ff 00 00 F0 AA")
#SET_STATIC_COL_BLUE  = bytearray.fromhex("56 00 00 ff 00 F0 AA")
#SET_STATIC_COL_WHITE = bytearray.fromhex("56 00 00 00 FF 0F AA")
# MODES_DICT = {
# 0x25: "Seven color cross fade",
# 0x26: "Red gradual change",
# 0x27: "Green gradual change",
# 0x28: "Blue gradual change",
# 0x29: "Yellow gradual change",
# 0x2A: "Cyan gradual change",
# 0x2B: "Purple gradual change",
# 0x2C: "White gradual change",
# 0x2D: "Red, Green cross fade",
# 0x2E: "Red blue cross fade",
# 0x2F: "Green blue cross fade",
# 0x30: "Seven color stobe flash",
# 0x31: "Red strobe flash",
# 0x32: "Green strobe flash",
# 0x33: "Blue strobe flash",
# 0x34: "Yellow strobe flash",
# 0x35: "Cyan strobe flash",
# 0x36: "Purple strobe flash",
# 0x37: "White strobe flash",
# 0x38: "Seven color jumping change"
# }


def logger(message):
    if debug: print(message)

def philips_hue_to_real_hue(hue):
    # Get to degrees
    return hue / 65535

def convert_philips_sv(bri):
    return bri/254

def send_mqtt(mqtt_client,value):
    logger("MQTT: Sending value: %s to topic %s" % (value, mqtt_reporting_topic))
    mqtt_client.publish(mqtt_reporting_topic, value)

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            logger(f"Discovered device: {dev.addr}")

class DataDelegate(DefaultDelegate):
    def __init__(self,mqtt_client, mac):
        DefaultDelegate.__init__(self)
        self.mqtt_client = mqtt_client
        self.mac = mac
    
    def handleNotification(self, cHandle, data):
        logger(f"Notification from device: {self.mac}")
        if cHandle == 12:
            # The protocol for my devices looks like 0x66,0x4,power,mode,0x20,speed,red,green,blue,white,0x3,0x99
            # This is a response to a status update
            # Hex response looks like
            # Off (but red)
            # ['0x66', '0x4', '0x24', '0x41', '0x20', '0x1', '0xff', '0x0', '0x0', '0x0', '0x3', '0x99']
            # Off but blue
            # ['0x66', '0x4', '0x24', '0x41', '0x20', '0x1', '0x0', '0x0', '0xff', '0x0', '0x3', '0x99']
            # On but green
            # ['0x66', '0x4', '0x23', '0x41', '0x20', '0x1', '0x0', '0xff', '0x0', '0x0', '0x3', '0x99']

            data = [hex(x) for x in data]
            logger("Response received: "+str(data))
            if data[0] == "0x66" and data[1] == "0x4" and data[11] == "0x99":
                # Probably what we're looking for
                power = True if data[2] == "0x23" else False
                mode  = int(data[3], base=16)
                speed = int(data[5], base=16)
                rgb   = [int(data[6], base=16), int(data[7], base=16), int(data[8], base=16)]
                # white = data[9] # My LEDs dont have white
                json_status = json.dumps({"mac":self.mac, "power":power, "rgb":rgb, "speed": speed, "mode":mode})# json_status?  Wasn't he in Fast and Furious?
                logger(json_status)
                send_mqtt(self.mqtt_client, json_status)
            else:
                logger("Didn't understand the response data.")
        else:
            logger(f"Got a different handle: {cHandle}")

def mqtt_on_connect(client, userdata, flags, rc):
    logger("MQTT Connected")
    client.subscribe(mqtt_subscription_topic)

def mqtt_message_received(client, userdata, message):
    if message.topic == mqtt_subscription_topic:
        # get status
        # set colour [rrr,ggg,bbb]
        # set mode
        # set speed
        # set brightness.  Accept a brightness in, and then scale the rgb values accordingly?

        try:
            json_request = json.loads(message.payload)
            mac = json_request["mac"]
            logger(f"Received MQTT request for device: {mac}")
            logger(json.dumps(json_request, indent=4, sort_keys=True))
        except:
            logger("Failed to parse payload JSON.  Giving up")
            return False

        # Set up a connection to the device
        try:
            trione = Peripheral(mac) # We might need to put a mutex around this, or some kind of queue
        except BTLEDisconnectError:
            logger(f"Failed to connect to device {mac}")
            message = '{"mac": "'+mac+'", "connect": false}'
            send_mqtt(client, message)
            return False
        trione.withDelegate(DataDelegate(client, mac))
        service = trione.getServiceByUUID(MAIN_SERVICE)
        characteristic = service.getCharacteristics(MAIN_CHARACTERISTIC)[0]
        keys = json_request.keys()
        if "status" in keys:
            logger(f"Requesting status from {mac}")
            characteristic.write(GET_STATUS)
            trione.waitForNotifications(2)
        
        if "power" in keys:
            power = SET_POWER_ON if json_request["power"] == True else SET_POWER_OFF
            logger(f"Setting power to {json_request['power']} on {mac}")
            characteristic.write(power)

        if "rgb_colour" in keys:
            r,g,b = json_request["rgb_colour"]
            if "percentage" in keys:
                scale_factor = int(json_request["percentage"])/100
            else:
                scale_factor = 1
            colour_message = SET_COLOUR_BASE
            colour_message[1] = int(r * scale_factor)
            colour_message[2] = int(g * scale_factor)
            colour_message[3] = int(b * scale_factor)
            logger(f"Setting colour to ({r},{g},{b}) on {mac}")
            characteristic.write(colour_message)
        
        if "philips_hue" in keys and "philips_saturation" in keys and "philips_brightness" in keys:
            # Turns out the colour conversion in the Node Red node was fine.  It's the lights that are the problem.
            # I'll leave this here for now though
            logger("Doing Philips Hue style colours")
            h = philips_hue_to_real_hue(json_request["philips_hue"])
            s = convert_philips_sv(json_request["philips_saturation"])
            v = convert_philips_sv(json_request["philips_brightness"])
            logger(f"H:{h}  S:{s}  V:{v}")
            r,g,b = colorsys.hsv_to_rgb(h,s,v)
            r = r * 255
            g = g * 255
            b = b * 255
            logger(f"R: {r}  G:{g}  B:{b}")
            colour_message = SET_COLOUR_BASE
            colour_message[1] = int(r)
            colour_message[2] = int(g)
            colour_message[3] = int(b)
            characteristic.write(colour_message)


        if "mode" in keys:
            # I guess you need to set a mode and a speed at the same time, and can't set one without the other?
            # Haven't done any testing on that.
            mode = json_request["mode"]
            speed = json_request["speed"]
            if mode >= 37 and mode <= 56:
                mode_message = SET_MODE
                mode_message[1] = mode
                mode_message[2] = speed
                logger(f"Setting mode {mode} speed {speed} on {mac}")
                characteristic.write(mode_message)
        
        trione.disconnect()


        
def find_devices():
    triones={}
    scanner = Scanner().withDelegate(ScanDelegate())
    devices = scanner.scan(10.0)

    for dev in devices:
        for (adtype, desc, value) in dev.getScanData():
            if desc == "Complete Local Name" and value.startswith("Triones:"):
                triones[dev.addr] = dev.rssi
    if len(triones) > 0:
        triones = dict(sorted(triones.items(), key=lambda item:item[1], reverse=True))
        print("\n\n")
        for key, value in triones.items():
            print(f"Triones device - MAC address: {key}   RSSI: {value}")
    else:
        print("None found :(")


## hwid = "78:82:a4:00:05:1e"

def server():
    if mqtt_server_ip is not None:
        mqtt_client = mqtt.Client()
        mqtt_client.on_connect = mqtt_on_connect
        mqtt_client.on_message = mqtt_message_received
        mqtt_client.connect(mqtt_server_ip, 1883, 60)
    else:
        raise NameError("No MQTT Server configured")
    
    while True:
        try:
            mqtt_client.loop_forever()
        except KeyboardInterrupt:
            logger("Exiting...")
            mqtt_client.disconnect()
            raise
        except BTLEDisconnectError:
            logger("Device has gone away..")
            send_mqtt(mqtt_client, '{"connect":"False"}')
            raise
            # I read something which suggests that these devices sometimes return data which is invalid
            # and this causes BlueZ to choke. The upshot is that if this happens when we're trying to
            # read status information no information will be returned, but then next time, two status
            # messages get returned.  Maybe we could do a wait for messages as the first thing we do...
            # might slow us down a bit, but :shrug: 

if len(sys.argv) > 1 and sys.argv[1] == "--scan":
        find_devices()

else:
    logger("Running in server mode")
    server()
