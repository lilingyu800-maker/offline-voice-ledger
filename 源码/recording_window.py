"""A fixed two-minute text collection window, independent of ASR and the GUI."""
import math
import unicodedata
import uuid

RECORDING_SECONDS = 120

def split_at_deadline(samples,rate,captured_end,deadline):
    captured_start=captured_end-len(samples)/rate
    count=max(0,min(len(samples),round((deadline-captured_start)*rate)))
    return samples[:count],samples[count:]

class RecordingWindow:
    def __init__(self, duration=RECORDING_SECONDS):
        self.duration=duration
        self.clear()

    def clear(self):
        self.token=None
        self.started=None
        self.deadline=None
        self.fragments=[]

    @property
    def active(self):
        return self.token is not None

    @property
    def text(self):
        return ''.join(self.fragments)

    def accept(self, text, now, captured_token=None):
        text=unicodedata.normalize('NFKC',text).strip().strip('。!！?？,，;；')
        if not text:
            return False
        if not self.active:
            if '记账' not in text:
                return False
            self.token=uuid.uuid4().hex
            self.started=now
            self.deadline=now+self.duration
            text=text[text.index('记账'):]
        elif now>=self.deadline and captured_token!=self.token:
            return False
        # Repeating the activation word inside a window is ordinary content.
        # It must neither clear previous text nor restart the fixed deadline.
        self.fragments.append(text)
        return True

    def remaining(self, now):
        return max(0,math.ceil(self.deadline-now)) if self.active else 0

    def due(self, now):
        return self.active and now>=self.deadline

    def end_early(self, now):
        if self.active:
            self.deadline=min(self.deadline,now)
