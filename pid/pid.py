#!/usr/bin/python
# Copyright 2015 Neuhold Markus and Kleinsasser Mario
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
from datetime import datetime
import urllib.request
import urllib.error
from os import path
from ws4py.client.threadedclient import WebSocketClient
from time import sleep
import json
import re
import os
import subprocess
import time
import traceback
import configparser
sys.path.insert(0, "..")

import pidglobals
from common import smsgwglobals
from common.config import SmsConfig
from common.helper import GlobalHelper
from common.filelogger import FileLogger
from helper.heartbeat import Heartbeat
from helper.wrapped import WrappedUSBModem
from helper.gammumodem import USBModem

SOCAT_PROC = {}

class PidWsClient(WebSocketClient):
    def opened(self):
        # as we are connected set the time when it was done
        self.lastprimcheck = datetime.now()

        smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                    "Opened connection to " +
                                    str(self.bind_addr))
        data = {}
        data['action'] = 'register'
        data['pidid'] = pidglobals.pidid
        data['modemlist'] = pidglobals.modemlist
        data['pidprotocol'] = pidglobals.pidprotocol

        # if modemlist is not [] register at PIS
        if data['modemlist']:
            asjson = json.dumps(data)
            smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                         "Registration data: " +
                                         asjson)
            tosend = GlobalHelper.encodeAES(asjson)
            self.send(tosend)
        else:
            # close connection to PIS
            closingreason = "Unable to connect to modem(s)"
            pidglobals.closingcode = 4000
            self.close(code=4000, reason=closingreason)
            # if >= 4000 the pid.py endlessloop will exit

    def closed(self, code, reason=None):
        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "Closed down with code: " + str(code) +
                                     " - reason: " + str(reason))
        # signal heartbeat to stop
        if pidglobals.heartbeatdaemon is not None:
            pidglobals.heartbeatdaemon.stop()
        # set the closing reason in globals
        pidglobals.closingcode = code

    def received_message(self, msg):
        plaintext = GlobalHelper.decodeAES(str(msg))

        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "Message received: " +
                                     str(plaintext))
        data = json.loads(plaintext)

        if data['action'] == "sendsms":
            tosend = Modem.sendsms(data)

            plaintext = json.dumps(tosend)
            smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                         "Message delivery status: " +
                                         str(plaintext))
            message = GlobalHelper.encodeAES(plaintext)
            # reply sms-status to PIS
            self.send(message)
            #Make sure answer will be delivered before shutdown (if will happen)
            sleep(0.1)

            # Exit PID on ERROR on sending sms
            if "ERROR" in tosend['status']:
                closingreason = "Modem ERROR while sending SMS!"

                pidglobals.closingcode = 4000
                self.close(code=4000, reason=closingreason)

            # calculate difference time to last primary PIS check
            diff = datetime.now() - self.lastprimcheck

            # only if 5 mins are passed (= 300 sec)
            if diff.seconds > 300:
                if self.check_primpid() == "reconnect":
                    # close Websocket to reconnect!
                    # fixes #25 wait a bit to let pis fetch the smsstatus first
                    time.sleep(1)

                    closingreason = "Primary PID is back! Reinit now!"
                    pidglobals.closingcode = 4001
                    self.close(code=4001, reason=closingreason)

        if data['action'] == "register":
            if data['status'] == "registered":
                # Start Heartbeat to connected PID
                hb = Heartbeat(data['modemlist'], self)
                hb.daemon = True
                hb.start()

        if data['action'] == "heartbeat":
            # connection to PIS is OK but
            # Response from WIS is NOT OK
            if data['status'] != 200:
                # close Connection to PIS and retry initialisation
                self.close()

        if data['action'] == "restartmodem":
            modem = [m for m in pidglobals.modemlist if m['modemid'] == data['modemid']]
            if modem:
                closingreason = "Modem RESTART requested!"

                pidglobals.closingcode = 4005
                self.close(code=4005, reason=closingreason)

    def check_primpid(self):
        # Do a simple URL-check and denn close Websocket connection.
        # Set the closing code to 4001 Going back to Primary
        # This will result in a reconnect on first URL.

        status = "none"
        if pidglobals.curpisurl == pidglobals.primpisurl:
            status = "nothing to do"
        else:
            request = urllib.request.Request(pidglobals.primpisurl)
            try:
                urllib.request.urlopen(request, timeout=5)
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    status = "reconnect"
                    smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                                 "PRIMPIS is back!")
            except Exception as e:
                status = "primPID not back!"
                smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                             "PRIMPIS not available - "
                                             "Error: " + str(e))

        self.lastprimcheck = datetime.now()
        return status


