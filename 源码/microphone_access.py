"""Read Windows permission status and verify actual access; never change permissions."""
import ctypes
import os
import uuid

MICROPHONE_SETTINGS = 'ms-settings:privacy-microphone'
SOUND_SETTINGS = 'ms-settings:sound'

class MicrophoneIssue(Exception):
    def __init__(self, kind, detail=''):
        self.kind = kind
        self.detail = detail
        super().__init__(detail or kind)

def windows_access_status():
    """DeviceAccessInformation.CurrentStatus: 0 unknown, 1 allowed, 2/3 denied.
    Use the public WinRT ABI without adding a separately installed runtime.
    Unknown or unavailable APIs must fall back to opening the input stream.
    """
    if os.name != 'nt':
        return 0
    api = ctypes.WinDLL('combase')
    hresult = ctypes.c_long
    ptr = ctypes.c_void_p
    api.RoInitialize.argtypes = [ctypes.c_uint]
    api.RoInitialize.restype = hresult
    api.WindowsCreateString.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.POINTER(ptr)]
    api.WindowsCreateString.restype = hresult
    api.WindowsDeleteString.argtypes = [ptr]
    api.WindowsDeleteString.restype = hresult
    api.RoGetActivationFactory.argtypes = [ptr, ptr, ctypes.POINTER(ptr)]
    api.RoGetActivationFactory.restype = hresult
    api.RoUninitialize.argtypes = []
    api.RoUninitialize.restype = None
    initialized = api.RoInitialize(1) in (0, 1)
    handle, factory, info = ptr(), ptr(), ptr()
    def method(interface, index, return_type, *argtypes):
        table = ctypes.cast(interface, ctypes.POINTER(ctypes.POINTER(ptr))).contents
        return ctypes.WINFUNCTYPE(return_type, ptr, *argtypes)(table[index])
    try:
        name = 'Windows.Devices.Enumeration.DeviceAccessInformation'
        if api.WindowsCreateString(name, len(name), ctypes.byref(handle)) < 0:
            return 0
        iid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID('574bd3d3-5f30-45cd-8a94-724fe5973084').bytes_le)
        if api.RoGetActivationFactory(handle, ctypes.byref(iid), ctypes.byref(factory)) < 0:
            return 0
        # IInspectable (6 entries), CreateFromId, CreateFromDeviceClassId,
        # CreateFromDeviceClass(AudioCapture=1).
        create = method(factory, 8, hresult, ctypes.c_int32, ctypes.POINTER(ptr))
        if create(factory, 1, ctypes.byref(info)) < 0:
            return 0
        value = ctypes.c_int32()
        get_status = method(info, 8, hresult, ctypes.POINTER(ctypes.c_int32))
        if get_status(info, ctypes.byref(value)) < 0:
            return 0
        return value.value if value.value in (0, 1, 2, 3) else 0
    except (OSError, AttributeError, ValueError):
        return 0
    finally:
        for interface in (info, factory):
            if interface.value:
                method(interface, 2, ctypes.c_ulong)(interface)
        if handle.value:
            api.WindowsDeleteString(handle)
        if initialized:
            api.RoUninitialize()

def audio_issue(exc):
    text = str(exc)
    denied = any(word in text.lower() for word in ('access denied','access is denied','permission denied','0x80070005','权限','拒绝访问'))
    # PortAudio includes a (host-api, native-code, message) tuple for host errors.
    for arg in getattr(exc, 'args', ()):
        if isinstance(arg, tuple) and len(arg) >= 2 and isinstance(arg[1], int):
            denied = denied or (arg[1] & 0xffffffff) == 0x80070005
    return MicrophoneIssue('denied' if denied else 'unavailable', text)

def check_access(sd, device):
    status = windows_access_status()
    if status in (2, 3):
        raise MicrophoneIssue('denied_system' if status == 3 else 'denied')
    try:
        devices = sd.query_devices()
        if not any(item['max_input_channels'] > 0 for item in devices):
            raise MicrophoneIssue('no_device', '未检测到可用的麦克风输入设备')
        info = sd.query_devices(device, 'input')
        if info['max_input_channels'] < 1:
            raise MicrophoneIssue('no_device', '所选设备不是麦克风输入设备')
        try:
            sd.check_input_settings(device=device, channels=1, dtype='float32', samplerate=16000)
            rate = 16000
        except Exception:
            rate = int(info['default_samplerate'])
        # Permission reports alone do not prove the selected hardware is usable.
        # Open and close a local input stream without reading or saving audio.
        with sd.InputStream(device=device, channels=1, dtype='float32', samplerate=rate, blocksize=int(rate * 0.1)):
            pass
        return rate
    except MicrophoneIssue:
        raise
    except Exception as exc:
        # Recheck if permission changed while enumerating/opening the device.
        status = windows_access_status()
        if status in (2, 3):
            raise MicrophoneIssue('denied_system' if status == 3 else 'denied', str(exc)) from exc
        raise audio_issue(exc) from exc

def open_settings(sound=False):
    os.startfile(SOUND_SETTINGS if sound else MICROPHONE_SETTINGS)
