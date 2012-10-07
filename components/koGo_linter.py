# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License
# Version 1.1 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS"
# basis, WITHOUT WARRANTY OF ANY KIND, either express or implied. See the
# License for the specific language governing rights and limitations
# under the License.
#
# The Original Code is Komodo code.
#
# The Initial Developer of the Original Code is ActiveState Software Inc.
# Portions created by ActiveState Software Inc are Copyright (C) 2000-2007
# ActiveState Software Inc. All Rights Reserved.
#
# Contributor(s):
#   ActiveState Software Inc
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

# Komodo Go language service.

import os
import re
import logging
import process
import tempfile
import subprocess
import koprocessutils

from xpcom import components

from koLintResult import KoLintResult
from koLintResults import koLintResults

log = logging.getLogger("koGoLanguage")
log.setLevel(logging.INFO)


class KoGoLinter(object):
    _com_interfaces_ = [components.interfaces.koILinter]
    _reg_desc_ = "Go Linter"
    _reg_clsid_ = "{5a44b028-92e0-4159-bffd-92fd5658b322}"
    _reg_contractid_ = "@activestate.com/koLinter?language=Go;1"
    _reg_categories_ = [
        ("category-komodo-linter", 'Go'),
    ]

    def __init__(self):
        self._sysUtils = components.classes["@activestate.com/koSysUtils;1"].\
            getService(components.interfaces.koISysUtils)
        self._koDirSvc = components.classes["@activestate.com/koDirs;1"].\
            getService(components.interfaces.koIDirs)
        self._check_for_go_binary()

    def _check_for_go_binary(self):
        try:
            subprocess.call(['go'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError:
            log.error('"go" binary not found.')

    def lint(self, request):
        log.debug("Request: [%s]", request)
        encoding_name = request.encoding.python_encoding_name
        text = request.content.encode(encoding_name)
        return self.lint_with_text(request, text)

    def lint_with_text(self, request, text):
        log.debug("Request: [%s]", request)
        log.debug("Text: [%s]", text)
        if not text.strip():
            return None
        # consider adding lint preferences? maybe for compiler selection, paths, etc?

        # Save the current buffer to a temporary file.
        env = koprocessutils.getUserEnv()
        results = koLintResults()

        try:
            temp_source_file = tempfile.NamedTemporaryFile(prefix='kogo', suffix='.go', delete=False)
            temp_dest_file = tempfile.NamedTemporaryFile(delete=False)
            temp_dest_file.close()
            compilation_command = ['go', 'build', '-o', temp_dest_file.name, temp_source_file.name]

            temp_source_file.write(text)
            temp_source_file.close()

            log.info('Running ' + ' '.join(compilation_command))
            p = process.ProcessOpen(compilation_command, env=env, stdin=None)
            output_text, error_text = p.communicate()
            log.debug("Output: output:[%s], error:[%s]", output_text, error_text)
            retval = p.returncode
        except (OSError, IOError) as e:
            log.error(str(e))
        else:
            log.debug("Return value: [%d]", retval)
            result_builders = {
                1: {'input': error_text, 'func': self._build_error_result, 'start': 0},
                2: {'input': output_text, 'func': self._build_output_result, 'start': 1}
            }
            if retval in result_builders.keys():
                if result_builders[retval]['input']:
                    output = result_builders[retval]['input'].replace(temp_source_file.name, request.koDoc.baseName)

                    for line in output.splitlines()[result_builders[retval]['start']:]:
                        log.debug("Error line: [%s]", line)
                        results.addResult(result_builders[retval]['func'](text, line, request.koDoc.baseName))
                else:
                    r = KoLintResult()
                    r.severity = r.SEV_ERROR
                    r.description = 'Unexpected error'
                    results.addResult(r)
        finally:
            os.unlink(temp_source_file.name)
            try:
                os.unlink(temp_dest_file.name)
            except OSError:
                pass    # No output file was created.
        log.debug("results: [%s]" , results)
        return results

    def _build_output_result(self, text, message, filename):
        # Example message:  hello.go:9: imported and not used: "time"
        r = KoLintResult()
        r.severity = r.SEV_ERROR
        m = re.match('%s:(?P<line_no>\d+): (?P<message>.*)' % re.escape(filename), message)

        if m:
            r.description = m.group('message')
            r.lineStart = r.lineEnd = int(m.group('line_no'))
            line_contents = text.splitlines()[r.lineStart - 1].rstrip()
            r.columnStart = len(line_contents) - len(line_contents.strip()) + 1
            r.columnEnd = len(line_contents) + 1

        log.debug("Result: [%s]", r)
        return r

    def _build_error_result(self, text, message, filename):
        # Example message:  hello.go:5:5: import "appengine/datastore": cannot find package
        r = KoLintResult()
        r.severity = r.SEV_ERROR
        m = re.match('%s:(?P<line_no>\d+):(?P<col_no>\d+): (?P<message>.*)' % re.escape(filename), message)

        if m:
            r.description = m.group('message')
            r.lineStart = r.lineEnd = int(m.group('line_no'))
            r.columnStart = int(m.group('col_no'))
            r.columnEnd = len(text.splitlines()[r.lineStart - 1].rstrip())

        log.debug("Result: [%s]", r)
        return r
