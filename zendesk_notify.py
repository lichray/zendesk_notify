#!/usr/bin/env python

import base64

# The endpoints must be Agent-oriented.

USERS_TMPL = 'https://{host}/api/v2/users/search.json?query={user}'
GROUPS_TMPL = 'https://{host}/api/v2/users/{user_id}/group_memberships.json'
TICKETS_TMPL = 'https://{host}/api/v2/tickets/recent.json'
VIEW_TICKETS_TMPL = base64.decodestring('''
aHR0cHM6Ly97aG9zdH0vcnVsZXMvc2VhcmNoP2ZpbHRlcj12aWV3cyZzZWFyY2hfbmFtZT1PcGVu
K1RpY2tldHMlMkMraW4reW91citncm91cCUyOHMlMjkmc2V0cyU1QjElNUQlNUJjb25kaXRpb25z
JTVEJTVCMCU1RCU1Qm9wZXJhdG9yJTVEPWlzJnNldHMlNUIxJTVEJTVCY29uZGl0aW9ucyU1RCU1
QjAlNUQlNUJzb3VyY2UlNUQ9Z3JvdXBfaWQmc2V0cyU1QjElNUQlNUJjb25kaXRpb25zJTVEJTVC
MCU1RCU1QnZhbHVlJTVEJTVCMCU1RD1jdXJyZW50X2dyb3VwcyZzZXRzJTVCMSU1RCU1QmNvbmRp
dGlvbnMlNUQlNUIxJTVEJTVCb3BlcmF0b3IlNUQ9bGVzc190aGFuJnNldHMlNUIxJTVEJTVCY29u
ZGl0aW9ucyU1RCU1QjElNUQlNUJzb3VyY2UlNUQ9c3RhdHVzX2lkJnNldHMlNUIxJTVEJTVCY29u
ZGl0aW9ucyU1RCU1QjElNUQlNUJ2YWx1ZSU1RCU1QjAlNUQ9MiZzZXRzJTVCMSU1RCU1QmNvbmRp
dGlvbnMlNUQlNUIyJTVEJTVCb3BlcmF0b3IlNUQ9aXNfbm90JnNldHMlNUIxJTVEJTVCY29uZGl0
aW9ucyU1RCU1QjIlNUQlNUJzb3VyY2UlNUQ9Z3JvdXBfaWQmc2V0cyU1QjElNUQlNUJjb25kaXRp
b25zJTVEJTVCMiU1RCU1QnZhbHVlJTVEJTVCMCU1RD0=
''')

POLL_INTERVAL = 60  # secs

import contextlib
import anydbm
import sys
import time
import webbrowser
import ConfigParser

import requests

try:
    from gi.repository import GObject as gobject
    from gi.repository import Notify
    Notify.init('zendesk-notify')
    _new_notification = Notify.Notification.new

    def _add_action(w, action, text, f):
        return w.add_action(action, text, f, None, None)

except ImportError:
    import gobject
    import pynotify
    pynotify.init('zendesk-notify')
    _new_notification = pynotify.Notification

    def _add_action(w, action, text, f):
        return w.add_action(action, text, f)


def Notifier(cfg, db):

    class Obj(dict):
        __getattr__ = dict.__getitem__
        __setattr__ = dict.__setitem__

    self = Obj(dialog=None,
               new_tickets=set(),
               previously_confirmed=True)

    def alert(title, link):
        self.dialog = _new_notification(title, '', "dialog-information")
        self.dialog.set_timeout(0)
        _add_action(self.dialog, link, "Show", open_link)
        self.dialog.connect("closed", closed)
        self.dialog.show()

    def warn(title, message):
        self.dialog = _new_notification(title, message, "dialog-warning")
        self.dialog.show()

    def request_json(uri_template, dic):
        uri = uri_template.format(**dic)
        return requests.get(uri, auth=tuple(dic['api_key'].split(':'))).json()

    def open_link(w, link, data):
        webbrowser.open(link)

    def closed(w):
        w.close()

        for ticket in self.new_tickets:
            db[ticket] = ''
        self.new_tickets = set()
        self.previously_confirmed = True

    def look_at_queue():
        try:
            users = request_json(USERS_TMPL, cfg)

            if users['count'] < 0:
                raise Exception('User not found')
            elif users['count'] > 1:
                raise Exception('User is not unique')

            cfg['user_id'] = str(users['users'][0]['id'])
            groups = request_json(GROUPS_TMPL, cfg)

            for group in groups['group_memberships']:
                tickets = request_json(TICKETS_TMPL, cfg)

                for ticket in tickets['tickets']:
                    ticket_id = str(ticket["id"])

                    if ticket_id not in db:
                        self.new_tickets.add(ticket_id)

            if len(self.new_tickets) != 0 and self.previously_confirmed:
                alert('Your group got %d new tickets' % len(self.new_tickets),
                      VIEW_TICKETS_TMPL.format(**cfg))
                self.previously_confirmed = False

        except Exception as e:
            warn('Request failed', str(e))

        return True

    def run():
        look_at_queue()
        gobject.timeout_add_seconds(POLL_INTERVAL, look_at_queue)
        gobject.MainLoop().run()

    return run


if __name__ == '__main__':
    parser = ConfigParser.RawConfigParser()
    parser.read('zendesk_notify.ini')
    cfg = parser.defaults()

    with contextlib.closing(anydbm.open('zendesk_notify.db', 'c')) as db:
        notifier = Notifier(cfg, db)

        try:
            notifier()
        except KeyboardInterrupt:
            exit(0)
