import ws.icb
import ws.api
from rx.subjects import Subject

class Resource(object):
    '''websocket resource'''
    def __init__(self, icb, noun):
        self.icb = icb
        self.noun = noun
        self.messageSubject = Subject()
        icb.stateSubject.first().subscribe(on_next=lambda state: self._on_icb_state(state))
        icb.messageSubject.subscribe(on_next=lambda message: self._on_icb_message(message))

    def put(self, body):
        self.icb.send('PUT', self.noun, body)

    def get(self, body):
        self.icb.send('GET', self.noun, body)

    def subscribe(self, fn):
        return self.messageSubject.subscribe(fn)

    def subscribe_once(self, fn):
        return self.messageSubject.first().subscribe(fn)

    def _on_icb_state(self, state):
        if state == ws.icb.STATE_CONNECTED:
            self._request_subscribe()

    def _on_icb_message(self, message):
        msg = ws.api.parse_message(message)
        if msg['noun'] == self.noun:
            self.messageSubject.on_next(msg)

    def _request_subscribe(self):
        self.icb.send('SUBSCRIBE', self.noun, {})
