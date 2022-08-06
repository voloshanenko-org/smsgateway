#!/usr/bin/python
# Copyright 2015 Bernhard Rausch and Mario Kleinsasser
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

# import cherrypy
import collections
import urllib.request
import json
import socket
from common.helper import GlobalHelper
from application import wisglobals
from common import smsgwglobals
from common import database
from .html import Htmlpage


class ViewMain(Htmlpage):
    def __init__(self):
        Htmlpage.__init__(self)
        self.setBody()

    def setBody(self):
        str_list = []
        str_list.append('<body>\n')
        str_list.append('''
        <table>
                    <tbody>
                    <tr>
                        <td id="routingtablewisid">WisID: ''' + wisglobals.wisid + '''<br>Version: ''' + wisglobals.version + '''</td>
                        <td>Router status:</td>
                        <td id="routerstatus"></td>
                        <td>Watchdog status:</td>
                        <td id="watchdogstatus"></td>
                    </tr>
                    </tbody>
        </table>
        ''')
        str_list.append('<div class="routing">')
        str_list.append('</div>')
        str_list.append('''
        <table>
            <tbody>
                <tr>
                    <td><b>Available modems: </b></td>
                    <td><label id="available_modems"></label></td>
                </tr>
            </tbody>
        </table>                    
        ''')
        str_list.append('<hr>')
        str_list.append('''
        <table>
            <tbody>
                <tr>
                    <td><b>SMS to resend: </b></td>
                    <td><label id="unprocessed_sms"></label></td>
                </tr>
                <tr>
                    <td><b>Available SMS to send: </b></td>
                    <td><label id="available_sms"></label></td>
                </tr>
                <tr>
                    <td><b>Scheduled SMS to send: </b></td>
                    <td><label id="scheduled_sms"></label></td>
                </tr>
            </tbody>
        </table>                    
        ''')
        str_list.append('<hr>')
        str_list.append('''
        <table>
            <tbody>
                <tr>
                    <td><b>Sent SMS from ACTIVE modems: </b></td>
                    <td><label id="sent_sms_active_modems"></label></td>
                </tr>
                <tr>
                    <td><b>Total sent SMS for TODAY : </b></td>
                    <td><label id="sent_sms_total_today"></label></td>
                </tr>
            </tbody>
        </table>                    
        ''')
        str_list.append('<hr>')
        str_list.append('''
        <input type="hidden" id="mobile_prefixes" value="''' + ",".join(wisglobals.allowedmobileprefixes) + '''">
        <form id="sendsms">
        <table id="sendsms">
            <tbody>
                <tr>
                    <td>Marketing company ID:</td>
                    <td><input type="text" id="appid" name="appid"></td>
                </tr>
                <tr>
                    <td>Send to:</td>
                    <td>
                        <textarea id="mobiles" name="mobiles" rows="10" cols="20"></textarea>
                        <textarea id="mobiles_bad" name="mobiles_bad" rows="10" cols="20" disabled></textarea>
                    </td>
                </tr>
                <tr>
                    <td>Numbers of mobiles: </td>
                    <td><label id="mobiles_count">0</label></td>
                </tr>
                <tr>
                    <td>Good mobiles: </td>
                    <td><label id="mobiles_count_good">0</label></td>
                </tr>
                <tr>
                    <td>Bad mobiles: </td>
                    <td><label id="mobiles_count_bad">0</label></td>
                </tr>                                
                <tr>
                    <td>SMS:</td>
                    <td><textarea id="content" name="content" rows="10" cols="50"></textarea></>
                </tr>
                <tr>
                    <td>Numbers of symbols: </td>
                    <td><label id="content_count">0</label></td>
                </tr>
                <tr>
                    <td><button class="btn" type="button" onclick="sendSms()">Send SMS</button></td>
                </tr>
            </tbody>
        </table>
        </form>
        <hr>
        ''')
        str_list.append('<form id="getsms" action="ajax/getsms">\n')
        str_list.append('Date:<input type="text" name="date">\n')
        str_list.append('<button class="btn" type="button"' +
                        ' onclick="getSms()">Read from ' + wisglobals.wisid + '</button>&nbsp;')
        str_list.append('<button class="btn" type="button"' +
                        ' onclick="getAllSms()">Read from routing</button>')
        str_list.append('</form>')
        str_list.append('<div class="sms">\n')
        str_list.append('</div>')
        str_list.append('</body>\n')
        Htmlpage.body = ''.join(str_list)