class Modem(object):
    """Class used to handle GAMMU modem requests
    """
    @staticmethod
    def connectmodems(modemlist):
        # init empty modemlist and connection dictionaries in pisglobals
        pidglobals.modemlist = []
        pidglobals.modemcondict = {}

        # init USBmodem connection
        # and remove modem if connection makes trouble...
        for modem in modemlist:
            Modem.connect_modem(modem)

    @staticmethod
    def connect_modem(modem):
        smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                            "Trying to init Modem: " +
                            str(modem))

        gammucfg = Modem.generate_gammu_config(modem)

        if pidglobals.wrapgammu:
            smsgwglobals.pidlogger.info("Loading WRAPPER for Gammu CLI")
            usbmodem = WrappedUSBModem(pidglobals.gammucmd,
                               gammucfg,
                               modem['gammusection'],
                               modem['pin'],
                               modem['ctryexitcode'])
        else:
            smsgwglobals.pidlogger.info("Loading Python Gammu")
            usbmodem = USBModem(gammucfg,
                        modem['gammusection'],
                        modem['pin'],
                        modem['ctryexitcode'])

        # for each modemid persist the object and the modemn pidglobals
        if usbmodem.get_status():
            modem['imsi'] = usbmodem.get_sim_imsi()
            modem['imei'] = usbmodem.get_modem_imei()
            modem['carrier'] = usbmodem.get_modem_carrier()

            carrier_cfg = {}
            if pidglobals.carriersconfig.get(modem['carrier']):
                carrier_cfg = pidglobals.carriersconfig.get(modem['carrier'])
            modem["balance_ussd"] = carrier_cfg.get('balance_ussd')
            modem["balance_regex"] = carrier_cfg.get('balance_regex')
            modem["sms_limit"] = carrier_cfg.get('sms_limit') if carrier_cfg.get('sms_limit') else 0
            modem["check_sim_status"] = carrier_cfg.get('check_sim_status')

            if modem["check_sim_status"] == False:
                modem['sim_blocked'] = "Check Skipped"
                smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                             "Skip sim_status check due to config value for: " +
                                             str(modem))
            else:
                #Check if SIM blocked by cell operator
                modem['sim_blocked'] = usbmodem.check_sim_blocked(modem)

            if "block_incoming_calls" in modem and modem["block_incoming_calls"]:
                # Block all incoming calls
                usbmodem.process_ussd("*35*0000#")

            if modem.get("balance_ussd") and modem.get("balance_regex"):
                 balance_ussd_reply = usbmodem.process_ussd(modem["balance_ussd"])
                 modem["account_balance"] = usbmodem.parse_ussd(balance_ussd_reply, modem["balance_regex"])
            else:
                modem["account_balance"] = "N/A"

            pidglobals.modemcondict[modem['modemid']] = usbmodem
            # As we can use connect_modem to reconnect - add to list only if not already exist
            if modem not in pidglobals.modemlist:
                pidglobals.modemlist.append(modem)
        else:
            smsgwglobals.pidlogger.error(pidglobals.pidid + ": " +
                                 "Unable to init USBModem: " +
                                 str(modem))

            # Kill the socat process if exist
            if SOCAT_PROC.get(modem["modemid"]):
                SOCAT_PROC[modem["modemid"]].kill()
            return None

    @staticmethod
    def generate_gammu_config(modem):
        abspath = path.abspath(path.join(path.dirname(__file__), path.pardir))
        pidglobals.abspath = abspath
        gammu_config_path = abspath + "/conf/modem_" + modem['modemid'] + ".conf"
        gammu_section = ""
        config = configparser.ConfigParser()
        if modem['gammusection'] != 0:
            gammu_section = "_" + modem['gammusection']
        gammu_section_title = "gammu" + gammu_section

        config.add_section(gammu_section_title)
        config[gammu_section_title]['port'] = Modem.get_gammu_port(modem)
        config[gammu_section_title]['name'] = modem["modemname"]
        config[gammu_section_title]['connection'] = modem["connection"] if modem.get("connection") else "at"
        config[gammu_section_title]['gammucoding'] = modem["gammuencoding"] if modem.get("gammuencoding") else "utf8"
        config[gammu_section_title]['logformat'] = modem["logformat"] if modem.get("logformat") else "textalldate"
        config[gammu_section_title]['logfile'] = modem["logfile"] if modem.get("logfile") else abspath +  "/logs/modem_" + modem["modemid"] + ".log"

        with open(gammu_config_path, 'w+') as configfile:
            config.write(configfile)
        config_dump = str({section: dict(config[section]) for section in config.sections()})
        smsgwglobals.pidlogger.debug("Gammu config for modem id: " + modem["modemid"] + " --> " + config_dump)

        return gammu_config_path

    @staticmethod
    def get_gammu_port(modem):
        gammu_port = None
        if modem.get("remote_ip") and modem.get("remote_port"):
            gammu_port = Modem.init_remote_serial_port(modem)
        else:
            try:
                gammu_port = modem["port"] if modem.get("port") else ""
            except:
                smsgwglobals.pidlogger.error(pidglobals.pidid + ": " +
                             "Unable to read port for for USBModem " + modem["modemid"])
        smsgwglobals.pidlogger.debug("Socat port for modem id: " + modem["modemid"] + " --> " + str(gammu_port))

        return gammu_port if gammu_port else ""

    @staticmethod
    def init_remote_serial_port(modem):
        # Try to use socat to init remote serial port
        device_name = "/dev/vmodem_" + modem["modemid"]
        commandLineCode = "/usr/bin/socat pty,link=" + device_name + ",waitslave tcp:" + modem["remote_ip"] + ":" + modem["remote_port"] + ",keepalive,keepidle=10,keepintvl=10"
        try:
            socat_proc = subprocess.Popen(commandLineCode,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, shell=True)

        except OSError:
            smsgwglobals.pidlogger.error(pidglobals.pidid + ": " +
                                         "Unable to init socat connection to: " + modem["remote_ip"] + ":" + modem["remote_ip"] + " for USBModem " + modem["modemid"])
            print(traceback.format_exc())

        # Socat on remote hosts can be slow, wait at least 3 seconds before trying init modem
        sleep(2)
        smsgwglobals.pidlogger.debug("Socat connection established for modem id: " + modem["modemid"] + " --> " + str(device_name))
        # Check if our socat process still running
        global SOCAT_PROC
        if socat_proc.poll() is None:
            SOCAT_PROC[modem["modemid"]] = socat_proc

        return device_name

    @staticmethod
    def sendsms(sms):
        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "Sending SMS: " + str(sms))
        status = {}
        status['smsid'] = sms['smsid']
        status['action'] = "status"

        if pidglobals.testmode:
            # special answers if testmode is true!
            if sms['content'] == "SUCCESS":
                time.sleep(5)
                status['status'] = "SUCCESS"
                status['status_code'] = 1

            elif sms['content'] == "ERROR":
                time.sleep(5)
                status['status'] = "ERROR"
                status['status_code'] = 100

            elif sms['content'] == "LONGWAIT":
                # has to be longer than maxwaitpid in smsgw.conf
                time.sleep(130)
                status['status'] = "SUCCESS"
                status['status_code'] = 1
            elif sms['content'] == "TESTMARIO_1":
                status['status'] = "SUCCESS"
                status['status_code'] = 1
            elif sms['content'] == "TESTMARIO_2":
                status['status'] = "SUCCESS"
                status['status_code'] = 1
            elif sms['content'] == "TESTMARIO_3":
                status['status'] = "SUCCESS"
                status['status_code'] = 1
            elif sms['content'] == "TESTMARIO_4":
                status['status'] = "SUCCESS"
                status['status_code'] = 1
            elif sms['content'] == "TESTMARIO_5":
                status['status'] = "SUCCESS"
                status['status_code'] = 1


        if "status" in status:
            # exit if testmode sms was sent
            return status

        # normal operation
        sentstatus = False
        status_code = None
        if sms['modemid'] in pidglobals.modemcondict:
            global SOCAT_PROC
            # If we use socat to establish connection to the remote modem, check if socket still alive
            if sms["modemid"] in SOCAT_PROC:
                modem_socat = SOCAT_PROC[sms["modemid"]]
                # If connection dead - establish it again
                if modem_socat.poll() is not None:
                    for modem in pidglobals.modemlist:
                        if modem["modemid"] == sms["modemid"]:
                            smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                                        "Socat connection DEAD to: " + modem["remote_ip"] + ":" +
                                                        modem["remote_ip"] + " for USBModem " + modem["modemid"] +
                                                        " . RE INIT connection")
                            Modem.connect_modem(modem)

            usbmodem = pidglobals.modemcondict[sms['modemid']]
            sentstatus, status_code = usbmodem.send_SMS(sms['content'],
                                           sms['targetnr'])
        if sentstatus:
            status['status'] = "SUCCESS"
            status['status_code'] = status_code
        else:
            status['status'] = "ERROR"
            status['status_code'] = status_code

        return status


