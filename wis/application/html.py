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
import uuid

class Htmlpage(object):

    header = None
    footer = None
    body = None

    def __init__(self):
        self.setHeader()
        self.setFooter()

    def setBody(self):
        raise NotImplementedError

    def setHeader(self):
        str_line = []
        str_line.append('<!DOCTYPE html>')
        str_line.append('<html>')
        str_line.append('<head>')
        str_line.append('<link href="css/style.css"' +
                        'rel="stylesheet" type="text/css" />')
        str_line.append('<link rel="stylesheet" href="//code.jquery.com/ui/1.12.1/themes/base/jquery-ui.css">')
        str_line.append('<script type="text/javascript"' +
                        ' src="js/jquery-3.5.1.min.js"></script>')
        str_line.append('<script type="text/javascript"' +
                        ' src="js/jquery-ui-1.12.1.min.js"></script>')
        str_line.append('<script type="text/javascript"' +
                        ' src="ts/js/jquery.tablesorter.min.js"></script>')
        str_line.append('<link href="ts/css/theme.blue.min.css"' +
                        'rel="stylesheet" type="text/css" />')
        str_line.append('<script type="text/javascript"' +
                        ' src="ts/js/jquery.tablesorter.widgets.min.js"></script>')
        str_line.append('<script type="text/javascript"' +
                        ' src="js/main.js?random=' +
                        str(uuid.uuid1()) +
                        '"></script>')
        str_line.append('''<script type="text/javascript" src="https://cdnjs.cloudflare.com/ajax/libs/toastr.js/2.1.4/toastr.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/toastr.js/2.1.4/toastr.min.css" />''')

        str_line.append('<title>')
        str_line.append('SMS Sender')
        str_line.append('</title>')
        str_line.append('</head>')
        self.header = ''.join(str_line)

    def setFooter(self):
        str_line = []
        str_line.append('</html>')
        self.footer = ''.join(str_line)

    def view(self):
        return self.header + self.body + self.footer
