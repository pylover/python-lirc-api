''' Top-level python bindings for the lircd socket interface. '''
##
#   @file client.py
#   @author Alec Leamas
#   @brief Python bindings for a subset of the lirc_client.h interface.
#   @ingroup  python_bindings

##
#   @defgroup python_bindings   Python client bindings
#
#   This module provides python interfaces to read and send lirc data.
#   Sending is a pure python implementation, reading data uses a C
#   extension module. The API is unstable.
#
#
#   Reading raw data
#   ----------------
#
#   Reading raw data direct from the lircd socket can be done with the
#   RawConnection object using something like
#
#          import lirc.client
#          conn = lirc.client.RawConnection(socket_path)
#          while True:
#              keypress = conn.readline()
#              ... do something with keypress
#
#   The optional socket_path argument is the path to the lircd socket.
#   If not given, it defaults to (falling priority)
#       - LIRC_SOCKET_PATH environment variable.
#       - The 'output' value in lirc_options.conf
#       - A hardcoded default like /run/lirc/lircd
#   Returns a code string as documented in lircd(8)
#
#
#   Reading lircrc-translated data.
#   -------------------------------
#
#   Reading application strings translated with lircrc can be achieved using
#
#          import lirc.client
#          conn = lirc.client.LircdConnection(
#                        program, lircrc_path, socket_path)
#          while True:
#              string = conn.readline()
#              ... do domething with string
#
#   The arguments:
#       - program: Program identifier as described in ircat(1).
#       - lircrc_path: Path to lircrc  file. See
#         get_default_lircrc_path() for defaults if omitted.
#       - socket_path: See RawConnection above.
#
#
#   Sending data
#   ------------
#
#   Sending commands is about creating a command and connection. In the
#   most simple form it looks like
#
#       import lirc.client
#       conn = lirc.client.CommandConnection()
#       reply = lirc.client.ListKeysCommand(conn, remote).run()
#       if not reply.success:
#           print(parser.data[0])
#
#   The parameters depends on the actual command; there is a Command
#   defined for all known lircd commands. The returned object is a
#   Reply with various info on the processed command
#
#   To get more control lower-level primitives could be used instead of
#   run() as in this example:
#
#       while not command.parser.is_completed():
#           line = conn.readline(0.1)
#           if line:
#               command.parser.feed(line)
#           else:
#               ... handle timeout
#       if not command.parser.result == lirc.client.Result.OK:
#           print("Cannot get version string")
#       else:
#           print(command.parser.data[0])
#
#
#   Non-blocking IO
#   ---------------
#
#   Both the RawConnection, LircdConnection and CommandConnection supports:
#
#     - fileno(): Returns file number to use in select(), poll() etc.,
#       for multiplexed applications.
#     - A has_data() test which can be used in a conditional waits when
#       coordinating threads.
#
#   All methods reading data has timeout provisions.
#
#
#   Configuration
#   -------------
#
#   The file config.py ,which can be imported using <i>import lirc.config</i>
#   provides access to the paths defined when running configure.
#

#   pylint: disable=W0613

##  @addtogroup python_bindings
#   @{


import configparser
from enum import Enum
import os
import os.path
import selectors
import socket
import sys
import time

import lirc.config
import _client

_DEFAULT_PROG = "lircd-client"


def get_default_socket_path():
    '''
    Get default value for the lircd socket path, using (falling priority):

      - The environment variable LIRC_SOCKET_PATH.
      - The 'output' value in the lirc_options.conf file if value and the
        corresponding file exists.
      - A hardcoded default like /run/lirc/lircd, possibly non-existing.
    '''

    if "LIRC_SOCKET_PATH" in os.environ:
        return os.environ["LIRC_SOCKET_PATH"]
    path = lirc.config.SYSCONFDIR + "/lirc/lirc_options.conf"
    parser = configparser.SafeConfigParser()
    try:
        parser.read(path)
    except configparser.Error:
        pass
    else:
        if parser.has_section("lircd"):
            try:
                path = str(parser.get('lircd', 'output'))
                if os.path.exists(path):
                    return path
            except configparser.NoOptionError:
                pass
    return lirc.config.VARRUNDIR + "/lirc/lircd"