class Pid(object):
    def run(self):

        # load the configuration
        abspath = path.abspath(path.join(path.dirname(__file__), path.pardir))
        pid_env_config_id = os.getenv("PID_ID")
        configfile = abspath + '/conf/smsgw_' + str(pid_env_config_id) + '.conf' if pid_env_config_id else '/conf/smsgw.conf'
        cfg = SmsConfig(configfile)
        smsgwglobals.pidlogger.debug("PID Env ID: " + str(pid_env_config_id))
        smsgwglobals.pidlogger.debug("PID Config file: " + configfile)

        pidglobals.pidid = cfg.getvalue('pidid', 'pid-dummy', 'pid')
        smsgwglobals.pidlogger.debug("PidID: " + pidglobals.pidid)

        # Gammu Debug on/off
        gammudebug = cfg.getvalue('gammudebug', 'Off', 'pid')
        if gammudebug == "On":
            pidglobals.gammudebug = True

            todir = cfg.getvalue('logdirectory', abspath + '/logs/', 'pid')
            tofile = cfg.getvalue('gammudebugfile', 'gammu.log', 'pid')
            gammudebugfile = todir + tofile
            pidglobals.gammudebugfile = gammudebugfile
            smsgwglobals.pidlogger.debug("Gammu Debug on! Will log to " +
                                         str(pidglobals.gammudebugfile))
        else:
            pidglobals.gammudebug = False

        # Wrapping Gammu or not
        wrapgammu = cfg.getvalue('wrapgammu', 'Off', 'pid')
        if wrapgammu == "On":
            pidglobals.wrapgammu = True

            gammucmd = cfg.getvalue('gammucmd', 'Blank', 'pid')
            smsgwglobals.pidlogger.debug("Gammucmd: " + str(gammucmd))

            if gammucmd == "Blank":
                option = "gammucmd - is not set!"
                cfg.errorandexit(option)

            if path.isfile(gammucmd) or path.islink(gammucmd):
                # file or link exists all fine
                pidglobals.gammucmd = gammucmd
            else:
                # exit PID here as not Modem connection will work!
                option = "gammucmd - Command given not found!"
                cfg.errorandexit(option)
        else:
            pidglobals.wrapgammu = False

        smsgwglobals.pidlogger.debug("WrapGammu: " +
                                     str(pidglobals.wrapgammu))

        testmode = cfg.getvalue('testmode', 'Off', 'pid')
        if testmode == "On":
            # set testmode - content "ERROR" "SUCCESS" and "LONGWAIT" is
            # handled in a special way now
            pidglobals.testmode = True
        else:
            pidglobals.testmode = False
        smsgwglobals.pidlogger.debug("TestMode: " +
                                     str(pidglobals.testmode))

        retrypisurl = cfg.getvalue('retrypisurl', '2', 'pid')
        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "RetryPisUrl: " + retrypisurl)

        retrywait = cfg.getvalue('retrywait', '5', 'pid')
        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "RetryWait: " + retrywait)

        modemcfg = cfg.getvalue('modemlist', '[{}]', 'pid')

        try:
            # convert json to list of dictionary entries
            modemlist = json.loads(modemcfg)
        except:
            cfg.errorandexit("modemlist - not a valid JSON structure!")

        #Get carriers config
        carriercfg = cfg.getvalue('carrierscfg', '{}', 'pid')
        try:
            # convert json to list of dictionary entries
            pidglobals.carriersconfig = json.loads(carriercfg)
        except:
            cfg.errorandexit("carrierscfg - not a valid JSON structure!")

        # check if modemcfg is set
        if 'modemid' not in modemlist[0]:
            # if len(modemlist) == 0:
            cfg.errorandexit("modemlist - not set!!!")
        else:
            # validate modem settings
            for modem in modemlist:
                try:
                    re.compile(modem['regex'])
                except:
                    cfg.errorandexit("modemlist - at " + modem['modemid'] +
                                     " - invalid regex!")

        # connect to USBModems and persist in pidglobals
        Modem.connectmodems(modemlist)

        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "ModemList: " +
                                     str(pidglobals.modemlist))
        if len(pidglobals.modemlist) == 0:
            errortext = "at any configured modem."
            cfg.errorandexit(errortext, 2)

        pisurlcfg = cfg.getvalue('pisurllist',
                                 '[{"url": "ws://127.0.0.1:7788"}]',
                                 'pid')
        # convert json to list of dictionary entries
        pisurllist = json.loads(pisurlcfg)
        smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                     "PisUrlList: " +
                                     str(pisurllist))

        # endless try to connect to configured PIS
        # error: wait for some secs, then 1 retry, then next PID  in list
        curpis = 0
        tries = 1
        while True:
            try:
                if pidglobals.closingcode:
                    raise

                baseurl = pisurllist[curpis]['url']
                pisurl = baseurl + "/ws"
                smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                            "Try " + str(tries) + ": " +
                                            "Connecting to: " +
                                            pisurl)
                # init websocket client with heartbeat, 30 is fixed in all
                # modules wis/pis/pid
                ws = PidWsClient(pisurl,
                                 protocols=['http-only', 'chat'],
                                 heartbeat_freq=30)
                ws.connect()
                # set values for primary check in Websocket connection!
                # trim ws out of ws:/.. and add http:/
                pidglobals.curpisurl = "http" + baseurl[2:]
                pidglobals.primpisurl = "http" + pisurllist[0]['url'][2:]
                ws.run_forever()
            except KeyboardInterrupt:
                ws.close()
                # leave while loop
                break
            except Exception as e:
                # do retry except there is no more modem to communicate
                if (pidglobals.closingcode is None or
                   pidglobals.closingcode < 4000):

                    # try to reconnect
                    smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                                "Got a problem will reconnect "
                                                "in " + retrywait + " seconds.")
                    smsgwglobals.pidlogger.debug(pidglobals.pidid + ": " +
                                                 "Problem is: " + str(e))
                    try:
                        time.sleep(int(retrywait))
                    except:
                        break

                    if tries < int(retrypisurl):
                        tries = tries + 1
                    else:
                        tries = 1
                        curpis = curpis + 1
                        if curpis == len(pisurllist):
                            curpis = 0
                    pidglobals.closingcode = None

                elif pidglobals.closingcode == 4001:
                    # go back to inital PID
                    # reset while parameter for pis and retries
                    smsgwglobals.pidlogger.info(pidglobals.pidid + ": " +
                                                "Going back to Prim PID")
                    curpis = 0
                    tries = 1
                    pidglobals.closingcode = None

                elif pidglobals.closingcode == 4000:
                    # leave while loop
                    # no connection to modem found!
                    smsgwglobals.pidlogger.debug(pidglobals.pidid + ": Sleep 45 seconds before shutdown..." )
                    sleep(45)
                    break
                elif pidglobals.closingcode == 4005:
                    # leave while loop
                    # pid restart requested
                    break
                elif pidglobals.closingcode == 4010:
                    # leave while loop
                    # pid lost connection to the modem. Probably sim card ejected
                    # Or HEARTBEAT failed
                    break


def main(argv):

    # in any case redirect stdout and stderr
    std = FileLogger(smsgwglobals.pidlogger)
    sys.stderr = std
    sys.stdout = std

    pid = Pid()
    pid.run()


# Called when running from command line
if __name__ == '__main__':
    main(sys.argv[1:])