class Ajax():

    @staticmethod
    def remove_fields(self, d):
        if not isinstance(d, (dict, list)):
            return d
        if isinstance(d, list):
            return [self.remove_fields(self, v) for v in d]
        return {k: self.remove_fields(self, v) for k, v in d.items()
            if k not in {'priority', 'sourceip', 'xforwardedfor', 'smsintime'}}

    def get_sms_stats(self):

        respdata = '{ "processed_sms": "N/A", "unprocessed_sms": "N/A" }'
        try:
            if wisglobals.sslenabled is not None and 'true' in wisglobals.sslenabled.lower():
                request = urllib.request.Request('https://' +
                                                 wisglobals.wisipaddress +
                                                 ':' +
                                                 wisglobals.wisport +
                                                 "/api/get_sms_stats")
            else:
                request = urllib.request.Request('http://' +
                                                wisglobals.wisipaddress +
                                                ':' +
                                                wisglobals.wisport +
                                                 "/api/get_sms_stats")
            request.add_header("Content-Type",
                           "application/json;charset=utf-8")

            data = GlobalHelper.encodeAES('{"get": "sms"}')
            f = urllib.request.urlopen(request, data, timeout=30)
            resp = f.read().decode('utf-8')
            respdata = GlobalHelper.decodeAES(resp)
        except urllib.error.URLError as e:
            smsgwglobals.wislogger.debug(e)
            smsgwglobals.wislogger.debug("AJAX: get_sms_stats connect error")
        except socket.timeout as e:
            smsgwglobals.wislogger.debug(e)
            smsgwglobals.wislogger.debug("AJAX: get_sms_stats socket connection timeout")
        finally:
            return respdata

    def getsms(self, all=False, date=None):
        smsgwglobals.wislogger.debug("AJAX: " + str(all))
        smsgwglobals.wislogger.debug("AJAX: " + str(date))

        str_list = []
        smsen = []

        if all is False:
            smsgwglobals.wislogger.debug("AJAX: " + str(all))
            try:
                if date is None:
                    data = GlobalHelper.encodeAES('{"get": "sms"}')
                else:
                    data = GlobalHelper.encodeAES('{"get": "sms", "date": "' + str(date) + '"}')

                if wisglobals.sslenabled is not None and 'true' in wisglobals.sslenabled.lower():
                    request = urllib.request.Request('https://' +
                                                     wisglobals.wisipaddress +
                                                     ':' +
                                                     wisglobals.wisport +
                                                     "/api/getsms")
                else:
                    request = urllib.request.Request('http://' +
                                                     wisglobals.wisipaddress +
                                                     ':' +
                                                     wisglobals.wisport +
                                                     "/api/getsms")
                request.add_header("Content-Type",
                                   "application/json;charset=utf-8")
                f = urllib.request.urlopen(request, data, timeout=30)
                resp = f.read().decode('utf-8')
                respdata = GlobalHelper.decodeAES(resp)
                raw_smsen = json.loads(respdata)
                smsen = self.remove_fields(self, raw_smsen)

            except urllib.error.URLError as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("AJAX: getsms connect error")
            except socket.timeout as e:
                smsgwglobals.wislogger.debug(e)
                smsgwglobals.wislogger.debug("AJAX: getsms socket connection timeout")
        else:
            smsgwglobals.wislogger.debug("AJAX: " + str(all))
            entries = wisglobals.rdb.read_wisurls_union()
            if len(entries) == 0:
                return "No Wis Urls"
            else:
                for entry in entries:
                    try:
                        if date is None:
                            data = GlobalHelper.encodeAES('{"get": "sms"}')
                        else:
                            data = GlobalHelper.encodeAES('{"get": "sms", "date": "' + str(date) + '"}')

                        request = urllib.request.Request(entry["wisurl"] +
                                                         "/api/getsms")
                        request.add_header("Content-Type",
                                           "application/json;charset=utf-8")
                        f = urllib.request.urlopen(request, data, timeout=30)
                        resp = f.read().decode('utf-8')
                        respdata = GlobalHelper.decodeAES(resp)
                        smsen = smsen + json.loads(respdata)

                    except urllib.error.URLError as e:
                        smsgwglobals.wislogger.debug(e)
                        smsgwglobals.wislogger.debug("AJAX: getsms connect error")
                    except socket.timeout as e:
                        smsgwglobals.wislogger.debug(e)
                        smsgwglobals.wislogger.debug("AJAX: getsms socket connection timeout")

        if smsen is None or len(smsen) == 0:
            return "No SMS in Tables found"

        th = []
        tr = []

        if len(smsen) > 0:
            od = collections.OrderedDict(sorted(smsen[0].items()))
            for k, v in od.items():
                th.append(k)

        for sms in smsen:
            od = collections.OrderedDict(sorted(sms.items()))
            td = []
            for k, v in od.items():
                td.append(v)

            tr.append(td)

        str_list.append('<table id="smsTable" class="tablesorter">\n')

        str_list.append('<thead>\n')
        str_list.append('<tr>\n')
        for h in th:
            str_list.append('<th>' + h + '</th>\n')

        str_list.append('</tr>\n')
        str_list.append('</thead>\n')

        str_list.append('<tbody>\n')
        for r in tr:
            str_list.append('<tr>\n')
            for d in r:
                str_list.append('<td>' + str(d) + '</td>\n')

            str_list.append('</tr>')

        str_list.append('</tbody>\n')
        str_list.append('</table>\n')
        return ''.join(str_list)

    def getrouting(self):
        str_list = []
        th = []
        tr = []

        rows = wisglobals.rdb.read_routing(web=True)

        if len(rows) == 0:
            return "No routes available!"

        if len(rows) > 0:
            db = database.Database()
            sim_sms_sent = db.read_sms_count_by_imsi(real_sent=True, all_imsi=True)
            for row in rows:
                for cnt in sim_sms_sent:
                    if cnt["imsi"] == row["imsi"]:
                        row["sms_sent"] = cnt["sms_count"]
                if not row.get("sms_sent"):
                    row["sms_sent"] = 0
                # To lazy now to rename field in db. So change it just for frontend output
                row["sms_scheduled"] = row["sms_count"]
                del row["sms_count"]
                del row["modemname"]

        if len(rows) > 0:
            # Add real sent sms field
            od = collections.OrderedDict(sorted(rows[0].items()))
            for k, v in od.items():
                th.append(k)

        for row in rows:
            od = collections.OrderedDict(sorted(row.items()))
            td = []
            for k, v in od.items():
                td.append(v)

            tr.append(td)

        str_list.append('<table id="routingTable" class="tablesorter">\n')

        str_list.append('<thead>\n')
        str_list.append('<tr>\n')
        for h in th:
            str_list.append('<th>' + h + '</th>\n')

        str_list.append('</tr>\n')
        str_list.append('</thead>\n')

        str_list.append('<tbody>\n')
        for r in tr:
            str_list.append('<tr>\n')
            for d in r:
                txt = None
                if "http" in str(d):
                    txt = '<a href="' + str(d) + '" target="_blank">' + str(d) + '</a>'
                else:
                    txt = str(d)
                str_list.append('<td>' + txt + '</td>\n')

            str_list.append('</tr>')

        str_list.append('</tbody>\n')
        str_list.append('</table>\n')
        return ''.join(str_list)


class Login(Htmlpage):

    def __init__(self):
        Htmlpage.__init__(self)
        self.setBody()

    def setBody(self):
        str_list = """
<body>
<table style="margin-left:auto;margin-right:auto;top:50%;">
   <tbody>
      <tr>
         <td>
            <div id="logo">
               <img width="100" height="100" src="images/smsgateway-logo-small.png">
            </div>
         </td>
         <td>
            <div id="loginform">
               <form method="post" action="checkpassword">
                  <table class="logintable">
                     <tbody>
                        <tr>
                           <td class="label">
                              Username:
                           </td>
                           <td class="form">
                              <input name="username" type="text" autofocus>
                           </td>
                        </tr>
                        <tr>
                           <td class="label">
                              Password:
                           </td>
                           <td class="form">
                              <input name="password" type="password">
                           </td>
                        </tr>
                        <tr>
                           <td class="label">
                           </td>
                           <td class="form">
                              <input value="Login" type="submit">
                           </td>
                        </tr>
                     </tbody>
                  </table>
               </form>
            </div>
         </td>
      </tr>
   </tbody>
</table>
</body>
"""
        Htmlpage.body = str_list
