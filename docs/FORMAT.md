# 曲谱与场景配置

`.reedscore.json` 保存 `schema_version=1`、标题、总时长、参考 BPM、参考 A4 频率、元数据和音符列表。每个音符记录绝对 `start_ms`、`duration_ms`、`midi_pitch`、力度、模型分数、声部、音分偏差与唯一标识。BPM 当前不自动估计，默认 120 只是参考；MIDI 导出按绝对时间写入，不量化、不移调。文本简谱采用固定 `1=C4` 并逐音记录秒数和时长。

`notes` 是当前编辑结果，`original_notes` 是转写时的完整候选备份。元数据记录引擎版本、波形概览与原始弯音数据；`confidence` 是模型激活值，不是准确概率。MIDI 导出采用一毫秒一 tick，仅导出当前音符的离散音高和时值，亚毫秒时值至少保留一 tick；弯音曲线仍保存在 JSON 中。

场景 JSON 保存 8 个基础音高及键位、3 个修饰输入及半音值、允许的组合、A4 参考频率和 4 个全局热键。鼠标输入使用 `MOUSE_LEFT / MOUSE_MIDDLE / MOUSE_RIGHT`；普通键写 `Z`、`,`、`F8` 等。热键支持 `CTRL+ALT+F8` 等组合。

内置口琴的 C4–C5 与 -12/+1/+12 半音来自现有实录与音阶推断，可直接使用。`pitch_source` 为 `sample-inferred`、`custom` 或 `measured`；缺少该字段的旧文件自动按原配置迁移。`calibrated` 保留兼容，不再限制真实游戏输入。高级音高编辑会将来源改为 `custom`。原曲谱始终保留；演奏移调、主旋律提取与跳过音域外音须显式开启。

`examples/晨风.reedscore.json` 是项目自制短旋律，供独立启动与预演使用。本地样例 MP3 及其派生内容不提交仓库。

演奏偏好中的 `long_policy` 为 `hold` 或 `rearticulate`，`repeat_gap` 为实际毫秒。同音间隔和长音分段仅改变临时演奏计划，不覆盖曲谱；变化后的事件起点仍按源时间轴调度。试听渲染速度只缩放时间，不改变频率。

`repair_minimum` / `repair_gap` 为碎音过滤与小间隙衔接的毫秒阈值（默认 80 / 50），`repair_merge` 控制相邻同音合并（默认 false）。主旋律转换采用这些参数；`metadata.melody_repair` 记录转换使用值。手动修整改变当前 `notes` 并可撤销，`original_notes` 保留完整候选；将阈值设为 0 可保留快速音符和真实小休止。

`melody_minimum` / `melody_maximum` 保存旋律候选的 MIDI 音域（默认 0 / 127），不改音高；新转写的 `metadata.melody_selection` 记录 `register-path-v2` 与范围。完整候选不受范围影响。`metadata.pitch_policy` 说明新 Basic Pitch 候选按 MIDI 半音发声，`pitch_bends_third_semitone` 仅保留原始分析数据，不直接转成可信的 `Note.cents`。手工和其他来源的音分仍由 `Note.cents` 保存。

程序旁 `storage-location.json` 的 `directory` 保存数据目录绝对路径；该文件和用户数据不提交 Git。切换目录复制持久文件并重写目录内绝对路径，不覆盖有不同内容的目标文件，不搬走或删除原目录。
