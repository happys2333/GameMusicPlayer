import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk
import pygame
import pygame._sdl2.audio as sdl2_audio
from pynput import keyboard
import json
import os
import random
import threading

import sys
CONFIG_FILE = "soundboard_config.json"
def get_resource_path(relative_path):

    if hasattr(sys, '_MEIPASS'):

        return os.path.join(sys._MEIPASS, relative_path)

    return os.path.join(os.path.abspath("."), relative_path)


class GameMusicPlayer:
    def __init__(self, root):
        self.root = root
        self.root.title("GameMusicPlayer")
        self.root.geometry("700x450")
        self.root.eval('tk::PlaceWindow . center')

        pygame.init()

        self.config_data = {
            "output_device": None,
            "bindings": {},
            "volume": 0.8
        }
        self.temp_filepaths = []


        self.current_pressed = set()
        self.hotkey_states = {}
        self.is_recording = False

        self.load_config()
        self.init_audio_mixer()
        self.setup_ui()
        self.update_volume_setting()
        self.refresh_treeview()

        self.start_global_listener()



    def init_audio_mixer(self):
        if pygame.mixer.get_init():
            pygame.mixer.quit()

        device_name = self.config_data.get("output_device")
        try:
            pygame.mixer.init(devicename=device_name)
            pygame.mixer.music.set_volume(self.config_data["volume"])
        except:
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self.config_data["volume"])

    def key_to_str(self, key):

        if hasattr(key, 'vk') and key.vk is not None:
            if 96 <= key.vk <= 105:
                return f"numpad_{key.vk - 96}"

        if hasattr(key, 'char') and key.char:
            return str(key.char).lower()

        if hasattr(key, 'name') and key.name:
            name = str(key.name).replace("_l", "").replace("_r", "")
            return name

        return str(key)

    def start_global_listener(self):
        def on_press(key):
            key_str = self.key_to_str(key)
            self.current_pressed.add(key_str)
            self.check_hotkeys()

        def on_release(key):
            key_str = self.key_to_str(key)
            if key_str in self.current_pressed:
                self.current_pressed.remove(key_str)
            for hotkey in self.hotkey_states:
                if hotkey not in self.current_pressed:
                    self.hotkey_states[hotkey] = False

        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.start()

    def check_hotkeys(self):

        if self.is_recording: return

        for hotkey, files in self.config_data["bindings"].items():
            target_keys = set(hotkey.split('+'))

            if target_keys.issubset(self.current_pressed):

                if not self.hotkey_states.get(hotkey, False):
                    self.hotkey_states[hotkey] = True
                    self.root.after(0, self.play_or_stop, hotkey)
            else:
                self.hotkey_states[hotkey] = False

    # =======================================================

    def setup_ui(self):
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill=tk.X, padx=10)

        tk.Label(top_frame, text="快捷键:").grid(row=0, column=0, sticky=tk.W)

        self.hotkey_var = tk.StringVar()
        self.entry_hotkey = tk.Entry(top_frame, textvariable=self.hotkey_var, width=15, state='readonly')
        self.entry_hotkey.grid(row=0, column=1, padx=5)

        self.btn_capture = tk.Button(top_frame, text="⌨️ 录制", command=self.start_capture, bg="#e2e3e5")
        self.btn_capture.grid(row=0, column=2, padx=5)

        self.btn_select = tk.Button(top_frame, text="🎵 选音效", command=self.select_files)
        self.btn_select.grid(row=0, column=3, padx=5)

        self.btn_bind = tk.Button(top_frame, text="➕ 绑定", command=self.add_binding, bg="#d4edda")
        self.btn_bind.grid(row=0, column=4, padx=5)

        self.btn_delete = tk.Button(top_frame, text="🗑️ 删除整条", command=self.delete_binding, bg="#f8d7da")
        self.btn_delete.grid(row=0, column=5, padx=5)

        self.btn_settings = tk.Button(top_frame, text="⚙️ 设 置", command=self.open_settings, bg="#cce5ff")
        self.btn_settings.grid(row=0, column=6, padx=5)

        self.lbl_selected_files = tk.Label(top_frame, text="未选择文件", fg="gray")
        self.lbl_selected_files.grid(row=1, column=0, columnspan=7, pady=5, sticky=tk.W)

        device_frame = tk.Frame(self.root)
        device_frame.pack(fill=tk.X, padx=10)
        curr_dev = self.config_data.get("output_device") or "系统默认设备"
        self.lbl_curr_device = tk.Label(device_frame, text=f"当前输出设备: {curr_dev}", fg="#155724", bg="#d4edda")
        self.lbl_curr_device.pack(fill=tk.X, pady=2)

        volume_frame = tk.Frame(self.root, pady=10)
        volume_frame.pack(fill=tk.X, padx=10)

        tk.Label(volume_frame, text="播放音量调节 (0-100%):").pack(side=tk.LEFT)

        self.volume_var = tk.DoubleVar()
        self.volume_var.set(int(self.config_data["volume"] * 100))

        self.volume_slider = ttk.Scale(
            volume_frame,
            variable=self.volume_var,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            length=250,
            command=self.update_volume_setting
        )
        self.volume_slider.pack(side=tk.LEFT, padx=10)

        self.lbl_volume_percent = tk.Label(volume_frame, text=f"{int(self.volume_var.get())}%", width=5)
        self.lbl_volume_percent.pack(side=tk.LEFT)

        list_frame = tk.Frame(self.root)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        columns = ("hotkey", "count", "paths")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.tree.heading("hotkey", text="快捷键")
        self.tree.heading("count", text="数量 (双击管理)")
        self.tree.heading("paths", text="文件路径摘要")

        self.tree.column("hotkey", width=120, anchor=tk.CENTER)
        self.tree.column("count", width=120, anchor=tk.CENTER)
        self.tree.column("paths", width=350, anchor=tk.W)
        self.tree.pack(fill=tk.BOTH, expand=True)

        self.tree.bind("<Double-1>", self.open_song_manager)

    def open_song_manager(self, event):
        selected = self.tree.selection()
        if not selected: return

        hotkey = str(self.tree.item(selected[0])['values'][0])
        files = self.config_data["bindings"].get(hotkey, [])
        if not files: return

        manager_win = tk.Toplevel(self.root)
        manager_win.title(f"管理音效 - 快捷键: {hotkey}")

        win_width, win_height = 500, 300
        manager_win.transient(self.root)
        self.root.update_idletasks()
        pos_x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (win_width // 2)
        pos_y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (win_height // 2)
        manager_win.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        manager_win.grab_set()

        if hasattr(self, 'icon_image'):
            try:
                manager_win.iconphoto(False, self.icon_image)
            except:
                pass

        tk.Label(manager_win, text=f"当前【{hotkey}】绑定的所有音效文件：").pack(pady=5)

        frame = tk.Frame(manager_win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, width=60, selectbackground="#007bff")
        for f in files: listbox.insert(tk.END, f)
        listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=listbox.yview)

        def delete_selected_song():
            selected_idx = listbox.curselection()
            if not selected_idx:
                messagebox.showwarning("提示", "请先在列表中点击选中要删除的歌曲！", parent=manager_win)
                return

            idx = selected_idx[0]
            song_path = listbox.get(idx)

            self.config_data["bindings"][hotkey].remove(song_path)
            listbox.delete(idx)

            if len(self.config_data["bindings"][hotkey]) == 0:
                del self.config_data["bindings"][hotkey]
                messagebox.showinfo("提示", "该快捷键下已无音效，快捷键已被移除。", parent=manager_win)
                manager_win.destroy()

            self.save_config()
            self.refresh_treeview()

        btn_del = tk.Button(manager_win, text="🗑️ 删除选中的这首歌", command=delete_selected_song, bg="#f8d7da")
        btn_del.pack(pady=10)

    def open_settings(self):
        settings_win = tk.Toplevel(self.root)
        settings_win.title("输出设备设置")

        win_width = 400
        win_height = 150
        settings_win.transient(self.root)
        self.root.update_idletasks()
        root_x = self.root.winfo_x()
        root_y = self.root.winfo_y()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        pos_x = root_x + (root_width // 2) - (win_width // 2)
        pos_y = root_y + (root_height // 2) - (win_height // 2)
        settings_win.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        settings_win.grab_set()

        if hasattr(self, 'icon_image'):
            try:
                settings_win.iconphoto(False, self.icon_image)
            except:
                pass

        tk.Label(settings_win, text="请选择音频输出设备 (选择后立即生效):").pack(pady=10)

        try:
            devices = sdl2_audio.get_audio_device_names(False)
        except:
            devices = ["获取设备失败"]

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

    def update_volume_setting(self, event=None):
        slider_val = self.volume_var.get()
        volume_float = slider_val / 100.0
        pygame.mixer.music.set_volume(volume_float)
        self.lbl_volume_percent.config(text=f"{int(slider_val)}%")
        self.config_data["volume"] = volume_float

        if event is None:
            if hasattr(self, '_save_timer'):
                self.root.after_cancel(self._save_timer)
            self._save_timer = self.root.after(500, self.save_config)

    def start_capture(self):
        self.btn_capture.config(text="🔴 请按下组合键...", state=tk.DISABLED, bg="#ffc107")
        self.hotkey_var.set("")
        self.is_recording = True

        def worker():
            recorded = set()

            def on_press(key):
                recorded.add(self.key_to_str(key))

            def on_release(key):
                return False

            with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
                l.join()

            hotkey_str = '+'.join(recorded)
            self.root.after(0, self.finish_capture, hotkey_str)

        threading.Thread(target=worker, daemon=True).start()

    def finish_capture(self, hotkey):
        self.is_recording = False  # 解除录制状态锁
        if hotkey and 'esc' not in hotkey:
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

    def delete_binding(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("提示", "请先在下方列表中点击选中一条记录！")
            return

        hotkey = str(self.tree.item(selected[0])['values'][0])
        if hotkey in self.config_data["bindings"]:
            if messagebox.askyesno("确认删除", f"确定要删除快捷键【{hotkey}】及其绑定的所有音效吗？"):
                del self.config_data["bindings"][hotkey]
                self.save_config()
                self.refresh_treeview()

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
                    pygame.mixer.music.set_volume(self.config_data["volume"])
                    pygame.mixer.music.play()
                except:
                    pass

    def save_config(self):
        if not hasattr(self, 'root'): return
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config_data, f, ensure_ascii=False, indent=4)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                if "bindings" not in data:
                    self.config_data["bindings"] = data
                    self.config_data["output_device"] = None
                    self.config_data["volume"] = 0.8
                    self.save_config()
                else:
                    self.config_data = data
                    if "volume" not in self.config_data:
                        self.config_data["volume"] = 0.8
            except:
                pass

    def refresh_treeview(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for hotkey, files in self.config_data["bindings"].items():
            count = len(files)
            summary = os.path.basename(files[0]) + (f" 等共 {count} 首" if count > 1 else "")
            self.tree.insert("", tk.END, values=(hotkey, count, summary))


if __name__ == "__main__":
    root = tk.Tk()
    img = tk.PhotoImage(file=get_resource_path("logo.png"))
    root.iconphoto(False, img)
    app = GameMusicPlayer(root)
    root.mainloop()