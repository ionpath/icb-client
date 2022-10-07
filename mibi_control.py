from datetime import datetime
import json
from time import sleep
import requests

from ws.icb import ICB, STATE_CONNECTED
from rx import Observable

class MIBIConnection:

    DEFAULT_WS_ADDRESS = 'ws://localhost:8088'

    def __init__(
        self,
        websocket_url = None,
        connection = None
    ):
        if connection:
            self.connection = connection
        else:
            websocket_url = self.DEFAULT_WS_ADDRESS if websocket_url is None else websocket_url
            self.make_connection(websocket_url)
        
    def make_connection(self, websocket_url):
        self.connection = ICB(websocket_url)
        self.connection.stateSubject.filter(lambda x: x == STATE_CONNECTED).timeout(5000).to_blocking().first()

class MIBIConfig():

    @staticmethod
    def list_imaging_presets_display_names(imaging_presets):
        return [p['displayName'] for p in imaging_presets]

    @staticmethod
    def find_imaging_preset(imaging_presets, display_name):
        try:
            return next(p for p in imaging_presets if p['displayName'] == display_name)
        except StopIteration:
            return None

    @staticmethod
    def find_timing_preset(timing_presets, description, _id):

        try:
            if description is not None:
                return next(p for p in timing_presets if p['description'] == description)
            elif _id is not None:
                return next(p for p in timing_presets if p['id'] == _id)
        except StopIteration:
            return None
    
    def __init__(
        self,
        address = 'http://localhost:9099'
    ):
        self.config = requests.get(address + '/api/config-snapshot').json()
        self.full_config = self.config['uiInstrumentConfig']

    def get_imaging_preset(self, display_name):
        return MIBIConfig.find_imaging_preset(self.full_config["imagingPresets"], display_name)

    def get_timing_preset(self, description=None, _id=None):
        return MIBIConfig.find_timing_preset(self.full_config['timing'], description, _id)

class MIBISetup(MIBIConnection):

    @staticmethod
    def get_fov(position, scanCount, resolution, size, imaging_preset, timing_preset, run_order=None, standard_target=None, slide_id=None, section_id=None):
        fov = {
            "centerPointMicrons": position,
            "scanCount": scanCount,
            "frameSizePixels": {
                "width": resolution,
                "height": resolution
            },
            "fovSizeMicrons": size,
            "fullTiming": timing_preset,
            "timingChoice": timing_preset["id"],
            "timingDescription": timing_preset["description"],
            "imagingPreset": imaging_preset,
            "standardTarget": standard_target,
            "slideId": slide_id,
            "sectionId": section_id
        }
    
        if run_order is not None:
            fov["runOrder"] = run_order
    
        return fov
    
    def __init__(
        self,
        websocket_url = None,
        connection = None
    ):
        super().__init__(websocket_url, connection)

        self.mibi_config = MIBIConfig(websocket_url, connection)

    def get_fovs(
        self,
        count,
        scans,
        position,
        resolution,
        size,
        imaging_preset,
        timing_preset,
        standard_target=None,
        slide_id=None,
        section_id=None
    ):
        fovs = []
        for fov in range(count):

            fovs.append(
                MIBISetup.get_fov(
                    position,
                    scans,
                    resolution,
                    size,
                    imaging_preset,
                    timing_preset,
                    fov + 1,
                    standard_target,
                    slide_id,
                    section_id
                )
            )
        return fovs

    def setup_fovs_sync(self, count, scans_per_fov, position, resolution, size, imaging_preset, timing_preset=None, standard_target=None, slide_id=None, section_id=None):
        imaging_preset = self.mibi_config.get_imaging_preset(imaging_preset)

        if timing_preset is None:
            timing_preset = self.mibi_config.get_timing_preset(_id=imaging_preset["defaults"]["timingChoice"])
        else:
            timing_preset = self.mibi_config.get_timing_preset(description=timing_preset)

        fovs = self.get_fovs(
            count,
            scans_per_fov,
            position,
            resolution,
            size,
            imaging_preset,
            timing_preset,
            standard_target,
            slide_id,
            section_id
        )

        return self.setup_fovs_sync_with_fovs(fovs)

    def setup_fovs_sync_with_fovs(self, fovs):

        _fovs = []

        for i, fov in enumerate(fovs):

            fullTiming = self.mibi_config.get_timing_preset(fov['timingDescription'])

            if fullTiming is None:
                raise Exception('Invalid timingDescription')

            fov['timingChoice'] = fullTiming['id']
            fov['fullTiming'] = fullTiming
            fov['scans'] = ['{}' for i in range(fov['scanCount'])]
            fov['runOrder'] = i + 1

            standard_target = fov.get("standardTarget")
            slide_id = fov.get("slideId")
            section_id = fov.get("sectionId")

            if (standard_target is None) and (slide_id is None and section_id is None):
                raise Exception('Must provide either a standard target or a slide and section id pair')

            _fovs.append(fov)

        return self.setup_fovs(_fovs)  

    def setup_fovs(self, fovs):
        fov_setup_resource = self.connection.get_resource('/fovsetup')
        on_fov_setup = fov_setup_resource.messageSubject.filter(lambda x: len(x['body']['fovs']) == len(fovs))
        fov_setup_resource.put({'fovs': fovs})

        results = on_fov_setup.timeout(5000).to_blocking().first()
        return results['body']['fovs']

