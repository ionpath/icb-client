import json
import time
import uuid

VERSION = '1.7'

def create_message(verb, noun, body):
    return [
        verb,
        noun,
        {
            'messageId': str(uuid.uuid4()),
            'timestampMillis': time_millis(),
            'version': VERSION
        },
        body
    ]


def parse_message(json_str):
    msg = json.loads(json_str)
    return {
        'verb': msg[0],
        'noun': msg[1],
        'headers': msg[2],
        'body': msg[3]
    }


def time_millis():
    return int(round(time.time() * 1000))
