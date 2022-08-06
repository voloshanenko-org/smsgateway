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

import cherrypy
import socket
import json
import os
import sys
sys.path.insert(0, "..")
import re
import uuid
from queue import Queue
import urllib.request
import threading
from datetime import datetime

from common import error
from common.config import SmsConfig
from common import smsgwglobals
from common.helper import GlobalHelper
from common.database import Database
from common.filelogger import FileLogger
from application.helper import Helper
from application import root
from application.smstransfer import Smstransfer
from application.watchdog import Watchdog, Watchdog_Scheduler
from application.router import Router
from application.stats import Logstash
from application import wisglobals
from application import apperror
from application import routingdb

from ldap3 import Server, Connection, ALL

import ssl

SMS_QUEUE = None

# disable ssl check for unverified requests
# https://www.python.org/dev/peps/pep-0476/
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    # Legacy Python that doesn't verify HTTPS certificates by default
    pass
else:
    # Handle target environment that doesn't support HTTPS verification
    ssl._create_default_https_context = _create_unverified_https_context


class Root(object):
    def triggerwatchdog(self):
        smsgwglobals.wislogger.debug("TRIGGER WATCHDOG")

        smsgwglobals.wislogger.debug("TRIGGER WATCHDOG ROUTER")
        if wisglobals.routerThread is None:
            smsgwglobals.wislogger.debug("Router died! Restarting it!")
            rt = Router(2, "Router")
            rt.daemon = True
            rt.start()
        elif not wisglobals.routerThread.isAlive():
            smsgwglobals.wislogger.debug("Router died! Restarting it!")
            rt = Router(2, "Router")
            rt.daemon = True
            rt.start()
        else:
            pass

        if wisglobals.watchdogThread is None:
            smsgwglobals.wislogger.debug("Watchdog died! Restarting it!")
            wd = Watchdog(1, "Watchdog", SMS_QUEUE)
            wd.daemon = True
            wd.start()
        elif not wisglobals.watchdogThread.isAlive():
            smsgwglobals.wislogger.debug("Watchdog died! Restarting it!")
            wd = Watchdog(1, "Watchdog", SMS_QUEUE)
            wd.daemon = True
            wd.start()
        else:
            smsgwglobals.wislogger.debug("TRIGGER WATCHDOG")
            smsgwglobals.wislogger.debug("Wakup watchdog")
            wisglobals.watchdogThreadNotify.set()

    @cherrypy.expose
    def viewmain(self):
        return root.ViewMain().view()

    @cherrypy.expose
    def index(self):
        if 'logon' not in cherrypy.session:
            return root.Login().view()
        elif cherrypy.session['logon'] is True:
            raise cherrypy.HTTPRedirect("/main")

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def checkpassword(self, **params):
        username = cherrypy.request.params.get('username').lower()
        password = cherrypy.request.params.get('password')

        # check if password is empty
        if not password:
            smsgwglobals.wislogger.debug("FRONT: No password on login")
            raise cherrypy.HTTPRedirect("/")

        # check if username is valid
        if not username:
            smsgwglobals.wislogger.debug("FRONT: No username on login")
            raise cherrypy.HTTPRedirect("/")

        if len(username) > wisglobals.validusernamelength:
            smsgwglobals.wislogger.debug("FRONT: Username to long on login")
            raise cherrypy.HTTPRedirect("/")

        if (re.compile(wisglobals.validusernameregex).findall(username)):
            smsgwglobals.wislogger.debug("FRONT: Username is not valid login")
            raise cherrypy.HTTPRedirect("/")

        if 'root' in username:
            smsgwglobals.wislogger.debug("FRONT: ROOT Login " + username)
            try:
                if Helper.checkpassword(username, password) is True:
                    cherrypy.session['logon'] = True
                    raise cherrypy.HTTPRedirect("/main")
                else:
                    raise cherrypy.HTTPRedirect("/")
            except error.UserNotFoundError:
                raise cherrypy.HTTPRedirect("/")
        else:
            try:
                smsgwglobals.wislogger.debug("FRONT: Ldap Login " + username)
                if wisglobals.ldapenabled is None or 'true' not in wisglobals.ldapenabled.lower():
                    smsgwglobals.wislogger.debug("FRONT: Ldap Login disabled " + username)
                    raise cherrypy.HTTPRedirect("/")

                smsgwglobals.wislogger.debug("FRONT: Ldap Login " + username)
                smsgwglobals.wislogger.debug("FRONT: Ldap Users " + str(wisglobals.ldapusers))
                if username not in wisglobals.ldapusers:
                    smsgwglobals.wislogger.debug("FRONT: Ldap username not in ldapusers")
                    raise cherrypy.HTTPRedirect("/")

                smsgwglobals.wislogger.debug("FRONT: Ldap Server " + wisglobals.ldapserver)
                s = Server(wisglobals.ldapserver, get_info=ALL)
                userdn = 'cn=' + username + ',' + wisglobals.ldapbasedn
                c = Connection(s, user=userdn, password=password)

                if c.bind():
                    smsgwglobals.wislogger.debug("FRONT: Ldap login successful " + username)
                    cherrypy.session['logon'] = True
                    raise cherrypy.HTTPRedirect("//main")
                else:
                    raise cherrypy.HTTPRedirect("/")
            except error.UserNotFoundError:
                raise cherrypy.HTTPRedirect("/")

    @cherrypy.expose
    def main(self, **params):
        if 'logon' not in cherrypy.session:
            return root.Login().view()
        elif cherrypy.session['logon'] is True:
            return root.ViewMain().view()

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST', 'GET'])
    def ajax(self, arg, **params):
        if 'logon' not in cherrypy.session:
            # raise cherrypy.HTTPRedirect("/")
            return '<div id="sessiontimeout"></div>'

        smsgwglobals.wislogger.debug("AJAX: request with %s and %s ", str(arg), str(params))

        if "status" in arg:
            smsgwglobals.wislogger.debug("AJAX: called with %s and %s", str(arg), str(params))
            status = {}
            cherrypy.response.status = 200
            if wisglobals.routerThread is None:
                status['router'] = 'noobject'

            if wisglobals.routerThread.isAlive():
                status['router'] = 'alive'
            else:
                status['router'] = 'dead'

            if wisglobals.watchdogThread is None:
                status['watchdog'] = 'noobject'

            if wisglobals.watchdogThread.isAlive():
                status['watchdog'] = 'alive'
            else:
                status['watchdog'] = 'dead'

            data = json.dumps(status)
            return data

        if "getrouting" in arg:
            smsgwglobals.wislogger.debug("AJAX: called with %s and %s", str(arg), str(params))
            return root.Ajax().getrouting()

        if "get_sms_stats" in arg:
            smsgwglobals.wislogger.debug("AJAX: called with %s and %s", str(arg), str(params))
            return root.Ajax().get_sms_stats()

        if "getsms" in arg:
            smsgwglobals.wislogger.debug("AJAX: called with %s and %s", str(arg), str(params))
            if "all" in params:
                allflag = params['all']
                smsgwglobals.wislogger.debug("AJAX: all %s", str(allflag))
            else:
                allflag = False

            if "date" in params:
                date = params['date']
            else:
                date = None

            if allflag is not None and "true" in allflag:
                return root.Ajax().getsms(all=True, date=date)
            else:
                return root.Ajax().getsms(date=date)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    def api(self, arg, **params):
        cl = cherrypy.request.headers['Content-Length']
        rawbody = cherrypy.request.body.read(int(cl))
        smsgwglobals.wislogger.debug(rawbody)
        plaintext = GlobalHelper.decodeAES(rawbody)
        smsgwglobals.wislogger.debug(plaintext)
        data = json.loads(plaintext)

        if arg == "watchdog":
            if data["run"] == "True":
                self.triggerwatchdog()
            else:
                cherrypy.response.status = 400

        if arg == "heartbeat":
            if "routingid" in data:
                smsgwglobals.wislogger.debug(data["routingid"])
                try:
                    count = wisglobals.rdb.raise_heartbeat(data["routingid"])
                    if count == 0:
                        smsgwglobals.wislogger.debug("COUNT: " + str(count))
                        cherrypy.response.status = 400
                except error.DatabaseError:
                    cherrypy.response.status = 400
            else:
                cherrypy.response.status = 400

        if arg == "receiverouting":
            try:
                wisglobals.rdb.merge_routing(data)
            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)

        if arg == "requestrouting":
            if data["get"] != "peers":
                cherrypy.response.status = 400
                return

            smsgwglobals.wislogger.debug("Sending routing table to you")
            try:
                erg = wisglobals.rdb.read_routing()
                jerg = json.dumps(erg)
                data = GlobalHelper.encodeAES(jerg)
                return data

            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)

        if arg == "managemodem":
            try:
                if data["action"] == "register":
                    smsgwglobals.wislogger.debug("managemodem register")
                    smsgwglobals.wislogger.debug(wisglobals.wisid)

                    # add wisid to data object
                    data["wisid"] = wisglobals.wisid

                    # store date in routing table
                    wisglobals.rdb.write_routing(data)

                    # call receiverouting to distribute routing
                    Helper.receiverouting()

                elif data["action"] == "unregister":
                    smsgwglobals.wislogger.debug("managemodem unregister")
                    routingid = data["routingid"]
                    wisglobals.rdb.change_obsolete(routingid, 14)
                    if routingid in wisglobals.watchdogRouteThread:
                        wisglobals.watchdogRouteThread[routingid].terminate()
                        wisglobals.watchdogRouteThread.pop(routingid)
                        wisglobals.watchdogRouteThreadNotify.pop(routingid)
                        wisglobals.watchdogRouteThreadQueue.pop(routingid)

                    Helper.receiverouting()
                else:
                    return False
            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)

        if arg == "deligatesms":
            if "sms" in data:
                smsgwglobals.wislogger.debug(data["sms"])
                try:
                    sms = Smstransfer(**data["sms"])
                    sms.smsdict["status"] = -1
                    sms.writetodb()
                    self.triggerwatchdog()
                except error.DatabaseError:
                    cherrypy.response.status = 400
            else:
                cherrypy.response.status = 400

        if arg == "router":
            if data["action"] == "status":
                smsgwglobals.wislogger.debug("API: " + data["action"])
                if wisglobals.routerThread is None:
                    cherrypy.response.status = 200
                    data = GlobalHelper.encodeAES('{"ROUTER":"noobject"}')
                    return data

                if wisglobals.routerThread.isAlive():
                    cherrypy.response.status = 200
                    data = GlobalHelper.encodeAES('{"ROUTER":"alive"}')
                    return data
                else:
                    cherrypy.response.status = 200
                    data = GlobalHelper.encodeAES('{"ROUTER":"dead"}')
                    return data

        if arg == "getsms":
            if data["get"] != "sms":
                cherrypy.response.status = 400
                return

            if "date" in data:
                date = data["date"]
                smsgwglobals.wislogger.debug("API: " + date)
            else:
                date = None

            smsgwglobals.wislogger.debug("Sending SMS Table")
            smsgwglobals.wislogger.debug("Sending SMS Table date: " + str(date))
            try:
                db = Database()
                erg = db.read_sms_date(date=date)
                jerg = json.dumps(erg)
                data = GlobalHelper.encodeAES(jerg)
                return data

            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)

        if arg == "get_sms_stats":
            if data["get"] != "sms":
                cherrypy.response.status = 400
                return
            try:
                db = Database()
                erg = db.read_sms_stats()
                jerg = json.dumps(erg)
                data = GlobalHelper.encodeAES(jerg)
                return data

            except error.DatabaseError as e:
                smsgwglobals.wislogger.debug(e.message)

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.accept(media='application/json')
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def restartmodem(self, **params):
        json_data = cherrypy.request.json

        # all parameters to lower case
        json_data = dict([(x[0].lower(), x[1]) for x in json_data.items()])

        # check if parameters are given
        resp = {}
        if not json_data.get("imsi"):
            cherrypy.response.status = 422
            resp["message"] = ":imsi attribute not set"
            return resp

        imsi = json_data.get("imsi")
        route = [ r for r in wisglobals.rdb.read_routing() if r["imsi"] == imsi and r["obsolete"] < 1]

        if route:
            modemid = route[0]["modemid"]
            db = Database()
            sms_in_progress = db.read_sms(status=0, modemid=modemid)
            if sms_in_progress:
                cherrypy.response.status = 409
                resp["message"] = ":imsi '" + imsi + "'(Modem #" + modemid + ") BUSY now sending SMS!"
                return resp
            else:
                try:
                    jdata = json.dumps({ "modemid": modemid})
                    data = GlobalHelper.encodeAES(jdata)
                    request = urllib.request.Request(route[0]["pisurl"] + "/restartmodem")
                    request.add_header("Content-Type",
                                        "application/json;charset=utf-8")
                    smsgwglobals.wislogger.debug("WIS: restartmodem '" + route[0]["modemid"] +"' VIA " +
                                                 route[0]["pisurl"] +
                                                 "/restartmodem")

                    f = urllib.request.urlopen(request, data, timeout=10)
                    smsgwglobals.wislogger.debug("WIS modem restart (Modem #" + modemid + ") send to PIS returncode:" + str(f.getcode()))
                    # if all is OK set the sms status to SENT
                    if f.getcode() == 200:
                        cherrypy.response.status = 200
                        resp["message"] = ":imsi '" + imsi + "'(Modem #" + modemid + ") BUSY now sending SMS!"
                        return resp
                except urllib.error.URLError as e:
                    cherrypy.response.status = 500
                    resp["message"] = ":imsi '" + imsi + "'(Modem #" + modemid + ") can't be restarted now!"
                    return resp
                except socket.timeout as e:
                    cherrypy.response.status = 500
                    resp["message"] = ":imsi '" + imsi + "'(Modem #" + modemid + ") can't be restarted now!"
                    return resp

        else:
            cherrypy.response.status = 404
            resp["message"] = ":imsi '" + imsi + "' not found inside any active modem!"
            return resp

    @cherrypy.expose
    @cherrypy.tools.allow(methods=['POST'])
    @cherrypy.tools.accept(media='application/json')
    @cherrypy.tools.json_out()
    @cherrypy.tools.json_in()
    def sendsms(self, **params):
        json_data = cherrypy.request.json

        # all parameters to lower case
        json_data = dict([(x[0].lower(), x[1]) for x in json_data.items()])

        # check if parameters are given
        resp = {}
        if not json_data.get("content"):
            cherrypy.response.status = 422
            resp["message"] = ":content attribute not set"
            self.triggerwatchdog()
            return resp
        if not json_data.get("mobile"):
            cherrypy.response.status = 422
            resp["message"] = ":mobile attribute not set"
            self.triggerwatchdog()
            return resp

        mobile_array = isinstance(json_data.get('mobile'), list)
        if not mobile_array:
            mobile_numbers = [json_data.get('mobile')]
        else:
            mobile_numbers = json_data.get('mobile')

        initial_count = len(mobile_numbers)
        mobile_numbers_to_send = []

        invalid_messages = []
        for targetnr in mobile_numbers:
            digits_regex = '^\d{12}$'
            digits_match = re.search(digits_regex, targetnr)
            if digits_match is None:
                msg = ":mobile number '" + targetnr + "' not valid. Should be 12 digits!"
                invalid_messages.append(msg)
            else:
                allowed_prefix = False
                for prefix in wisglobals.allowedmobileprefixes:
                    prefix_regex = '^' + prefix + r'\d{7}$'
                    prefix_match = re.search(prefix_regex, targetnr)
                    if prefix_match is not None:
                        allowed_prefix = True
                if not allowed_prefix:
                    msg = ":mobile number '" + targetnr + "' not valid. Allowed prefixes: " + str(wisglobals.allowedmobileprefixes)
                    invalid_messages.append(msg)
                else:
                    mobile_numbers_to_send.append(targetnr)

        # All our numbers invalid
        if initial_count == len(invalid_messages):
            cherrypy.response.status = 422
            resp["message"] = ", ".join(invalid_messages)
            self.triggerwatchdog()
            return resp

        priority = 1
        if 'priority' in cherrypy.request.params:
            priority = int(json.get('priority'))

        sourceip=cherrypy.request.headers.get('Remote-Addr'),
        xforwardedfor=cherrypy.request.headers.get('X-Forwarded-For'),
        thread_sender = threading.Thread(target=self.thread_sender, args=[mobile_numbers_to_send, json_data, priority, sourceip, xforwardedfor])
        thread_sender.start()

        cherrypy.response.status = 200
        final_count = len(mobile_numbers_to_send)
        success_message = ":" + str(final_count) + " sms added to the queue successfully"
        if invalid_messages:
            invalid_msg = ", ".join(invalid_messages)
            success_message += ", " + invalid_msg
        resp["message"] = success_message
        self.triggerwatchdog()

        return resp

    def thread_sender(self, mobile_numbers_to_send, json_data, priority, sourceip, xforwardedfor):
        if isinstance(sourceip, tuple):
            sourceip = str(sourceip[0])
        if isinstance(xforwardedfor, tuple):
            xforwardedfor = str(xforwardedfor[0])

        for targetnr in mobile_numbers_to_send:
            # this is used for parameter extraction
            # Create sms data object and make sure that it has a smsid
            sms_uuid = str(uuid.uuid1())
            sms = Smstransfer(content=json_data.get('content'),
                              targetnr=targetnr,
                              priority=priority,
                              appid=json_data.get('appid'),
                              sourceip=sourceip,
                              xforwardedfor=xforwardedfor,
                              smsid=sms_uuid)

            smsgwglobals.wislogger.debug("WIS: sendsms interface " + str(sms.getjson()))

            # process sms to insert it into database
            try:
                Helper.processsms(sms)
                smsid = sms.smstransfer["sms"]["smsid"]
                SMS_QUEUE.put(smsid)
            except apperror.NoRoutesFoundError:
                self.triggerwatchdog()
                pass
            except apperror.NotAllowedTimeFrame:
                self.triggerwatchdog()
                pass


