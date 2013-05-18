# MilterSysUser
#
# This is a milter for postfix/sendmail that figures out which local user
# is sending an e-mail through SMTP, and adds a mail header containing
# that information.
#
# Author: Stefan Mensink
# Copyright: Basemotive VOF / Stefan Mensink
# License: MIT
#
# Copyright (c) 2013 Basemotive VOF / Stefan Mensink
# 
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
# 
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

# Settings
socketname = '/var/spool/postfix/private/milter.sock'
timeout = 600
run_as_user = 'postfix' # 'username' or None if you don't want to (or can't) do setuid/setgid
blocked_mailusers = [] # for example ["sam", "dean"]

# Script starts here...

import Milter
import StringIO
import time
import email
import sys
import subprocess
import ipaddr
import os
from pwd import getpwnam  
from socket import AF_INET, AF_INET6
from Milter.utils import parse_addr
if True:
  from multiprocessing import Process as Thread, Queue
else:
  from threading import Thread
  from Queue import Queue

logq = Queue(maxsize=4)

class MilterSysUser(Milter.Base):

  def __init__(self):  # A new instance with each new connection.
    self.id = Milter.uniqueID()  # Integer incremented with each call.

  @Milter.noreply
  def connect(self, IPname, family, hostaddr):
    protocol = '4' if family == AF_INET else '6'
    self.log("Connection from %s:%s (IPv%s)" % (hostaddr[0], hostaddr[1], protocol))
    self.process_info = self.get_process_info(protocol, hostaddr[0], hostaddr[1])
    if not self.process_info is None:
      self.log("Found userinfo: user=%s program=%s" % (self.process_info[0], self.process_info[1]))
    return Milter.CONTINUE

  def eom(self):
    if not self.process_info is None:
      self.addheader("X-Sender-Process-Info", "user=%s program=%s" % (self.process_info[0], self.process_info[1]))
      # block mail from users we don't want sending mail
      if self.process_info[0] in blocked_mailusers:
        self.log("Actively blocking mail from user %s" % (self.process_info[0]))
        self.setreply("550", "5.7.1", "User %s is blocked from sending mail" % (self.process_info[0]))
        return Milter.REJECT
    return Milter.CONTINUE

  def log(self,*msg):
    logq.put((msg,self.id,time.time()))

  def get_process_info(self, protocol, hostaddr, port):
    # Port 0 means it's a non-smtp connection (sendmail command)
    if port == "0": return None
    # Make sure the IP-address is link-local (postfix shouldn't accept mails on any other interface without auth)
    if hostaddr != "::1" and not ipaddr.IPAddress(hostaddr) in ipaddr.IPNetwork('127.0.0.0/8'): return None
    # Enclose IPv6 addresses in square brackets
    if ":" in hostaddr: hostaddr = "["+hostaddr+"]"
    # Check with lsof
    search_filter = "%stcp@%s:%s" % (protocol, hostaddr, port)
    try: output = subprocess.check_output(["sudo", "lsof", "-a", "-F", "cL", "-i", search_filter, "-u", "^postfix"])
    except subprocess.CalledProcessError as e: output = ""
    output_split = output.split("\n")
    if len(output_split) >= 3: return [output_split[2][1:], output_split[1][1:]]
    self.log("User process not found, protocol=%s hostaddr=%s port=%s" % (protocol, hostaddr, port))
    return None

def background():
  while True:
    t = logq.get()
    if not t: break
    msg,id,ts = t
    print "%s [%d]" % (time.strftime('%Y%b%d %H:%M:%S',time.localtime(ts)),id),
    # 2005Oct13 02:34:11 [1] msg1 msg2 msg3 ...
    for i in msg: print i,
    print

def main():
  # Run as a specific user
  if run_as_user != None:
    run_as_uid = getpwnam(run_as_user).pw_uid
    run_as_gid = getpwnam(run_as_user).pw_gid
    print "%s running as %s (uid=%s,gid=%s)" % (time.strftime('%Y%b%d %H:%M:%S'), run_as_user, run_as_uid, run_as_gid)
    # always set gid first, because once we've set uid, we can't set gid anymore
    os.setgid(run_as_gid)
    os.setuid(run_as_uid)

  # Log startup
  print "%s milter startup" % time.strftime('%Y%b%d %H:%M:%S')
  sys.stdout.flush()

  # Handle log printing in the background
  bt = Thread(target=background)
  bt.start()

  # Register to have the Milter factory create instances of your class:
  Milter.factory = MilterSysUser
  #Milter.set_flags(Milter.ADDHDRS) # we only need to add a header

  flags = Milter.CHGBODY + Milter.CHGHDRS + Milter.ADDHDRS
  flags += Milter.ADDRCPT
  flags += Milter.DELRCPT
  Milter.set_flags(flags)       # tell Sendmail which features we use

  Milter.runmilter("pythonfilter", socketname, timeout)

  # Wait for logger to complete
  logq.put(None)
  bt.join()
  print "%s milter shutdown" % time.strftime('%Y%b%d %H:%M:%S')

if __name__ == "__main__":
  main()

