# icb-client

Helper library for controlling MIBIScope

## example
```
import datetime
import shutil
import time
import requests
from icb import ICB

# connect to ICB
icb = ICB("ws://localhost:8088")

# create/get HV resources
hv_state_resource = icb.get_resource('/hv-state')
hv_adc_resource = icb.get_resource('/hv-adc')

# power HV on
hv_state_resource.put({'state': 'POWER_ON'})

# subscribe to incoming HV messages
state_subscription = hv_state_resource.subscribe(lambda msg: print('> HV STATE: ', msg['body']['state']))
adc_subscription = hv_adc_resource.subscribe(lambda msg: print('> ADC VALUES: ', msg['body']['hvChannels']))

# more advanced subscription using RxPY (see https://github.com/ReactiveX/RxPY/tree/release/v1.6.x fro more details)
dac_subscription = icb \
    .get_resource('/hv-dac') \
    .messageSubject \
    .map(lambda msg: msg['body']['hvChannels']) \
    .filter(lambda data: True) \
    .subscribe(lambda data: print('> DAC VALUES: ', data))

# throttled stream
throttle = datetime.timedelta(seconds=1)
gascontrol_subscription = icb \
    .get_resource('/gascontrol') \
    .messageSubject \
    .throttle_first(throttle) \
    .subscribe(lambda msg: print(msg['body']))

# give ICB some time to open DAC, in real code it should be guarded by getting real HV state
time.sleep(2)

# set Lens1 to 100.5
icb.get_resource('/hv-dac').put({'hvChannel': {'name': 'Lens1', 'value': 100.5, 'channel': 15}})

# power HV off later
time.sleep(10)
hv_state_resource.put({'state': 'POWER_OFF'})

# save attached tiff image 
url = 'http://localhost:9099/api/convenience/sed'
r = requests.get(url, stream=True)
if r.status_code == 200:
    with open('sed_image.tiff', 'wb') as f:
        r.raw.decode_content = True
        shutil.copyfileobj(r.raw, f) 

# unsubscribe (if you really need it for some reason)
state_subscription.dispose()
adc_subscription.dispose()
dac_subscription.dispose()

# close connection and exit
icb.close()

```