class Wisserver(object):

    def run(self):
        # load the configuration
        # Create default root user
        db = Database()

        abspath = os.path.abspath(os.path.join(os.path.dirname(__file__), os.path.pardir))

        # store the abspath in globals for easier handling
        wisglobals.smsgatewayabspath = abspath

        configfile = abspath + '/conf/smsgw.conf'
        cfg = SmsConfig(configfile)

        readme = open(abspath + '/README.md', 'r')
        readmecontent = readme.read()
        version = re.compile(r"(?<=## Version)(.*v.\..*)", re.S).findall(readmecontent)
        wisglobals.version = version[0].strip('\n') if version else "version not specified"

        smsgwglobals.wislogger.debug("WIS: Version: " + str(wisglobals.version))

        wisglobals.wisid = cfg.getvalue('wisid', 'nowisid', 'wis')
        wisglobals.wisipaddress = cfg.getvalue('ipaddress', '127.0.0.1', 'wis')
        wisglobals.wisport = cfg.getvalue('port', '7777', 'wis')
        wisglobals.cleanupseconds = cfg.getvalue('cleanupseconds', '315569520', 'wis')

        wisglobals.validusernameregex = cfg.getvalue('validusernameregex', '([^a-zA-Z0-9])', 'wis')
        wisglobals.validusernamelength = cfg.getvalue('validusernamelength', 30, 'wis')

        wisglobals.ldapserver = cfg.getvalue('ldapserver', None, 'wis')
        wisglobals.ldapbasedn = cfg.getvalue('ldapbasedn', None, 'wis')
        wisglobals.ldapenabled = cfg.getvalue('ldapenabled', None, 'wis')
        ldapusers = cfg.getvalue('ldapusers', '[]', 'wis')
        wisglobals.ldapusers = json.loads(ldapusers)
        wisglobals.ldapusers = [item.lower() for item in wisglobals.ldapusers]
        smsgwglobals.wislogger.debug("WIS:" + str(wisglobals.ldapusers))

        wis_env_root_password_hash = os.getenv("ROOT_PASSWORD_HASH")

        password_from_config = cfg.getvalue('password', '20778ba41791cdc8ac54b4f1dab8cf7602a81f256cbeb9e782263e8bb00e01794d47651351e5873f9ac82868ede75aa6719160e624f02bba4df1f94324025058', 'wis')
        password = wis_env_root_password_hash if wis_env_root_password_hash else password_from_config

        salt = cfg.getvalue('salt', 'changeme', 'wis')

        # write the default user on startup
        db.write_users('root', password, salt)

        # read pissendtimeout
        wisglobals.pissendtimeout = int(cfg.getvalue('pissendtimeout', '20', 'wis'))

        # Read allowed mobile prefixes to process
        mobile_prefixes_raw = cfg.getvalue('allowedmobileprefixes', '.*', 'wis').split(",")
        wisglobals.allowedmobileprefixes = set(sorted([ d.strip() for d in mobile_prefixes_raw if d != ""]))

        # Read allowed timeframe for sending start/finish time
        wisglobals.allowedstarttime = cfg.getvalue('allowedstarttime', '01:00', 'wis')
        wisglobals.allowedfinishtime = cfg.getvalue('allowedfinishtime', '23:30', 'wis')

        # Read resend scheduler start/finish timeframe
        wisglobals.resendstarttime = cfg.getvalue('resendstarttime', '09:00', 'wis')
        wisglobals.resendfinishtime = cfg.getvalue('resendfinishtime', '18:00', 'wis')
        wisglobals.resendinterval = int(cfg.getvalue('resendinterval', '30', 'wis'))

        # Set own start time to use in resend flow
        wisglobals.scriptstarttime = datetime.utcnow()

        # check if ssl is enabled
        wisglobals.sslenabled = cfg.getvalue('sslenabled', None, 'wis')
        wisglobals.sslcertificate = cfg.getvalue('sslcertificate', None, 'wis')
        wisglobals.sslprivatekey = cfg.getvalue('sslprivatekey', None, 'wis')
        wisglobals.sslcertificatechain = cfg.getvalue('sslcertificatechain', None, 'wis')

        smsgwglobals.wislogger.debug("WIS: SSL " + str(wisglobals.sslenabled))

        if wisglobals.sslenabled is not None and 'true' in wisglobals.sslenabled.lower():
            smsgwglobals.wislogger.debug("WIS: STARTING SSL")
            cherrypy.config.update({'server.ssl_module':
                                    'builtin'})
            cherrypy.config.update({'server.ssl_certificate':
                                    wisglobals.sslcertificate})
            cherrypy.config.update({'server.ssl_private_key':
                                    wisglobals.sslprivatekey})
            if wisglobals.sslcertificatechain is not None:
                cherrypy.config.update({'server.ssl_certificate_chain':
                                        wisglobals.sslcertificatechain})

        cherrypy.config.update({'server.socket_host':
                                wisglobals.wisipaddress})
        cherrypy.config.update({'server.socket_port':
                                int(wisglobals.wisport)})
        cherrypy.tree.mount(StatsLogstash(), '/api/stats/logstash', {'/': {'request.dispatch': cherrypy.dispatch.MethodDispatcher()}})

        # Start scheduler for sms resending and other maintenance operations
        Watchdog_Scheduler()

        cherrypy.quickstart(Root(), '/',
                            'wis-web.conf')