def get_default_lircrc_path():
    '''
    Get default path to the lircrc file according to (falling priority):
      - $XDG_CONFIG_HOME/lircrc if environment variable and file exists.
      - ~/.lircrc if it exists
      - A hardcoded default like /etc/lirc/lircrc, whether it exists or not.
    '''
    if "XDG_CONFIG_HOME" in os.environ:
        path = os.path.join(os.environ["XDG_CONFIG_HOME"], "lircrc")
        if os.path.exists(path):
            return path
    path = os.path.join(os.path.expanduser("~"), ".config" "lircrc")
    if os.path.exists(path):
        return path
    path = os.path.join(os.path.expanduser("~"), ".lircrc")
    if os.path.exists(path):
        return path
    return os.path.join(lirc.config.SYSCONFDIR, "lirc", "lircrc")


class BadPacketException(Exception):
    ''' Malformed or otherwise unparsable packet received. '''
    pass


class TimeoutException(Exception):
    ''' Timeout receiving data from remote host.'''
    pass


##
#  @defgroup receiving Classes to receive keypresses
#  @{

class RawConnection(object):
    '''
    Interface to receive raw keypresses. Parameters:
      - socket_path: lircd output socket path, see get_default_socket_path()
        for defaults.
      - prog: Program name used in lircrc decoding, see ircat(1). Could be
        omitted if only raw keypresses should be read.
    '''
    # pylint: disable=no-member

    def __init__(self, socket_path=None, prog=_DEFAULT_PROG):
        if socket_path:
            os.environ["LIRC_SOCKET_PATH"] = socket_path
        else:
            os.environ["LIRC_SOCKET_PATH"] = get_default_socket_path()
        fd = _client.lirc_init(prog)
        self._socket = socket.fromfd(fd, socket.AF_UNIX, socket.SOCK_STREAM)
        self._select = selectors.DefaultSelector()
        self._select.register(self._socket, selectors.EVENT_READ)
        self._buffer = bytearray(0)

    def readline(self, timeout=None):
        '''
        Read a code string.
          - timeout: seconds
              - if set to 0 immediately returns either a string or None.
              - if set to None (default mode) use blocking read.
          - Returns: code string as described in lircd(8) or None.
        '''
        if timeout:
            start = time.clock()
        while b'\n' not in self._buffer:
            if timeout is not None and timeout > 0:
                to = start + timeout - time.clock()
            else:
                to = timeout
            ready = self._select.select(to)
            if ready == []:
                return None
            self._buffer += self._socket.recv(4096)
        line, self._buffer = self._buffer.split(b'\n', 1)
        return line.decode("ascii", "ignore")

    def fileno(self):
        ''' Return the file nr used for IO, suitable for select() etc. '''
        return self._socket.fileno()

    def has_data(self):
        ''' Check if at least one code string is available. '''
        return b'\n' in self._buffer

    def close(self):
        ''' Close socket connection. '''
        self._socket.close()
        _client.lirc_deinit()


class LircdConnection(object):
    '''
    Interface to receive lircrc-translated keypresses. This is basically
    built on top of lirc_code2char() and as such supporting centralized
    translations using lircrc_class. See lircrcd(8).

    Parameters:
      - program: string, used to identify client. See ircat(1)
      - lircrc: lircrc file path. See get_default_lircrc_path() for defaults.
      - socket_path: lircd output socket path,  see get_default_socket_path()
       for defaults.
    '''
    # pylint: disable=no-member

    def __init__(self, program, lircrc_path=None, socket_path=None):
        if not lircrc_path:
            lircrc_path = get_default_lircrc_path()
        if not lircrc_path:
            raise FileNotFoundError("Cannot find lircrc config file.")
        self._connection = RawConnection(socket_path, program)
        self._lircrc = _client.lirc_readconfig(lircrc_path)
        self._program = program
        self._buffer = []

    def readline(self, timeout=None):
        '''
        Read translated keypress string. timeout as for
        RawConnection.readline()
        '''
        while len(self._buffer) <= 0:
            code = self._connection.readline(timeout)
            if code is None:
                return None
            strings = \
                _client.lirc_code2char(self._lircrc, self._program, code)
            if not strings or len(strings) == 0:
                continue
            self._buffer.extend(strings)
        return self._buffer.pop(0)

    def has_data(self):
        ''' Check if at least one translated string is available. '''
        return len(self._buffer) > 0

    def fileno(self):
        ''' Return the file nr used for IO, suitable for select() etc. '''
        return self._connection.fileno()

    def close(self):
        ''' Close socket connection. '''
        self._connection.close()
        _client.lirc_freeconfig(self._lircrc)