class MIBIStageControl(MIBIConnection):
    def set_stage_position(self, position):
        stage_resource = self.connection.get_resource('/stageparameters')

        is_ready_subject = stage_resource.messageSubject.filter(lambda x: x['body']['motorOn']['x'] == True and x['body']['motorOn']['y'] == True and x['body']['waiting'] == True)

        is_ready_subject.timeout(5000).to_blocking().first()
        print('Stage is ready!')
        on_transition_subject = stage_resource.messageSubject.timeout(5000).filter(lambda x: 'inTransition' in x['body'])
        on_stop_transition_subject = stage_resource.messageSubject.skip(1).filter(lambda x: 'inTransition' not in x['body'])

        stage_resource.put({
            'targetStagePositionMicrons': position
        })
        try:
            on_transition_subject.to_blocking().first()
            on_stop_transition_subject.to_blocking().first()
        except Exception as e:
            # we assume no response means that we have already reached the set point
            pass
        print('Stage transition complete!')
        
class MIBIHighVoltage(MIBIConnection):

    def save_as_default(self, channels):
        save_resource = self.connection.get_resource('/hv-save')
        save_resource.put({
            'hvChannels': channels
        })
class MIBIControl(MIBIConnection):
    """Acquire a MIBIcontrol run with configurable FOV parameters in Python."""

    DEFAULT_RUN_NAME_PREFIX = 'MIBICONTROL_PYTHON'
    
    def __init__(
        self,
        websocket_url = None,
        **kwargs
    ):  
        """Initialize a MIBIControl instance to control run acquisitions.

        Args:
            websocket_url (str, optional): The address to the MIBIcontrol websocket. If not provided, the default of `ws://localhost:8088` is used. Defaults to None.
        """
        super().__init__(websocket_url)

        self.mibi_setup = MIBISetup(
            websocket_url,
            self.connection,
            **kwargs
        )
        
        self.run_name_prefix = kwargs.get("run_name_prefix", self.DEFAULT_RUN_NAME_PREFIX)

    def get_default_run_name(self):
        return self.run_name_prefix + '_' + datetime.now().strftime('%d-%m-%YT%H%M%S')
    
    # TODO: Have a single universal function that accepts different formats for FOVs
    def setup_and_acquire_run_with_fovs(self, fovs):
        """Starts a run with the provided `fovs`. This method will execute synchronously, completing when the run has stopped acquiring (this includes run errors or cancellations).

        Args:
            fovs (dict): A list of dictionaries representing the FOV parameters comprising the run.
        """
        setup_fovs = self.mibi_setup.setup_fovs_sync_with_fovs(fovs)

        run_name = self.get_default_run_name()
            
        self._start_run(run_name, setup_fovs)

    def setup_and_acquire_run_with_json(self, filepath):
        """Starts a run using the FOV parameters encoded in the JSON at the provided `filepath`. This method will execute synchronously, completing when the run has stopped acquiring (this includes run errors or cancellations).

        Args:
            filepath (str): The path to the FOV JSON exported from the MIBIcontrol UI.  
        """
    
        fovs = None
        with open(filepath) as f:
            fovs = json.load(f)['fovs']

        setup_fovs = self.mibi_setup.setup_fovs_sync_with_fovs(fovs)

        run_name = self.get_default_run_name()
            
        self._start_run(run_name, setup_fovs)

    def setup_and_acquire_run(
        self,
        fov_count,
        scan_count,
        position,
        resolution,
        size,
        imaging_preset,
        timing_preset=None,
        standard_target=None,
        slide_id=None,
        section_id=None,
        run_name=None
    ):
        """Acquire a run based on provided FOV parameters.

        Args:
            fov_count (int): Number of FOVs to acquire
            scan_count (int): Number of scans per FOV to acquire
            position (dict): The FOV center point in microns of the x and y axes (e.g. {"x": 0, "y": 5})
            resolution (int): FOV frame size
            size (int): Height and width of FOV in microns
            imaging_preset (str): Name of imaging preset used for acquiring FOV
            timing_preset (str, optional): Description of timing preset used for acquiring FOV. If None, the default timing preset of the provided imaging preset is used. Defaults to None. 
            standard_target (str, optional): The standard target which is acquired by the FOV. Either `standard_target` or both `slide_id` and `section_id` must be provided. Defaults to None. 
            slide_id (str, optional): MIBItracker Slide ID matching the loaded slide in the instrument. Defaults to None.
            section_id (str, optional): MIBItracker Section ID matching the FOV target. Defaults to None.
            run_name (str, optional): The name of the acquired run. If not provided, then a run name containing the time of acquisition will be used. Defaults to None.
        """

        setup_fovs = self.mibi_setup.setup_fovs_sync(
            fov_count,
            scan_count,
            position,
            resolution,
            size,
            imaging_preset,
            timing_preset,
            standard_target,
            slide_id,
            section_id
        )

        run_name = self.get_default_run_name()
            
        self._start_run(run_name, setup_fovs)

    def _start_run(self, run_name, fovs):
        DEFAULT_IPUI_URL = 'http://ionpath/'

        run_parameters_resource = self.connection.get_resource('/runparameters')
        state_resource = self.connection.get_resource('/state')

        def filter_for_run_end(x):
            run = x['body']
            return run_name == run['name'] and run['status'] not in ['inProgress', 'queued']

        def filter_for_blank_state(x):
            return x['body']['currentState'] == 'blanked'

        run_params_observable = run_parameters_resource.messageSubject.as_observable()

        # update_subscription = run_params_observable.subscribe(lambda x: print('Run update:', x['body']['name'], x['body']['status'], '\n\n\n'))
        
        print('\n\n\nStarting run:', run_name)
        print('Follow progress here: ' + DEFAULT_IPUI_URL)

        run_parameters_resource.put({
            'status': 'inProgress',
            'name': run_name,
            'fovs': fovs
        })
        
        state_resource.messageSubject.combine_latest(run_params_observable, lambda x, y: (x, y)).filter(lambda xy: filter_for_blank_state(xy[0]) and filter_for_run_end(xy[1])).to_blocking().first()

        # update_subscription.dispose()
        print('Run completed.')
