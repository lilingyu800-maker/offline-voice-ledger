import unittest
from recording_window import RecordingWindow, RECORDING_SECONDS

class RecordingWindowTests(unittest.TestCase):
    def test_fixed_two_minutes_and_no_activation_no_record(self):
        window=RecordingWindow()
        self.assertEqual(RECORDING_SECONDS,120)
        self.assertFalse(window.accept('普通聊天',10))
        self.assertTrue(window.accept('请记账，清风，4个88A硒鼓。',10))
        self.assertEqual(window.deadline,130)
        self.assertEqual(window.remaining(10),120)
        self.assertFalse(window.due(129.999))
        self.assertTrue(window.due(130))

    def test_complete_first_sentence_does_not_end_window(self):
        window=RecordingWindow()
        window.accept('记账，清风，4个88A硒鼓',0)
        self.assertTrue(window.active)
        window.accept('1只12A硒鼓',60)
        window.accept('9个12A碳粉',119.9)
        self.assertEqual(window.text,'记账,清风,4个88A硒鼓1只12A硒鼓9个12A碳粉')
        self.assertEqual(window.deadline,120)

    def test_repeat_activation_keeps_previous_content_and_deadline(self):
        window=RecordingWindow()
        window.accept('记账，清风，4个88A硒鼓',0)
        token=window.token
        window.accept('记账还有1只12A硒鼓',60)
        self.assertEqual(window.deadline,120)
        self.assertEqual(window.token,token)
        self.assertIn('4个88A硒鼓记账还有1只12A硒鼓',window.text)

    def test_late_decoder_result_for_pre_boundary_audio_is_kept(self):
        window=RecordingWindow()
        window.accept('记账，清风，4个88A硒鼓',0)
        self.assertFalse(window.accept('窗口外文字',120.1))
        self.assertTrue(window.accept('1只12A硒鼓',120.5,captured_token=window.token))
        self.assertIn('1只12A硒鼓',window.text)
        self.assertNotIn('窗口外文字',window.text)

    def test_early_finish_and_new_window_do_not_duplicate_previous(self):
        window=RecordingWindow()
        window.accept('记账清风4个88A硒鼓',5)
        first=window.token
        window.end_early(35)
        self.assertEqual(window.deadline,35)
        window.clear()
        window.accept('记账李凌宇1个12A',40)
        self.assertNotEqual(window.token,first)
        self.assertEqual(window.deadline,160)
        self.assertNotIn('清风',window.text)

if __name__=='__main__':
    unittest.main()
