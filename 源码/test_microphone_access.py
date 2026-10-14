import unittest
from unittest.mock import Mock, patch
import microphone_access as mic

def audio_device():
    sd=Mock()
    sd.query_devices.side_effect=lambda *args: {'max_input_channels':1,'default_samplerate':48000} if args else [{'max_input_channels':1,'default_samplerate':48000}]
    sd.InputStream.return_value.__enter__=Mock(return_value=sd.InputStream.return_value)
    sd.InputStream.return_value.__exit__=Mock(return_value=False)
    return sd

class MicrophoneAccessTests(unittest.TestCase):
    def test_denied_user_and_system_before_opening_audio(self):
        for status,kind in [(2,'denied'),(3,'denied_system')]:
            sd=audio_device()
            with patch.object(mic,'windows_access_status',return_value=status), self.assertRaises(mic.MicrophoneIssue) as caught:
                mic.check_access(sd,None)
            self.assertEqual(caught.exception.kind,kind)
            sd.query_devices.assert_not_called()
            sd.InputStream.assert_not_called()

    def test_allowed_and_unspecified_verify_actual_access(self):
        for status in (0,1):
            sd=audio_device()
            with patch.object(mic,'windows_access_status',return_value=status):
                self.assertEqual(mic.check_access(sd,4),16000)
            self.assertEqual(sd.InputStream.call_args.kwargs['device'],4)
            sd.InputStream.return_value.__enter__.assert_called_once()
            sd.InputStream.return_value.__exit__.assert_called_once()

    def test_absent_hardware_is_not_reported_as_permission_denied(self):
        sd=audio_device()
        sd.query_devices.side_effect=None
        sd.query_devices.return_value=[]
        with patch.object(mic,'windows_access_status',return_value=1), self.assertRaises(mic.MicrophoneIssue) as caught:
            mic.check_access(sd,None)
        self.assertEqual(caught.exception.kind,'no_device')
        sd.InputStream.assert_not_called()

    def test_unknown_permission_and_failed_open(self):
        for error,kind in [(OSError('Access is denied'),'denied'),(OSError('device busy'),'unavailable')]:
            sd=audio_device()
            sd.InputStream.side_effect=error
            with patch.object(mic,'windows_access_status',return_value=0), self.assertRaises(mic.MicrophoneIssue) as caught:
                mic.check_access(sd,None)
            self.assertEqual(caught.exception.kind,kind)

    def test_permission_revoked_during_open(self):
        sd=audio_device()
        sd.InputStream.side_effect=OSError('cannot open stream')
        with patch.object(mic,'windows_access_status',side_effect=[1,2]), self.assertRaises(mic.MicrophoneIssue) as caught:
            mic.check_access(sd,None)
        self.assertEqual(caught.exception.kind,'denied')

    def test_device_native_sample_rate_fallback(self):
        sd=audio_device()
        sd.check_input_settings.side_effect=OSError('unsupported samplerate')
        with patch.object(mic,'windows_access_status',return_value=1):
            self.assertEqual(mic.check_access(sd,None),48000)

    def test_windows_permission_and_sound_settings_targets(self):
        with patch.object(mic.os,'startfile',create=True) as launch:
            mic.open_settings()
            launch.assert_called_with('ms-settings:privacy-microphone')
            mic.open_settings(sound=True)
            launch.assert_called_with('ms-settings:sound')

    def test_native_hresult_access_denied(self):
        self.assertEqual(mic.audio_issue(OSError('host error',(-9999,-2147024891,'error'))).kind,'denied')

if __name__=='__main__':
    unittest.main()
