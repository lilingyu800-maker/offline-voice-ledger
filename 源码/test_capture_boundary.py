import queue
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import sounddevice as sd
import main
from recording_window import split_at_deadline

class CaptureBoundaryTests(unittest.TestCase):
    def test_audio_block_straddling_deadline_is_split(self):
        samples=np.arange(1600,dtype=np.float32)
        before,after=split_at_deadline(samples,16000,120.05,120)
        self.assertEqual(len(before),800)
        self.assertEqual(len(after),800)
        self.assertEqual(before[-1],799)
        self.assertEqual(after[0],800)

    def test_last_in_progress_utterance_is_decoded_before_window_closes(self):
        app=main.App.__new__(main.App)
        app.events=queue.Queue()
        app.stop_flag=threading.Event()
        app.window_boundary=('window-test',120.0)
        captured=[]
        class Vad:
            def reset(self):
                self.samples=[]
                self.pending=[]
            def accept_waveform(self,data):
                self.samples.extend(data.tolist())
                if len(data) and np.max(data)>2:
                    app.stop_flag.set()
            def is_speech_detected(self):
                return bool(self.samples)
            def empty(self):
                return not self.pending
            @property
            def front(self):
                return SimpleNamespace(samples=self.pending[0])
            def pop(self):
                self.pending.pop(0)
            def flush(self):
                if self.samples:
                    self.pending.append(np.array(self.samples,dtype=np.float32))
        vad=Vad()
        app.model=(object(),vad,512)
        class Stream:
            def __init__(self,**kwargs):
                self.callback=kwargs['callback']
            def __enter__(self):
                self.callback(np.ones((1600,1),dtype=np.float32),1600,None,False)
                block=np.concatenate((np.full(800,2,dtype=np.float32),np.full(800,9,dtype=np.float32))).reshape(-1,1)
                self.callback(block,1600,None,False)
                return self
            def __exit__(self,*args):
                return False
        def decode(model,samples):
            captured.append(samples)
            return '1只12A硒鼓'
        # The recognizer is mocked; this test must also work without downloaded models.
        with tempfile.TemporaryDirectory() as model_dir,patch.object(main,'MODEL',Path(model_dir)),patch.object(main,'check_access',return_value=16000),patch.object(sd,'InputStream',Stream),patch.object(main,'transcribe',side_effect=decode),patch.object(main.time,'monotonic',side_effect=[119.95,120.05]):
            app.listen(None)
        events=[]
        while not app.events.empty():
            events.append(app.events.get_nowait())
        self.assertEqual(len(captured),1)
        self.assertEqual(np.max(captured[0]),2)
        self.assertEqual(sum(captured[0]==1),1600)
        self.assertEqual(sum(captured[0]==2),800)
        self.assertIn(('final',('1只12A硒鼓','window-test')),events)
        self.assertIn(('window_done','window-test'),events)
        self.assertLess(events.index(('final',('1只12A硒鼓','window-test'))),events.index(('window_done','window-test')))

if __name__=='__main__':
    unittest.main()