class StatsLogstash:
    exposed = True

    def POST(self):
        smsgwglobals.wislogger.debug("WIS: STATS API call LOGSTASH")
        cl = cherrypy.request.headers['Content-Length']
        rawbody = cherrypy.request.body.read(int(cl))
        rawbody = rawbody.decode("utf-8")

        if not rawbody:
            return "error"

        body = ""
        retval = {}
        retval['all'] = "error"
        retval['pro'] = "error"
        try:
            body = json.loads(rawbody)
        except:
            smsgwglobals.wislogger.debug("WIS: STATS API LOGSTASH json loads error")
            cherrypy.response.status = 400
            return "No valid json given"

        if 'token' not in body:
            cherrypy.response.status = 400
            return "No token given"
        try:
            reporter = Logstash(body['token'])
            retval = reporter.report()
        except RuntimeError as e:
            smsgwglobals.wislogger.debug("WIS: STATS exception " + str(e))

        return '{"all" : ' + str(retval['all']) + ', "pro" : ' + str(retval['pro']) + '}'


def main(argv):

    # in any case redirect stdout and stderr
    std = FileLogger(smsgwglobals.wislogger)
    sys.stderr = std
    sys.stdout = std

    # Create the routingdb
    wisglobals.rdb = routingdb.Database()
    wisglobals.rdb.create_table_routing()
    wisglobals.rdb.read_routing()

    # Create message queue
    global SMS_QUEUE
    SMS_QUEUE = Queue()

    # Start the router
    rt = Router(2, "Router")
    rt.daemon = True
    rt.start()

    # Start the watchdog
    wd = Watchdog(1, "Watchdog", SMS_QUEUE)
    wd.daemon = True
    wd.start()

    # After startup let the watchdog run to clean database
    wisglobals.watchdogThreadNotify.set()

    wisserver = Wisserver()
    wisserver.run()

# Called when running from command line
if __name__ == '__main__':
    main(sys.argv[1:])
