import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pygame
import pygame._sdl2.audio as sdl2_audio  # 新增：用于获取底层音频设备列表
import keyboard
import json
import os
import random
import threading

CONFIG_FILE = "soundboard_config.json"


class AdvancedSoundboard:
    def __init__(self, root):
        self.root = root
        self.root.title("Pro Meme 音效板 (多设备输出版)")
        self.root.geometry("700x450")
        self.root.eval('tk::PlaceWindow . center')

        # 核心：必须先初始化 pygame 基础模块，才能扫描音频设备
        pygame.init()

        # 数据结构升级
        self.config_data = {
            "output_device": None,  # 保存用户选择的设备名称
            "bindings": {}  # 保存快捷键字典
        }
        self.temp_filepaths = []

        self.load_config()  # 先读取配置（获取设备名）
        self.init_audio_mixer()  # 根据配置初始化混音器

        self.setup_ui()
        self.refresh_treeview()
        self.register_hotkeys()

    def init_audio_mixer(self):
        """初始化或重新初始化音频引擎"""
        # 如果之前初始化过，先退出
        if pygame.mixer.get_init():
            pygame.mixer.quit()

        device_name = self.config_data.get("output_device")
        try:
            # 尝试使用指定的设备启动
            if device_name:
                pygame.mixer.init(devicename=device_name)
                print(f"🔈 已连接到音频设备: {device_name}")
            else:
                pygame.mixer.init()
                print("🔈 已连接到默认音频设备")
        except Exception as e:
            print(f"⚠️ 连接设备 '{device_name}' 失败，退回默认设备。原因: {e}")
            pygame.mixer.init()

    def setup_ui(self):
        # --- 顶部控制区 ---
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill=tk.X, padx=10)

        tk.Label(top_frame, text="快捷键:").grid(row=0, column=0, sticky=tk.W)

        self.hotkey_var = tk.StringVar()
        self.entry_hotkey = tk.Entry(top_frame, textvariable=self.hotkey_var, width=12, state='readonly')
        self.entry_hotkey.grid(row=0, column=1, padx=5)

        self.btn_capture = tk.Button(top_frame, text="⌨️ 录制", command=self.start_capture, bg="#e2e3e5")
        self.btn_capture.grid(row=0, column=2, padx=5)

        self.btn_select = tk.Button(top_frame, text="🎵 选音效", command=self.select_files)
        self.btn_select.grid(row=0, column=3, padx=5)

        self.btn_bind = tk.Button(top_frame, text="➕ 绑定", command=self.add_binding, bg="#d4edda")
        self.btn_bind.grid(row=0, column=4, padx=5)

        self.btn_delete = tk.Button(top_frame, text="🗑️ 删除", command=self.delete_binding, bg="#f8d7da")
        self.btn_delete.grid(row=0, column=5, padx=5)

        # 新增：设置按钮
        self.btn_settings = tk.Button(top_frame, text="⚙️ 设 置", command=self.open_settings, bg="#cce5ff")
        self.btn_settings.grid(row=0, column=6, padx=5)

        self.lbl_selected_files = tk.Label(top_frame, text="未选择文件", fg="gray")
        self.lbl_selected_files.grid(row=1, column=0, columnspan=7, pady=5, sticky=tk.W)

        # --- 当前设备显示区 ---
        device_frame = tk.Frame(self.root)
        device_frame.pack(fill=tk.X, padx=10)
        curr_dev = self.config_data.get("output_device") or "系统默认设备"
        self.lbl_curr_device = tk.Label(device_frame, text=f"当前输出设备: {curr_dev}", fg="#155724", bg="#d4edda")
        self.lbl_curr_device.pack(fill=tk.X, pady=2)

        # --- 底部列表区 ---
        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("hotkey", "count", "paths")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.tree.heading("hotkey", text="快捷键")
        self.tree.heading("count", text="数量")
        self.tree.heading("paths", text="文件路径摘要")

        self.tree.column("hotkey", width=100, anchor=tk.CENTER)
        self.tree.column("count", width=50, anchor=tk.CENTER)
        self.tree.column("paths", width=350, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)


    def open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("输出设备设置")

        # 1. 设定子窗口的宽高
        win_width = 400
        win_height = 150

        # 2. 将其设置为“临时对话框”（始终在主窗口上方，且随主窗口一起最小化）
        settings_win.transient(self.root)

        # 3. 强制刷新界面，确保主窗口当前的尺寸和坐标是最新的
        self.root.update_idletasks()

        # 4. 获取主窗口的尺寸和在屏幕上的坐标
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        # 5. 计算子窗口相对主窗口居中的完美坐标
        pos_x = root_x + (root_width // 2) - (win_width // 2)
        pos_y = root_y + (root_height // 2) - (win_height // 2)

        # 6. 应用尺寸和计算好的屏幕坐标
        settings_win.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")

        # 7. 模态窗口：锁定主窗口，必须先关掉设置才能点主界面
        settings_win.grab_set()

        tk.Label(settings_win, text="请选择音频输出设备 (选择后立即生效):").pack(pady=10)

        # 获取系统所有的输出设备列表
        try:
            devices = sdl2_audio.get_audio_device_names(False)
        except Exception as e:
            devices = ["获取设备失败"]
            print(e)

        devices.insert(0, "系统默认设备")

        device_combo = ttk.Combobox(settings_win, values=devices, state="readonly", width=40)
        curr = self.config_data.get("output_device")
        if curr in devices:
            device_combo.set(curr)
        else:
            device_combo.set("系统默认设备")
        device_combo.pack(pady=5)

        def save_and_apply():
            selected = device_combo.get()
            if selected == "系统默认设备" or selected == "获取设备失败":
                self.config_data["output_device"] = None
            else:
                self.config_data["output_device"] = selected

            display_name = selected if selected != "系统默认设备" else "系统默认设备"
            self.lbl_curr_device.config(text=f"当前输出设备: {display_name}")

            self.save_config()
            self.init_audio_mixer()
            settings_win.destroy()

        tk.Button(settings_win, text="保存并应用", command=save_and_apply, bg="#007bff", fg="white").pack(pady=10)
    # --- 原有逻辑适配更新 ---
    def start_capture(self):
        self.btn_capture.config(text="🔴 请按下组合键...", state=tk.DISABLED, bg="#ffc107")
        self.hotkey_var.set("")

        def worker():
            hotkey = keyboard.read_hotkey(suppress=False)
            self.root.after(0, self.finish_capture, hotkey)

        threading.Thread(target=worker, daemon=True).start()

    def finish_capture(self, hotkey):
        if hotkey != 'esc':
            self.hotkey_var.set(hotkey)
        self.btn_capture.config(text="⌨️ 录制", state=tk.NORMAL, bg="#e2e3e5")

    def select_files(self):
        filepaths = filedialog.askopenfilenames(
            title="选择音效",
            initialdir=os.getcwd(),
            filetypes=[("Audio Files", "*.mp3 *.wav"), ("All Files", "*.*")]
        )
        if filepaths:
            self.temp_filepaths = list(filepaths)
            self.lbl_selected_files.config(text=f"已选择 {len(self.temp_filepaths)} 个文件", fg="blue")

    def add_binding(self):
        hotkey = self.hotkey_var.get().strip().lower()
        if not hotkey or not self.temp_filepaths:
            messagebox.showwarning("提示", "请先录制快捷键并选择音频！")
            return

        bindings = self.config_data["bindings"]
        if hotkey in bindings:
            bindings[hotkey].extend(self.temp_filepaths)
            bindings[hotkey] = list(set(bindings[hotkey]))
        else:
            bindings[hotkey] = self.temp_filepaths

        self.hotkey_var.set("")
        self.temp_filepaths = []
        self.lbl_selected_files.config(text="未选择文件", fg="gray")

        self.save_config()
        self.refresh_treeview()
        self.register_hotkeys()

    def delete_binding(self):
        selected = self.tree.selection()
        if not selected: return

        hotkey = self.tree.item(selected)['values'][0]
        if hotkey in self.config_data["bindings"]:
            del self.config_data["bindings"][hotkey]
            self.save_config()
            self.refresh_treeview()
            self.register_hotkeys()

    def play_or_stop(self, hotkey):
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            return

        files = self.config_data["bindings"].get(hotkey)
        if files:
            chosen_file = random.choice(files)
            if os.path.exists(chosen_file):
                try:
                    pygame.mixer.music.load(chosen_file)
                    pygame.mixer.music.play()
                except Exception as e:
                    print(f"播放出错: {e}")

    def register_hotkeys(self):
        keyboard.unhook_all()
        for hotkey in self.config_data["bindings"].keys():
            try:
                keyboard.add_hotkey(hotkey, lambda hk=hotkey: self.play_or_stop(hk))
            except Exception as e:
                print(f"无法绑定快捷键 {hotkey}: {e}")

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, ensure_ascii=False, indent=4)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 兼容旧版本配置 (如果读取到的是纯字典，则自动迁移)
                if "bindings" not in data:
                    print("检测到旧版配置，正在自动升级...")
                    self.config_data["bindings"] = data
                    self.save_config()
                else:
                    self.config_data = data
            except Exception as e:
                print(f"读取配置失败: {e}")

    def refresh_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for hotkey, files in self.config_data["bindings"].items():
            count = len(files)
            summary = os.path.basename(files[0]) + (f" 等共 {count} 首" if count > 1 else "")
            self.tree.insert("", tk.END, values=(hotkey, count, summary))


if __name__ == "__main__":
    root = tk.Tk()
    app = AdvancedSoundboard(root)
    root.mainloop()