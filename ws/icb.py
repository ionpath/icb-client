import json
import threading

import websocket
from rx.subjects import ReplaySubject

import ws.api
from resource import Resource

STATE_CONNECTED = 0
STATE_ERROR = 1
STATE_CLOSED = 2


class ICB(object):

    def __init__(self, url):
        print(f'ICB client connecting to {url}...')
        self.url = url
        self.messageSubject = ReplaySubject(1)
        self.stateSubject = ReplaySubject(1)
        self.ws = websocket.WebSocketApp(self.url,
                                         on_open=lambda ws: self._on_open(ws),
                                         on_message=lambda ws, message: self._on_message(ws, message),
                                         on_error=lambda ws, error: self._on_error(ws, error),
                                         on_close=lambda ws: self._on_close(ws))
        self.resources = {}
        try:
            thread = threading.Thread(target=self.ws.run_forever)
            thread.start()
        except (KeyboardInterrupt, SystemExit):
            self.ws.close()

    def get_resource(self, noun):
        if noun not in self.resources:
            self.resources[noun] = Resource(self, noun)
        return self.resources[noun]

    def close(self):
        self.ws.close()

    def send(self, verb, noun, body):
        message = ws.api.create_message(verb, noun, body)
        self.stateSubject.first().subscribe(on_next=lambda state: self._send_safe(state, message))

    def _on_message(self, ws, message):
        self.messageSubject.on_next(message)

    def _on_error(self, ws, error):
        print('ICB error:', error)
        self.stateSubject.on_next(STATE_ERROR)

    def _on_open(self, ws):
        print(f'ICB client connected to {self.url}')
        self.stateSubject.on_next(STATE_CONNECTED)

    def _on_close(self, ws):
        print('ICB client disconnected')
        self.stateSubject.on_next(STATE_CLOSED)

    def _send_safe(self, cur_state, message):
        if cur_state == STATE_CONNECTED:
            self.ws.send(json.dumps(message))
        else:
            print('could not send, not connected')
