import ctypes
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from ledger import Ledger, compact, parse, normalize_entry, correct_speech_entry, state_dir, validate_name
from recognition import load_model, transcribe
from microphone_access import MicrophoneIssue, check_access, audio_issue, open_settings
from recording_window import RecordingWindow, split_at_deadline

BASE = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
MODEL = BASE / '模型' / 'sensevoice'

class App:
    def __init__(self, root):
        self.root = root
        self.ledger = Ledger()
        self.config_file = state_dir() / '设置.json'
        try:
            self.config = json.loads(self.config_file.read_text('utf-8'))
        except (OSError, ValueError):
            self.config = {'aliases': '李凌宇=李凌宇|李玲雨|李玲宇|李凌雨|李灵宇', 'auto': True}
        self.events = queue.Queue()
        self.stop_flag = threading.Event()
        self.thread = None
        self.model = None
        self.microphone_dialog = None
        self.window=RecordingWindow()
        self.window_boundary=None
        self.awaiting_finish=False
        self.preview_token=None
        self.draft_file=state_dir()/'两分钟草稿.json'
        self.countdown=tk.StringVar(value='等待激活 · 说“记账”后连续记录两分钟')
        self.status = tk.StringVar(value='就绪 · 点击“开始聆听”后说：记账，清风，4个88A硒鼓')
        self.heard = tk.StringVar(value='尚未接收到语音')
        self.raw = tk.StringVar(value='记账，清风，4个88A硒鼓')
        self.name = tk.StringVar()
        self.entry = tk.StringVar()
        self.auto = tk.BooleanVar(value=self.config.get('auto', True))
        root.title('离线语音记账')
        root.geometry('960x730')
        root.minsize(840,650)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TLabel', font=('Microsoft YaHei UI',10))
        style.configure('TButton', font=('Microsoft YaHei UI',10), padding=7)
        style.configure('Treeview', rowheight=28, font=('Microsoft YaHei UI',10))
        outer = ttk.Frame(root, padding=20)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='离线语音记账', font=('Microsoft YaHei UI',22,'bold')).pack(anchor='w')
        ttk.Label(outer, text='说“记账，姓名，账目内容” · 例如：记账，清风，4个88A硒鼓').pack(anchor='w', pady=(4,14))
        controls = ttk.Frame(outer)
        controls.pack(fill='x')
        self.start_btn = ttk.Button(controls, text='开始聆听', command=self.start)
        self.start_btn.pack(side='left')
        self.stop_btn = ttk.Button(controls, text='停止聆听', command=self.stop, state='disabled')
        self.stop_btn.pack(side='left', padx=8)
        ttk.Label(controls, text='麦克风').pack(side='left', padx=(10,4))
        self.device_box = ttk.Combobox(controls, state='readonly', width=34)
        self.device_box.pack(side='left')
        ttk.Button(controls, text='刷新', command=self.devices).pack(side='left', padx=8)
        recording_bar=ttk.Frame(outer)
        recording_bar.pack(fill='x',pady=(8,0))
        ttk.Label(recording_bar,textvariable=self.countdown,foreground='#1D4ED8').pack(side='left')
        self.finish_btn=ttk.Button(recording_bar,text='结束本次记录',command=self.request_finish,state='disabled')
        self.finish_btn.pack(side='right')
        ttk.Checkbutton(outer, text='两分钟结束后自动写入（取消后可先修改，再手动保存）', variable=self.auto, command=self.save_config).pack(anchor='w', pady=10)
        ttk.Label(outer, textvariable=self.status, wraplength=880, foreground='#1D4ED8').pack(anchor='w')
        ttk.Label(outer, textvariable=self.heard, wraplength=880, foreground='#475569').pack(anchor='w', pady=(6,12))
        edit = ttk.LabelFrame(outer, text='文字测试 / 修正识别结果', padding=10)
        edit.pack(fill='x')
        line = ttk.Frame(edit)
        line.pack(fill='x')
        ttk.Entry(line, textvariable=self.raw).pack(side='left', fill='x', expand=True)
        ttk.Button(line, text='解析文字', command=self.parse_manual).pack(side='left', padx=(8,0))
        fields = ttk.Frame(edit)
        fields.pack(fill='x', pady=(8,0))
        ttk.Label(fields,text='姓名').pack(side='left',padx=(0,6))
        self.name_box=ttk.Entry(fields,textvariable=self.name,width=20)
        self.name_box.pack(side='left',padx=(0,12))
        ttk.Label(fields,text='账目').pack(side='left',padx=(0,6))
        self.entry_box=tk.Text(fields,height=3,width=43,wrap='word',font=('Microsoft YaHei UI',10))
        self.entry_box.pack(side='left',fill='x',expand=True,padx=(0,12))
        def sync_entry(*args):
            value=self.entry.get()
            if self.entry_box.get('1.0','end-1c')!=value:
                state=self.entry_box.cget('state')
                self.entry_box.configure(state='normal')
                self.entry_box.delete('1.0','end')
                self.entry_box.insert('1.0',value)
                self.entry_box.see('end')
                self.entry_box.configure(state=state)
        self.entry.trace_add('write',sync_entry)
        self.entry_box.bind('<KeyRelease>',lambda event:self.entry.set(self.entry_box.get('1.0','end-1c')))
        ttk.Button(fields,text='保存一条',command=self.save_manual).pack(side='left')
        aliases = ttk.Frame(outer)
        aliases.pack(fill='x', pady=12)
        ttk.Button(aliases,text='姓名纠正设置',command=self.edit_aliases).pack(side='left')
        ttk.Button(aliases,text='打开账目文件夹',command=self.open_folder).pack(side='left',padx=8)
        ttk.Button(aliases,text='重试未写入',command=self.retry).pack(side='left')
        ttk.Button(aliases,text='清空未保存草稿',command=self.clear_draft).pack(side='left',padx=8)
        ttk.Label(outer,text=f'保存位置：{self.ledger.root}',wraplength=880).pack(anchor='w',pady=(0,8))
        table_frame=ttk.Frame(outer)
        table_frame.pack(fill='both',expand=True)
        self.table=ttk.Treeview(table_frame, columns=('time','name','entry','state'), show='headings')
        for col,title,width in [('time','系统时间',180),('name','姓名',140),('entry','账目',320),('state','写入状态',240)]:
            self.table.heading(col,text=title)
            self.table.column(col,width=width,minwidth=70)
        scroll=ttk.Scrollbar(table_frame,orient='vertical',command=self.table.yview)
        self.table.configure(yscrollcommand=scroll.set)
        self.table.pack(side='left',fill='both',expand=True)
        scroll.pack(side='right',fill='y')
        ttk.Label(outer,text='说“记账”后记录两分钟，同一窗口的内容合并为一行；可点击“结束本次记录”提前完成。',foreground='#64748B',wraplength=880).pack(anchor='w',pady=(10,0))
        self.devices()
        self.ledger.retry()
        self.refresh()
        self.restore_draft()
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)

    def devices(self):
        if self.thread and self.thread.is_alive():
            return
        try:
            import sounddevice as sd
            previous=self.device_ids[self.device_box.current()] if hasattr(self,'device_ids') and self.device_box.current()>=0 else None
            self.device_ids=[None]
            labels=['系统默认麦克风']
            for i,d in enumerate(sd.query_devices()):
                if d['max_input_channels'] > 0:
                    self.device_ids.append(i)
                    labels.append(f"{i}: {d['name']}")
            self.device_box['values']=labels
            self.device_box.current(self.device_ids.index(previous) if previous in self.device_ids else 0)
        except Exception as exc:
            self.device_ids=[None]
            self.device_box['values']=['系统默认麦克风']
            self.device_box.current(0)
            self.status.set(f'无法列出麦克风：{exc}')

    def aliases(self):
        mapping={}
        for line in self.config.get('aliases','').splitlines():
            if not line.strip():
                continue
            if '=' not in line:
                raise ValueError('姓名设置每行格式：正确姓名=识别结果1|识别结果2')
            canonical, variants=line.split('=',1)
            canonical=compact(canonical)
            validate_name(canonical)
            mapping[canonical]=canonical
            for variant in variants.split('|'):
                if compact(variant):
                    mapping[compact(variant)]=canonical
        return mapping

    def save_config(self):
        self.config['auto']=bool(self.auto.get())
        tmp=self.config_file.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.config,ensure_ascii=False,indent=2),'utf-8')
        os.replace(tmp,self.config_file)

    def edit_aliases(self):
        dialog=tk.Toplevel(self.root)
        dialog.title('姓名纠正设置')
        dialog.geometry('620x380')
        ttk.Label(dialog,text='每行：正确姓名=同音识别结果1|同音识别结果2\n例如：李凌宇=李玲宇|李灵宇\n只会按这里明确设置的对应关系纠正姓名。',padding=12).pack(anchor='w')
        box=tk.Text(dialog,font=('Microsoft YaHei UI',12),height=10)
        box.pack(fill='both',expand=True,padx=12)
        box.insert('1.0',self.config.get('aliases',''))
        def save():
            old=self.config.get('aliases','')
            self.config['aliases']=box.get('1.0','end').strip()
            try:
                self.aliases()
                self.save_config()
                dialog.destroy()
            except Exception as exc:
                self.config['aliases']=old
                messagebox.showerror('设置未保存',str(exc),parent=dialog)
        ttk.Button(dialog,text='保存设置',command=save).pack(pady=12)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_flag.clear()
        self.start_btn['state']='disabled'
        self.stop_btn['state']='normal'
        self.device_box['state']='disabled'
        self.status.set('正在检查麦克风权限和设备…')
        idx=max(self.device_box.current(),0)
        device=self.device_ids[idx]
        self.thread=threading.Thread(target=self.listen,args=(device,),daemon=True)
        self.thread.start()

    def listen(self,device):
        try:
            import sounddevice as sd
            import numpy as np
            rate=check_access(sd,device)
            if self.stop_flag.is_set():
                return
            self.events.put(('status','麦克风可用，正在加载本地语音模型…'))
            if not MODEL.is_dir():
                raise RuntimeError('缺少模型文件夹，请保留完整的“应用”文件夹')
            if self.model is None:
                self.model=load_model(MODEL)
            recognizer,vad,window=self.model
            vad.reset()
            audio=queue.Queue(maxsize=150)
            def callback(data,frames,clock,status):
                if status:
                    self.events.put(('warning',f'麦克风状态：{status}，请检查设备或系统负载'))
                try:
                    if not self.stop_flag.is_set():
                        audio.put_nowait((data[:,0].copy(),time.monotonic()))
                except queue.Full:
                    self.events.put(('fatal_audio','音频处理不及时，已停止聆听；请关闭高负载程序后重新开始'))
                    self.stop_flag.set()
            with sd.InputStream(samplerate=rate,blocksize=int(rate*0.1),device=device,dtype='float32',channels=1,callback=callback):
                if not self.stop_flag.is_set():
                    self.events.put(('status','正在聆听 · 激活文字：记账'))
                buffer=np.zeros(0,dtype=np.float32)
                speaking=False
                flushed_token=None
                def drain_segments(token):
                    nonlocal speaking
                    while not vad.empty():
                        samples=np.asarray(vad.front.samples,dtype=np.float32)
                        vad.pop()
                        text=transcribe(recognizer,samples)
                        if text:
                            self.events.put(('final',(text,token)))
                        speaking=False
                def feed(data,token):
                    nonlocal buffer,speaking
                    if not len(data):
                        return
                    if rate!=16000:
                        data=np.interp(np.arange(int(len(data)*16000/rate))*rate/16000,np.arange(len(data)),data).astype(np.float32)
                    buffer=np.concatenate((buffer,data))
                    while len(buffer)>=window:
                        vad.accept_waveform(buffer[:window])
                        buffer=buffer[window:]
                    if vad.is_speech_detected() and not speaking:
                        self.events.put(('partial','检测到语音，正在累积账目…'))
                        speaking=True
                    drain_segments(token)
                def flush_window(token):
                    nonlocal buffer,speaking,flushed_token
                    if len(buffer):
                        vad.accept_waveform(np.pad(buffer,(0,max(0,window-len(buffer)))))
                    vad.flush()
                    drain_segments(token)
                    self.events.put(('window_done',token))
                    flushed_token=token
                    vad.reset()
                    buffer=np.zeros(0,dtype=np.float32)
                    speaking=False
                while not self.stop_flag.is_set() or not audio.empty():
                    try:
                        data,captured_end=audio.get(timeout=0.1)
                    except queue.Empty:
                        boundary=self.window_boundary
                        if boundary and boundary[0]!=flushed_token and time.monotonic()>=boundary[1]:
                            flush_window(boundary[0])
                        continue
                    boundary=self.window_boundary
                    if boundary and boundary[0]!=flushed_token:
                        token,deadline=boundary
                        if captured_end>=deadline:
                            before,after=split_at_deadline(data,rate,captured_end,deadline)
                            feed(before,token)
                            flush_window(token)
                            feed(after,None)
                        else:
                            feed(data,token)
                    else:
                        feed(data,None)
                boundary=self.window_boundary
                if boundary and boundary[0]!=flushed_token:
                    flush_window(boundary[0])
        except MicrophoneIssue as exc:
            if not self.stop_flag.is_set():
                self.events.put(('microphone_issue',exc))
        except Exception as exc:
            if not self.stop_flag.is_set():
                if 'sd' in locals() and isinstance(exc, sd.PortAudioError):
                    self.events.put(('microphone_issue',audio_issue(exc)))
                else:
                    self.events.put(('error',f'无法启动聆听：{exc}'))
        finally:
            self.events.put(('stopped',''))

    def stop(self):
        if self.window.active:
            self.request_finish()
        self.stop_flag.set()
        self.status.set('正在停止聆听…')
        self.stop_btn['state']='disabled'

    def poll(self):
        microphone_issue=None
        try:
            while True:
                kind,text=self.events.get_nowait()
                if kind=='partial':
                    self.heard.set('正在识别：'+text)
                elif kind=='final':
                    value,token=text
                    if not self.stop_flag.is_set() or (self.window.active and token==self.window.token):
                        self.receive(value,captured_token=token)
                elif kind=='window_done':
                    if self.window.active and text==self.window.token:
                        self.finish_window()
                elif kind=='status' and self.stop_flag.is_set():
                    pass
                elif kind in ('status','warning','fatal_audio','error'):
                    self.status.set(text)
                elif kind=='microphone_issue':
                    microphone_issue=text
                elif kind=='stopped':
                    if self.window.active:
                        self.finish_window()
                    self.start_btn['state']='normal'
                    self.stop_btn['state']='disabled'
                    self.device_box['state']='readonly'
                    if self.status.get().startswith('正在停止'):
                        self.status.set('已停止聆听')
        except queue.Empty:
            pass
        if microphone_issue:
            self.show_microphone_help(microphone_issue)
        self.tick_window()
        self.root.after(100,self.poll)

    def show_microphone_help(self,issue):
        if self.microphone_dialog and self.microphone_dialog.winfo_exists():
            self.microphone_dialog.lift()
            return
        denied=issue.kind in ('denied','denied_system')
        no_device=issue.kind=='no_device'
        title='需要开启麦克风权限' if denied else ('未检测到麦克风' if no_device else '暂时无法使用麦克风')
        self.status.set(title+' · 请按弹窗提示配置后重新检测')
        dialog=tk.Toplevel(self.root)
        self.microphone_dialog=dialog
        dialog.title(title)
        dialog.transient(self.root)
        dialog.resizable(False,False)
        content=ttk.Frame(dialog,padding=20)
        content.pack(fill='both',expand=True)
        ttk.Label(content,text=title,font=('Microsoft YaHei UI',16,'bold')).pack(anchor='w')
        if denied:
            explanation='Windows 当前未允许访问麦克风。点击下方按钮打开系统设置，开启：\n\n① 麦克风访问权限\n② 允许应用访问麦克风\n③ 允许桌面应用访问麦克风\n\n设置完成后，返回这里点击“重新检测并开始”。'
            if issue.kind=='denied_system':
                explanation+='\n如果开关灰色或显示由组织管理，请联系电脑管理员。'
        elif no_device:
            explanation='未检测到可用的麦克风输入设备。请连接麦克风，或在系统声音设置中启用输入设备。\n\n连接完成后，返回这里点击“重新检测并开始”。若仍不可用，也可检查麦克风权限。'
        else:
            explanation='所选麦克风暂时无法打开，可能与权限、设备连接、驱动或其他软件占用有关。\n\n请检查系统麦克风权限和声音输入设备，关闭可能独占麦克风的软件，再点击“重新检测并开始”。'
        ttk.Label(content,text=explanation,wraplength=590,justify='left').pack(anchor='w',pady=(12,14))
        if issue.detail:
            ttk.Label(content,text='检测信息：'+issue.detail,wraplength=590,foreground='#64748B').pack(anchor='w',pady=(0,12))
        self.microphone_message=explanation
        def close_dialog():
            self.microphone_dialog=None
            dialog.destroy()
        def launch(sound=False):
            try:
                open_settings(sound=sound)
            except OSError as exc:
                messagebox.showerror('无法打开系统设置','请手动打开 Windows 设置 → 隐私和安全性 / 隐私 → 麦克风。\n\n'+str(exc),parent=dialog)
        def retry():
            close_dialog()
            self.devices()
            self.start()
        buttons=ttk.Frame(content)
        buttons.pack(fill='x')
        ttk.Button(buttons,text='打开麦克风权限设置',command=launch).pack(side='left')
        ttk.Button(buttons,text='打开声音设置',command=lambda:launch(True)).pack(side='left',padx=8)
        ttk.Button(buttons,text='重新检测并开始',command=retry).pack(side='left')
        ttk.Button(content,text='暂不使用麦克风',command=close_dialog).pack(anchor='e',pady=(12,0))
        dialog.protocol('WM_DELETE_WINDOW',close_dialog)
        dialog.update_idletasks()
        x=self.root.winfo_rootx()+max(0,(self.root.winfo_width()-dialog.winfo_reqwidth())//2)
        y=self.root.winfo_rooty()+max(0,(self.root.winfo_height()-dialog.winfo_reqheight())//2)
        dialog.geometry(f'+{x}+{y}')
        dialog.grab_set()

    def receive(self,text,captured_token=None):
        self.heard.set('识别结果：'+text)
        if not self.window.active and self.preview_token:
            if '记账' in text:
                self.status.set('还有未保存草稿，请先“保存一条”或“清空未保存草稿”，再开启下一次记录')
            return
        if not self.window.accept(text,time.monotonic(),captured_token):
            return
        self.window_boundary=(self.window.token,self.window.deadline)
        self.finish_btn['state']='normal'
        self.name_box['state']='disabled'
        self.entry_box.configure(state='disabled')
        self.raw.set(self.window.text)
        draft_saved=self.persist_draft(self.window.text,self.window.token)
        self.update_preview(self.window.text)
        if draft_saved:
            self.status.set('正在记录两分钟内的全部语音内容，结束时合并为一条账目')
        self.tick_window()

    def update_preview(self,raw):
        try:
            record=parse(raw,self.aliases())
            if record is None:
                return None
            record=(record[0],correct_speech_entry(record[1]))
        except ValueError:
            return None
        self.name.set(record[0]); self.entry.set(record[1])
        return record

    def tick_window(self):
        if not self.window.active:
            return
        if self.awaiting_finish:
            self.countdown.set('正在整理结束前的语音…')
            return
        remaining=self.window.remaining(time.monotonic())
        self.countdown.set(f'本次记录剩余 {remaining//60:02d}:{remaining%60:02d} · 所有内容合并为一行')
        if self.window.due(time.monotonic()) and not self.awaiting_finish:
            self.request_finish(early=False)

    def request_finish(self,early=True):
        if not self.window.active or self.awaiting_finish:
            return
        if early:
            self.window.end_early(time.monotonic())
        self.awaiting_finish=True
        self.window_boundary=(self.window.token,self.window.deadline)
        self.finish_btn['state']='disabled'
        self.countdown.set('正在整理结束前的语音…')
        if not self.thread or not self.thread.is_alive():
            self.finish_window()

    def finish_window(self):
        if not self.window.active:
            return
        raw,token=self.window.text,self.window.token
        self.window.clear()
        self.window_boundary=None
        self.awaiting_finish=False
        self.preview_token=token
        self.finish_btn['state']='disabled'
        self.name_box['state']='normal'
        self.entry_box.configure(state='normal')
        self.countdown.set('本次记录已结束 · 说“记账”可开启下一个两分钟窗口')
        record=self.update_preview(raw)
        if record is None:
            self.status.set('本次内容已保留为草稿，请补全姓名和账目后点击“保存一条”')
            return
        if not self.auto.get():
            self.status.set('两分钟记录已结束，请检查姓名和全部账目，再点击“保存一条”')
            return
        try:
            self.save_record(record,raw,uid=token)
            self.discard_draft()
        except Exception as exc:
            self.status.set('记录已保留为草稿，保存失败：'+str(exc))

    def persist_draft(self,raw,token):
        try:
            tmp=self.draft_file.with_suffix('.tmp')
            tmp.write_text(json.dumps({'raw':raw,'token':token},ensure_ascii=False),'utf-8')
            os.replace(tmp,self.draft_file)
            return True
        except OSError as exc:
            self.status.set('暂时无法保存恢复草稿：'+str(exc))
            return False

    def restore_draft(self):
        try:
            data=json.loads(self.draft_file.read_text('utf-8'))
            raw,token=data['raw'],data['token']
            if not isinstance(raw,str) or not isinstance(token,str):
                return
            if self.ledger.db.execute('SELECT id FROM events WHERE id=?',(token,)).fetchone():
                self.discard_draft()
                return
            self.preview_token=token
            self.raw.set(raw)
            self.update_preview(raw)
            self.status.set('已恢复上次未完成的语音草稿，请检查后“保存一条”，或清空草稿')
            self.countdown.set('上次草稿已恢复，等待你确认')
        except (OSError,ValueError,KeyError):
            pass

    def discard_draft(self):
        self.draft_file.unlink(missing_ok=True)
        self.preview_token=None

    def clear_draft(self):
        if self.window.active:
            messagebox.showinfo('正在记录','请先结束本次记录，再清空未保存草稿。')
            return
        try:
            self.discard_draft()
            self.name.set('');self.entry.set('');self.raw.set('')
            self.status.set('未保存草稿已清空，已入账的记录仍保留')
            self.countdown.set('等待激活 · 说“记账”后连续记录两分钟')
        except OSError as exc:
            messagebox.showerror('无法清空草稿',str(exc))

    def parse_manual(self):
        if self.window.active:
            messagebox.showinfo('正在记录','请先结束本次记录；如需检查后再写入，可取消自动写入。')
            return
        try:
            record=parse(self.raw.get(),self.aliases())
            if record is None:
                raise ValueError('文字中必须包含激活文字“记账”')
            self.name.set(record[0]); self.entry.set(record[1])
            self.status.set('文字已解析，请检查后点击“保存一条”')
        except Exception as exc:
            messagebox.showerror('无法解析',str(exc))

    def save_manual(self):
        if self.window.active:
            self.request_finish()
            return
        try:
            name=compact(self.name.get())
            name=self.aliases().get(name,name)
            validate_name(name)
            record=(name,normalize_entry(self.entry_box.get('1.0','end-1c')))
            self.save_record(record,self.raw.get(),uid=self.preview_token)
            self.discard_draft()
        except Exception as exc:
            messagebox.showerror('无法保存',str(exc))

    def save_record(self,record,raw,uid=None):
        uid=self.ledger.enqueue(*record,raw=raw,uid=uid)
        row=next(x for x in self.ledger.recent() if x[0]==uid)
        if row[4]:
            self.status.set(f'已写入：{record[0]} · {record[1]}')
            try:
                import winsound
                winsound.MessageBeep(winsound.MB_OK)
            except Exception:
                pass
        else:
            self.status.set('已保留到本地待写入队列：'+row[5])
        self.refresh()

    def refresh(self):
        self.table.delete(*self.table.get_children())
        for row in self.ledger.recent():
            self.table.insert('', 'end',iid=row[0],values=(*row[1:4], '已写入' if row[4] else '待写入：'+row[5]))

    def retry(self):
        self.ledger.retry()
        self.refresh()
        pending=sum(not x[4] for x in self.ledger.recent())
        self.status.set(f'重试完成，最近记录中有 {pending} 条待写入' if pending else '重试完成，所有记录已写入')

    def open_folder(self):
        try:
            self.ledger.root.mkdir(parents=True,exist_ok=True)
            os.startfile(self.ledger.root)
        except Exception as exc:
            messagebox.showerror('无法打开',str(exc))

    def close(self):
        self.stop_flag.set()
        if self.window.active:
            self.finish_window()
        self.ledger.close()
        self.root.destroy()

def main():
    if '--self-test' in sys.argv:
        from selftest import run
        report=Path(sys.argv[sys.argv.index('--self-test')+1])
        audio=Path(sys.argv[sys.argv.index('--audio')+1]) if '--audio' in sys.argv else None
        try:
            result=run(MODEL,audio)
        except Exception as exc:
            result={'passed':False,'error':repr(exc)}
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
        return
    mutex=None
    if os.name=='nt':
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.CreateMutexW.restype=ctypes.c_void_p
        mutex=kernel.CreateMutexW(None,False,'Local\\OfflineVoiceLedger_v1')
        if ctypes.get_last_error()==183:
            ctypes.windll.user32.MessageBoxW(None,'离线语音记账已经在运行，请切换到已打开的窗口。','离线语音记账',0)
            return
    root=tk.Tk()
    try:
        App(root)
        root.mainloop()
    except Exception as exc:
        messagebox.showerror('程序错误',str(exc))
    finally:
        if mutex:
            kernel.CloseHandle.argtypes=[ctypes.c_void_p]
            kernel.CloseHandle(mutex)

if __name__=='__main__':
    main()
