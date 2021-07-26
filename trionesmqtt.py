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

debug = True # Prints messages to stdout. Once things are working set this to False

mqtt_server_ip = "mqtt" # Change to the IP address of your MQTT server.  If you need an MQTT server, look at Mosquitto.
mqtt_subscription_topic = "triones/control" # Where we will listen for messages to act on.
mqtt_reporting_topic = "triones/status" # Where we will send status messages

# Triones constants
GET_STATUS           = bytearray.fromhex("EF 01 77")
SET_POWER_ON         = bytearray.fromhex("CC 23 33")
SET_POWER_OFF        = bytearray.fromhex("CC 24 33")
SET_COLOUR_BASE      = bytearray.fromhex("56 ff ff ff 00 F0 AA")
SET_STATIC_COL_RED   = bytearray.fromhex("56 ff 00 00 00 F0 AA")
SET_STATIC_COL_GREEN = bytearray.fromhex("56 00 ff 00 00 F0 AA")
SET_STATIC_COL_BLUE  = bytearray.fromhex("56 00 00 ff 00 F0 AA")
SET_STATIC_COL_WHITE = bytearray.fromhex("56 00 00 00 FF 0F AA")
SET_MODE             = bytearray.fromhex("BB 27 7F 44")
#  MODE from MODES_DICT ---------------------^ 
#  SPEED from 01 to FF ------------------------ ^ 

MODES_DICT = {
0x25: "Seven color cross fade",
0x26: "Red gradual change",
0x27: "Green gradual change",
0x28: "Blue gradual change",
0x29: "Yellow gradual change",
0x2A: "Cyan gradual change",
0x2B: "Purple gradual change",
0x2C: "White gradual change",
0x2D: "Red, Green cross fade",
0x2E: "Red blue cross fade",
0x2F: "Green blue cross fade",
0x30: "Seven color stobe flash",
0x31: "Red strobe flash",
0x32: "Green strobe flash",
0x33: "Blue strobe flash",
0x34: "Yellow strobe flash",
0x35: "Cyan strobe flash",
0x36: "Purple strobe flash",
0x37: "White strobe flash",
0x38: "Seven color jumping change"
}

# Triones static service
## It looks like everything goes to one address and replies all come from a single address
## and the variation in services is just done in the payload.
MAIN_SERVICE         = 0xFFD5 # Service which provides the characteristics 
#MAIN_RESULT          = 0xFFD4 # Results of writes in payload from here

# Triones static characteristics
MAIN_CHARACTERISTIC   = 0xFFD9


def logger(message):
    if debug: print(message)

def send_mqtt(topic, value):
    # We should just send JSON objects, it'll make it easier
    logger("MQTT: Sending value: %s to topic %s" % (value, topic))
    mqtt_client.publish(topic, value)

class ScanDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
    def handleDiscovery(self, dev, isNewDev, isNewData):
        if isNewDev:
            logger("Discovered device %s" % (dev.addr))

class DataDelegate(DefaultDelegate):
    def __init__(self):
        DefaultDelegate.__init__(self)
    def handleNotification(self, cHandle, data):
        if cHandle == 12:
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
            # The protocol for my devices looks like 0x66,0x4,power,mode,0x20,speed,red,green,blue,white,0x3,0x99
            if data[0] == "0x66" and data[1] == "0x4" and data[11] == "0x99":
                # Probably what we're looking for
                power = True if data[2] == 0x23 else False
                mode  = int(data[3], base=16)
                speed = int(data[5], base=16)
                rgb   = [int(data[6], base=16), int(data[7], base=16), int(data[8], base=16)]
                # white = data[9] # My LEDs dont have white
                json_status = {"power":power, "rgb":rgb, "speed": speed, "mode":mode}# json_status?  Wasn't he in Fast and Furious?
                json_status = json.dumps(json_status)
                logger(json_status)
                send_mqtt(mqtt_reporting_topic, json_status)
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
        # set power
        # set mode
        # set speed
        try:
           json_request = json.loads(message.payload)
        except:
            logger("Failed to parse payload JSON.  Giving up")
            return False

        # Set up a connection to the device
        trione = Peripheral(json_request["mac"])
        trione.withDelegate(DataDelegate())
        characteristics = trione.getCharacteristics()
        service = trione.getServiceByUUID(MAIN_SERVICE)
        characteristic = service.getCharacteristics(MAIN_CHARACTERISTIC)[0]
        
        keys = json_request.keys()
        if "status" in keys:
            characteristic.write(GET_STATUS)
            trione.waitForNotifications(3)
        
        if "colour" in keys:
            r,g,b = json_request["colour"] # This needs to be a list of ints
            print("red")
            print(type(red))
            print(r)
            print("../..")
            colour_message = SET_COLOUR_BASE
            colour_message[1] = int(r)
            colour_message[2] = int(g)
            colour_message[3] = int(b)
            characteristic.write(colour_message)

        if "power" in keys:
            if json_request["power"] == True:
                characteristic.write(SET_POWER_ON)
            elif json_request["power"] == False:
                characteristic.write(SET_POWER_OFF)

        if "mode" in keys:
            # I guess you need to set a mode and a speed at the same time, and can't set one without the other?
            # Haven't done any testing on that.
            mode = json_request["mode"]
            speed = json_request["speed"]
            if mode >= 37 and mode <= 56:
                mode_message = SET_MODE
                mode_message[1] = mode
                mode_message[2] = speed      
                characteristic.write(mode_message)
        

        trione.disconnect()


        
def find_devices():
    triones={}
    scanner = Scanner().withDelegate(ScanDelegate())
    devices = scanner.scan(10.0)

    for dev in devices:
        logger("Device %s, RSSI=%sdB" % (dev.addr, dev.rssi))
        for (adtype, desc, value) in dev.getScanData():
            #print(f"desc: {desc}      value:  {value}")
            if desc == "Complete Local Name" and value.startswith("Triones:"):
                triones[dev.rssi] = dev
                logger("Found Triones device %s at address %s. RSSI %s" % (value, dev.addr, dev.rssi))

    # We should now have a dict of Triones devices, let's sort by rssi and choose the one with the best connection
    if len(triones) > 0:
        triones = triones[sorted(triones.keys(), reverse=True)[0]].addr
        logger("Using hwaddr %s" % triones)
        return triones
    else:
        return None


## hwid = "78:82:a4:00:05:1e"

if mqtt_server_ip is not None:
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_message = mqtt_message_received
    mqtt_client.connect(mqtt_server_ip, 1883, 60)
else:
    raise NameError("No MQTT Server configured")

try:
    mqtt_client.loop_forever()
except KeyboardInterrupt:
    logger("Caught ctrl-c.  Disconnecting from device.")
except BTLEDisconnectError:
    logger("Device has gone away..")