## @}

##
#  @defgroup sending Classes to send commands
#  @{


class CommandConnection(RawConnection):
    ''' Extends the parent with a send() method. '''

    def __init__(self, _socket=None):
        RawConnection.__init__(self, _socket)

    def send(self, command):
        ''' Send  single line over socket '''
        if not isinstance(command, bytearray):
            command = command.encode("ascii")
        while len(command) > 0:
            sent = self._socket.send(command)
            command = command[sent:]


class Result(Enum):
    ''' Public reply parser result, available when completed. '''
    OK = 1
    FAIL = 2
    INCOMPLETE = 3


class Command(object):
    ''' Command, parser and connection container with a run() method. '''

    def __init__(self, cmd_string, connection, timeout=0.4):
        self._conn = connection
        self._cmd_string = cmd_string
        self._parser = ReplyParser()

    def run(self, timeout=None):
        ''' Run the command and return a Reply. '''
        self._conn.send(self._cmd_string)
        while not self._parser.is_completed():
            line = self._conn.readline(timeout)
            if not line:
                raise TimeoutException("No data from lircd host.")
            self._parser.feed(line)
        return self._parser


class Reply(object):
    '''
    The status/result from parsing a command reply.  Public attributes:
       - result: Enum Result, reflects parser state.
       - success: boolean, reflects SUCCESS/ERROR.
       - data: List of lines, the command DATA payload.
       - sighup: boolean, reflects if a SIGHUP package has been received
         (these are otherwise ignored).
       - last_line: string, last input line (for error messages).
    '''
    def __init__(self):
        self.result = Result.INCOMPLETE
        self.success = None
        self.data = []
        self.sighup = False
        self.last_line = ""


class ReplyParser(Reply):
    ''' Handles the actual parsing of a command reply.  '''

    def __init__(self):
        Reply.__init__(self)
        self._state = self._State.BEGIN
        self._lines_expected = None
        self._buffer = bytearray(0)

    def is_completed(self):
        ''' Returns true if no more reply input is required. '''
        return self.result != Result.INCOMPLETE

    def feed(self, line):
        ''' Enter a line of data into parsing FSM, update state. '''

        fsm = {
            self._State.BEGIN: self._begin,
            self._State.COMMAND: self._command,
            self._State.RESULT: self._result,
            self._State.DATA: self._data,
            self._State.LINE_COUNT: self._line_count,
            self._State.LINES: self._lines,
            self._State.END: self._end,
            self._State.SIGHUP_END: self._sighup_end
        }
        line = line.strip()
        if not line:
            return
        self.last_line = line
        fsm[self._state](line)
        if self._state == self._State.DONE:
            self.result = Result.OK

##
#  @defgroup FSM Internal parser FSM
#  @{
#  pylint: disable=missing-docstring,redefined-variable-type

    class _State(Enum):
        ''' Internal FSM state. '''
        BEGIN = 1
        COMMAND = 2
        RESULT = 3
        DATA = 4
        LINE_COUNT = 5
        LINES = 6
        END = 7
        DONE = 8
        NO_DATA = 9
        SIGHUP_END = 10

    def _bad_packet_exception(self, line):
        raise BadPacketException(
            "Cannot parse: %s\nat state: %s\n" % (line, self._state))

    def _begin(self, line):
        if line == "BEGIN":
            self._state = self._State.COMMAND

    def _command(self, line):
        if not line:
            self._bad_packet_exception(line)
        self._state = self._State.RESULT

    def _result(self, line):
        if line in ["SUCCESS", "ERROR"]:
            self.success = line == "SUCCESS"
            self._state = self._State.DATA
        elif line == "SIGHUP":
            self._state = self._State.SIGHUP_END
            self.sighup = True
        else:
            self._bad_packet_exception(line)

    def _data(self, line):
        if line == "END":
            self._state = self._State.DONE
        elif line == "DATA":
            self._state = self._State.LINE_COUNT
        else:
            self._bad_packet_exception(line)

    def _line_count(self, line):
        try:
            self._lines_expected = int(line)
        except ValueError:
            self._bad_packet_exception(line)
        if self._lines_expected == 0:
            self._state = self._State.END
        else:
            self._state = self._State.LINES

    def _lines(self, line):
        self.data.append(line)
        if len(self.data) >= self._lines_expected:
            self._state = self._State.END

    def _end(self, line):
        if line != "END":
            self._bad_packet_exception(line)
        self._state = self._State.DONE

    def _sighup_end(self, line):
        if line == "END":
            self._state = self._State.BEGIN
        else:
            self._bad_packet_exception(line)

