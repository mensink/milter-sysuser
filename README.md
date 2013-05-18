milter-sysuser
==============

A postfix/sendmail milter that determines/blocks the system user for local SMTP connections

Abstract
--------

On most multi-user systems, like webservers, users are allowed to send e-mail either through
a local sendmail program, or by using the SMTP server on localhost. The problem with the
latter method is that e-mails are not tagged with information about the actual sender.
Should you have to deal with a malicious user or a compromised website that's sending spam
through your local mailserver, it would be easier if you could simply check the mail headers
and identify the culprit.

This is a milter that tries to figure out who the sender is for mail messages that enter
the mailsystem through a local network interface (127.0.0.0/8 or ::1). This is possible
because milters are executed while the network connection is still open, and the details
about the connection from the server end are known.

The information about the user is then added in the form of a mail header in the actual
message.

How it works
------------

A milter (short for MailfILTER) is a sort of plugin for MTA's like postfix or sendmail.
Because it is invoked even while the message is being received, a milter can do some
interesting stuff at early stages in receiving mail. Typically milters are used for
signing mail, greylisting, traffic shaping and so on.

Our milter is a simple python script, but because it utilizes the
[python-milter](http://www.bmsi.com/python/milter.html) library, it provides a fully
working milter interface.

When a mail is being sent, as soon as a HELO is issued our script receives a notification
of this, including on which interface and port the connection was made. Knowing the server
part of the connection, the script uses the [lsof](http://people.freebsd.org/~abe/)
unix-command to identify who is holding the other end of the connection. This information
is then retained until later and a header is added to the mail that contains the user
and program name that was found.

Additionally, it's possible to hard-code some usernames into the script and have all mail
(that comes in through local SMTP) blocked for those users. Typically this is not
recommended, but may turn out useful as a temporary solution while troubleshooting a
compromised website.

Requirements
------------

This tool has only been tested with the [Postfix](http://www.postfix.org/) software
running on [Debian](http://www.debian.org/), but it should also work with sendmail, and
on any unix-like system that has either MTA and Python installed.

On my debian, it needs the following additional packages to be installed:

* `python-ipaddr`
* `sudo`

Installing
----------

The first step would of course be downloading the `milter-sysuser.py` file, and put
it somewhere on the target machine. You should either run it with the same user-id as
postfix, or run it as root and have the script use setgid+setuid to run it as that
user.

Before you run it, open up the file and edit the 'Settings' part at the top of the
file. The settings are these:

* `socketname`: This is the socket-file you want to use. It must also be openable by
  the postfix program. That's why the script should run as postfix's user.
* `timeout`: The socket timeout. I suppose 600 seconds should be more than enough,
  but you can set it higher if needed, or 0 if you want it to never timeout (which
  is not recommended).
* `run_as_user`: Set this to a valid username and the script will automatically
  run as that user. Set it to None if it already runs with the right credentials.
  The credentials are important, because otherwise the postfix program will not be
  able to use the created socket.
* `blocked_mailusers`: This is a list with usernames for whom all local SMTP-mail
  should be blocked.

Now, you need to allow the user to run lsof so it can figure out the right
information. I'm using sudo for this. Edit the /etc/sudoers file (use `sudovi` on
Debian to do this) and add the following line:

`postfix ALL=(ALL) NOPASSWD: /usr/bin/lsof`

If your postfix user is any other than `postfix`, put the correct username there.

Now you should be able to run the milter: `python milter-sysuser.py`

To activate it in Postfix, add the following line to `/etc/postfix/main.cf`:

`smtpd_milters = unix:/private/milter.sock`

On my system, the socket location is relative to `/var/spool/postfix/` so we don't
specify the full path here.

Additionally, I like the following line because it doesn't break your Postfix should
the milter not work for whatever reason:

`milter_default_action = accept`

That's it, now if the milter is running, restart postfix and you're done.

Testing
-------

Replace `user@localdomain` with an actual user, and preferrably the from address too:

`stefan@s00:~# telnet localhost smtp`  
`Trying ::1...`  
`Connected to localhost.`  
`Escape character is '^]'.`  
`220 s00.basemotive.nl ESMTP Postfix (Debian/GNU)`  
`helo localhost`  
`250 s00.basemotive.nl`  
`mail from: some@example.org`  
`250 2.1.0 Ok`  
`rcpt to: user@localdomain`  
`250 2.1.5 Ok`  
`data`  
`354 End data with <CR><LF>.<CR><LF>`  
`This is only a test.`  
`.`

Now, the resulting mail should have a header like this:

`X-Sender-Process-Info: user=stefan program=telnet`

If it doesn't work, check the postfix logs. Also, the `milter-sysuser.py`
should output some information about each mail that passes through it.

Notes
-----

Comments and suggestions are welcome.
