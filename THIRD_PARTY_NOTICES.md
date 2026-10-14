# 第三方组件与模型

本仓库的根 LICENSE 仅适用于本项目自写代码和文档，不覆盖第三方库、模型、声音、商标及其许可证文件。

当前源码依赖 sherpa-onnx、NumPy、sounddevice、openpyxl 等库。`源码/requirements.txt` 记录已使用的直接依赖版本，`许可证/` 保留收集到的第三方版权和许可文本。本仓库不包含这些库的二进制分发包。

## SenseVoice：代码许可与模型许可分开处理

原组件清单误将 SenseVoice Small 模型标为 Apache-2.0，已于 2026-10-14 更正。

- 本机 ONNX 模型来自 sherpa-onnx 的 SenseVoice 转换模型系列。模型附带的 LICENSE 指向 FunASR 的许可说明。
- 模型提供方的 [SenseVoiceSmall 模型页面](https://huggingface.co/FunAudioLLM/SenseVoiceSmall) 标注 `model-license`。
- [转换模型的 LICENSE](https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/blob/main/LICENSE) 指向 FunASR。
- 对应的 [FunASR MODEL_LICENSE](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) 是独立模型协议，不能用代码库的 MIT 或 sherpa-onnx 的 Apache-2.0 替代。
- `许可证/SenseVoice/MODEL_LICENSE` 保存了 2026-10-14 获取的当前协议文本，版本 1.1，SHA-256：`7dba975a2069691db4992b0592d70828b330d2f8a30a71450f4e152a554e84f8`。实际使用及再分发前应核对所下载模型对应的协议。
- `许可证/SenseVoice/LICENSE.txt` 是 SenseVoice 代码库的 MIT 文本，不能当作模型权重许可证。

模型原作者：FunAudioLLM / FunASR（阿里巴巴团队）；ONNX 转换发布方：k2-fsa / sherpa-onnx。模型名称：SenseVoice Small。当前仓库不附带权重、词表或音频。

## 其他来源

- sherpa-onnx：[上游](https://github.com/k2-fsa/sherpa-onnx)，Apache-2.0。
- Silero VAD：[上游许可](https://github.com/snakers4/silero-vad/blob/master/LICENSE)，MIT。
- NumPy：许可见 `许可证/numpy/`；其 Windows 二进制还附带 OpenBLAS 等独立组件说明。
- sounddevice、PortAudio、openpyxl、cffi、pycparser、et-xmlfile、Python、Tcl/Tk、ONNX Runtime：保留在 `许可证/` 下的各自文本。

## 发布完整 EXE 的额外检查

源码公开与打包全部依赖再分发不是同一件事。现有完整程序含 Python、OpenSSL、ONNX Runtime、PyInstaller bootloader、Windows 运行库等；仍需逐项确认所打包版本的许可、第三方 NOTICE 和再分发条件。现有许可目录不代表已经完成全部二进制依赖审计。因此本次只提供源码上传目录，不把现成完整程序认定为已经完成发布合规检查。