## @}
#  FSM
#  pylint: enable=missing-docstring,redefined-variable-type

##  @}

#   sending

##
#  @defgroup Commands Commands to control lircd
#  @{


class SimulateCommand(Command):
    ''' Simulate a button press, see SIMULATE in lircd(8) manpage. '''
    # pylint: disable=too-many-arguments

    def __init__(self, connection, remote, key, repeat=1, keycode=0):
        cmd = "SIMULATE %016d %02d %s %s\n" % \
            (int(keycode), int(repeat), key, remote)
        Command.__init__(self, cmd, connection)


class ListRemotesCommand(Command):
    ''' List available remotes, see LIST in lircd(8) manpage. '''

    def __init__(self, connection):
        Command.__init__(self, "LIST\n", connection)


class ListKeysCommand(Command):
    ''' List available keys in given remote, see LIST in lircd(8) manpage. '''

    def __init__(self, connection, remote):
        Command.__init__(self, "LIST %s\n" % remote, connection)


class StartRepeatCommand(Command):
    ''' Start repeating given key, see SEND_START in lircd(8) manpage. '''

    def __init__(self, connection, remote, key):
        cmd = "SEND_START %s %s\n" % (remote, key)
        Command.__init__(self, cmd, connection)


class StopRepeatCommand(Command):
    ''' Stop repeating given key, see SEND_STOP in lircd(8) manpage. '''

    def __init__(self, connection, remote, key):
        cmd = "SEND_STOP %s %s\n" % (remote, key)
        Command.__init__(self, cmd, connection)


class SendCommand(Command):
    ''' Send given key, see SEND_ONCE in lircd(8) manpage. '''

    def __init__(self, connection, remote, keys):
        if not len(keys):
            print("No keys given")
            sys.exit(1)
        cmd = "SEND_ONCE %s %s\n" % (remote, " ".join(keys))
        Command.__init__(self, cmd, connection)


class SetTransmittersCommand(Command):
    ''' Set transmitters to use, see SET_TRANSMITTERS in lircd(8) manpage. '''

    def __init__(self, connection, transmitters):
        if isinstance(transmitters, list):
            mask = 0
            for transmitter in transmitters:
                mask |= (1 << (int(transmitter) - 1))
        else:
            mask = transmitters
        cmd = "SET_TRANSMITTERS %d\n" % mask
        Command.__init__(self, cmd, connection)


class VersionCommand(Command):
    ''' Get lircd version, see VERSION in lircd(8) manpage. '''

    def __init__(self, connection):
        Command.__init__(self, "VERSION\n", connection)


class DrvOptionCommand(Command):
    ''' Set a driver option value, see DRV_OPTION in lircd(8) manpage. '''

    def __init__(self, connection, option, value):
        cmd = "DRV_OPTION %s %s\n" % (option, value)
        Command.__init__(self, cmd, connection)


class SetLogCommand(Command):
    '''
    Start/stop logging lircd output , see SET_INPUTLOG in lircd(8)
    manpage.
    '''

    def __init__(self, connection, logfile=None):
        cmd = "SET_INPUTLOG"
        if logfile:
            cmd += " " + logfile
        cmd += "\n"
        Command.__init__(self, cmd, connection)


##  @}
#   commands

##  @}
#   python-bindings
