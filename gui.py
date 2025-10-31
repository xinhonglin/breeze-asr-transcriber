from customtkinter import *
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import subprocess
import threading
import os
import sys
import platform
from datetime import datetime
from typing import Optional

# 可選：首次使用時提示下載模型
try:
    from huggingface_hub import snapshot_download
    HF_AVAILABLE = True
except Exception:
    HF_AVAILABLE = False


class AudioConverterApp:
    def __init__(self):
        self.app = CTk()
        self.app.geometry("700x600")
        self.app.title("音檔轉逐字稿")
        set_appearance_mode("Dark")
        
        # 應用程式狀態
        self.selected_file_path = None
        self.is_converting = False
        self.conversion_thread = None
        self.current_process = None
        # 決定編碼方式（使用系統預設編碼，避免跨平台問題）
        # 在 Windows 打包環境中 sys.stdout 可能是 None
        self.encoding = getattr(sys.stdout, 'encoding', None) or 'utf-8'
        
        self.setup_window()
        self.create_widgets()
        
        # 設定視窗關閉時的處理
        self.app.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        self.app.mainloop()
    
    def setup_window(self):
        """設定視窗位置至螢幕中央"""
        # 固定視窗尺寸
        window_width, window_height = 700, 600
        
        screen_width = self.app.winfo_screenwidth()
        screen_height = self.app.winfo_screenheight()
        
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        
        self.app.geometry(f"{window_width}x{window_height}+{x}+{y}")
    
    def create_widgets(self):
        """建立 UI 元件"""
        # 主容器
        main_container = CTkFrame(self.app)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)
        
        # 標題
        self.title_label = CTkLabel(
            main_container,
            text="歡迎使用音檔轉逐字稿工具",
            font=("微軟正黑體", 16),
            text_color="white"
        )
        self.title_label.pack(pady=(0, 15))
        
        # 按鈕區域
        button_frame = CTkFrame(main_container)
        button_frame.pack(pady=(0, 10))
        
        self.upload_btn = CTkButton(
            button_frame,
            text="上傳音檔",
            corner_radius=20,
            command=self.upload_audio,
            width=120
        )
        self.upload_btn.pack(side="left", padx=10)
        
        self.convert_btn = CTkButton(
            button_frame,
            text="開始轉換",
            corner_radius=20,
            command=self.start_conversion,
            state="disabled",
            fg_color="gray",
            width=120
        )
        self.convert_btn.pack(side="left", padx=10)
        
        self.cancel_btn = CTkButton(
            button_frame,
            text="取消轉換",
            corner_radius=20,
            command=self.cancel_conversion,
            state="disabled",
            fg_color="#cc5555",
            width=120
        )
        self.cancel_btn.pack(side="left", padx=10)
        
        # 狀態標籤
        self.status_label = CTkLabel(
            main_container,
            text="",
            font=("微軟正黑體", 10),
            text_color="#cccccc"
        )
        self.status_label.pack(pady=(0, 10))

        # 首次模型下載提示（預設隱藏）
        self.model_frame = CTkFrame(main_container)
        self.model_frame.pack(fill="x", pady=(0, 10))
        self.model_frame.pack_forget()

        self.model_label = CTkLabel(
            self.model_frame,
            text="",
            font=("微軟正黑體", 11),
            text_color="#dddddd",
            anchor="w",
            justify="left"
        )
        self.model_label.pack(anchor="w", pady=(0, 6))

        self.model_progress = CTkProgressBar(
            self.model_frame,
            mode="indeterminate",
            width=400
        )
        self.model_progress.pack(anchor="w")
        
        # 輸出區域容器
        output_label = CTkLabel(
            main_container,
            text="執行輸出：",
            font=("微軟正黑體", 12)
        )
        output_label.pack(anchor="w", pady=(10, 5))
        
        # 使用 Frame 來正確包含 Text 和 Scrollbar
        output_frame = CTkFrame(main_container)
        output_frame.pack(fill="both", expand=True, pady=(0, 10))
        
        self.output_text = tk.Text(
            output_frame,
            wrap="word",
            bg="#2b2b2b",
            fg="white",
            font=("Consolas", 10),
            state="disabled"
        )
        self.output_text.pack(side="left", fill="both", expand=True)
        
        # 正確綁定滾動條
        scrollbar = tk.Scrollbar(output_frame, command=self.output_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.output_text.configure(yscrollcommand=scrollbar.set)
    
    def update_button_states(self, uploading=None, converting=None, canceling=None):
        """集中管理按鈕狀態
        參數：
        - uploading: 是否啟用「上傳音檔」按鈕
        - converting: 是否啟用「開始轉換」按鈕
        - canceling: 是否啟用「取消轉換」按鈕（若為 None，則依 converting 推斷）
        """
        if uploading is not None:
            state = "normal" if uploading else "disabled"
            color = "#1f6aa5" if uploading else "gray"
            self.upload_btn.configure(state=state, fg_color=color)

        if converting is not None:
            state = "normal" if converting else "disabled"
            color = "#1f6aa5" if converting else "gray"
            self.convert_btn.configure(state=state, fg_color=color)

        # 取消按鈕：優先使用 canceling；否則遵循 converting 的狀態
        if canceling is not None:
            cancel_state = "normal" if canceling else "disabled"
            cancel_color = "#cc5555" if canceling else "gray"
            self.cancel_btn.configure(state=cancel_state, fg_color=cancel_color)
        elif converting is not None:
            cancel_state = "normal" if converting else "disabled"
            cancel_color = "#cc5555" if converting else "gray"
            self.cancel_btn.configure(state=cancel_state, fg_color=cancel_color)
    
    def update_status(self, text):
        """更新狀態標籤"""
        self.status_label.configure(text=text)
    
    def upload_audio(self):
        """選擇音檔"""
        file_path = filedialog.askopenfilename(
            title="選擇音檔",
            filetypes=[("Audio Files", "*.mp3 *.wav *.m4a"), ("All Files", "*.*")]
        )
        
        if not file_path:
            return
        
        # 驗證檔案是否存在且可讀
        if not self._validate_file(file_path):
            return
        
        self.selected_file_path = file_path
        file_name = Path(file_path).name
        file_size = self._get_file_size(file_path)
        
        self.title_label.configure(text=f"你已選擇音檔: {file_name} ({file_size})")
        self.update_button_states(uploading=False, converting=True, canceling=False)
        self.clear_output()
        self.update_status("")
    
    def start_conversion(self):
        """開始轉換"""
        # 檢查是否已在轉換
        if self.is_converting:
            messagebox.showwarning("警告", "正在轉換中，請稍候...")
            return
        
        if not self.selected_file_path:
            messagebox.showerror("錯誤", "請先選擇音檔")
            return
        
        
        self.is_converting = True
        self.update_button_states(uploading=False, converting=False, canceling=True)
        self.update_status("⏳ 轉換中...")
        self.clear_output()
        self.append_output(f"開始轉換...\n檔案: {Path(self.selected_file_path).name}\n時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n系統: {platform.system()}\n\n")
        
        # 在背景執行（非 daemon 以確保應用關閉時執行緒能正確終止）
        self.conversion_thread = threading.Thread(target=self._run_conversion, daemon=False)
        self.conversion_thread.start()
    
    def _get_desktop_path(self):
        """
        智慧偵測桌面路徑，支援：
        - 標準桌面: ~/Desktop
        - OneDrive 桌面: ~/OneDrive/桌面 或 ~/OneDrive/Desktop
        - 中文桌面: ~/桌面
        """
        # 候選路徑列表（按優先順序）
        candidates = [
            Path.home() / "Desktop",                    # 標準英文桌面
            Path.home() / "OneDrive" / "桌面",          # OneDrive 中文桌面
            Path.home() / "OneDrive" / "Desktop",       # OneDrive 英文桌面
            Path.home() / "OneDrive - Personal" / "桌面",  # OneDrive Personal 中文
            Path.home() / "OneDrive - Personal" / "Desktop",  # OneDrive Personal 英文
            Path.home() / "桌面",                       # 中文系統桌面
        ]
        
        # 在 Windows 上，嘗試從 Registry 讀取真實桌面路徑
        if platform.system() == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
                )
                desktop_path, _ = winreg.QueryValueEx(key, "Desktop")
                winreg.CloseKey(key)
                desktop_from_registry = Path(desktop_path)
                if desktop_from_registry.exists():
                    return desktop_from_registry
            except Exception:
                pass  # Registry 讀取失敗，繼續使用候選路徑
        
        # 尋找第一個存在的桌面路徑
        for path in candidates:
            if path.exists():
                return path
        
        # 如果都不存在，回退到標準路徑並建立
        default_path = Path.home() / "Desktop"
        default_path.mkdir(parents=True, exist_ok=True)
        return default_path
    
    def _run_conversion(self):
        """在背景線程執行轉換腳本"""
        try:
            # 生成輸出檔案路徑（放在使用者的桌面）
            input_path = Path(self.selected_file_path)
            
            # 智慧偵測桌面路徑（支援 OneDrive 同步桌面）
            desktop_path = self._get_desktop_path()
            
            output_path = desktop_path / f"{input_path.stem}_transcript.txt"
            
            # 如果輸出檔案已存在，先刪除（避免覆蓋提示卡住）
            if output_path.exists():
                try:
                    output_path.unlink()
                    self.app.after(0, self.append_output, f"✓ 已刪除舊的輸出檔案: {output_path.name}\n\n")
                except Exception as e:
                    self.app.after(0, self.append_output, f"⚠ 無法刪除舊檔案: {str(e)}\n\n")

            # 確保首次使用時模型已下載（以避免使用者無感的長時間等待）
            self._ensure_model_downloaded_with_ui()

            # ✅ 打包環境：直接導入 transcribe 模組執行（避免系統 Python 依賴問題）
            if getattr(sys, 'frozen', False):
                self.app.after(0, self.append_output, "使用打包環境執行轉錄...\n\n")
                
                # 使用內嵌的 transcribe 模組（PyInstaller 已打包所有依賴）
                try:
                    import transcribe as transcribe_module
                    
                    # 重定向 stdout 來捕捉輸出
                    import io
                    from contextlib import redirect_stdout
                    
                    class GUIWriter(io.StringIO):
                        def __init__(self, callback):
                            super().__init__()
                            self.callback = callback
                            self.buffer = ""
                        
                        def write(self, text):
                            self.buffer += text
                            # 當遇到換行時，輸出整行
                            if '\n' in self.buffer:
                                lines = self.buffer.split('\n')
                                for line in lines[:-1]:
                                    if line.strip():
                                        self.callback(line + '\n')
                                self.buffer = lines[-1]
                            return len(text)
                        
                        def flush(self):
                            if self.buffer.strip():
                                self.callback(self.buffer + '\n')
                                self.buffer = ""
                    
                    # 創建輸出捕捉器
                    output_writer = GUIWriter(lambda msg: self.app.after(0, self.append_output, msg))
                    
                    # 執行轉錄（在背景線程中，stdout 已重定向）
                    with redirect_stdout(output_writer):
                        transcribe_module.main(
                            input_audio=str(Path(self.selected_file_path).absolute()),
                            output_text=str(output_path),
                            non_interactive=True,
                            auto_clean_progress=True,
                            suppress_warnings=True
                        )
                    
                    # 確保剩餘緩衝區內容輸出
                    output_writer.flush()
                    return_code = 0
                    
                except Exception as e:
                    import traceback
                    error_detail = traceback.format_exc()
                    self.app.after(0, self.append_output, f"\n❌ 轉錄過程發生錯誤:\n{error_detail}\n")
                    return_code = 1
            else:
                # 開發環境：使用 subprocess
                transcribe_script = Path(__file__).parent / "transcribe.py"
                
                if not transcribe_script.exists():
                    error_msg = f"❌ 找不到轉錄腳本: {transcribe_script}\n"
                    self.app.after(0, self.append_output, error_msg)
                    self.app.after(0, self.update_status, "❌ 找不到轉錄腳本")
                    return
                
                command = [
                    sys.executable,
                    str(transcribe_script),
                    str(Path(self.selected_file_path).absolute()),
                    str(output_path),
                    "--non-interactive",
                    "--auto-clean-progress",
                    "--suppress-warnings"
                ]
                
                self.app.after(0, self.append_output, f"執行命令: {' '.join(command)}\n\n")

                # 強制 Python 不使用緩衝
                env = os.environ.copy()
                env['PYTHONUNBUFFERED'] = '1'
                
                # 合併 stderr 到 stdout，使用阻塞式讀取（在背景執行緒中不影響 GUI）
                self.current_process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,  # 行緩衝
                    encoding=self.encoding,
                    errors='replace',
                    env=env
                )
                
                # 直接在背景執行緒中逐行讀取（阻塞式，但不影響 GUI）
                try:
                    for line in iter(self.current_process.stdout.readline, ''):
                        if line:
                            # 使用 after() 安全地更新 GUI
                            self.app.after(0, self.append_output, line)
                except Exception as e:
                    self.app.after(0, self.append_output, f"\n⚠ 讀取輸出時發生錯誤: {str(e)}\n")
                finally:
                    # 確保關閉 stdout
                    try:
                        self.current_process.stdout.close()
                    except Exception:
                        pass
                
                # 等待進程結束
                return_code = self.current_process.wait()
            
            # 顯示完成訊息
            if return_code == 0:
                self.app.after(0, self.append_output, f"\n✓ 轉換完成！\n輸出檔案: {output_path}\n")
                self.app.after(0, self.update_status, "✓ 轉換完成")
            else:
                self.app.after(0, self.append_output, f"\n✗ 轉換失敗（錯誤代碼: {return_code}）\n")
                self.app.after(0, self.update_status, f"✗ 轉換失敗（代碼: {return_code}）")
        
        except FileNotFoundError as e:
            self.app.after(0, self.append_output, f"\n❌ 錯誤: 找不到檔案或 Python\n詳情: {str(e)}\n")
            self.app.after(0, self.update_status, "❌ 找不到檔案")
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            self.app.after(0, self.append_output, f"\n❌ 錯誤: {str(e)}\n{error_detail}\n")
            self.app.after(0, self.update_status, "❌ 發生錯誤")
        
        finally:
            # 只在非正常終止時才重新啟用按鈕
            if self.is_converting:
                self.is_converting = False
                self.current_process = None
                self.app.after(0, self.update_button_states, True, True, False)

    # ===== 模型下載提示相關 =====
    def _show_model_download_ui(self, message: str):
        """顯示模型下載提示與不定進度條"""
        def _show():
            self.model_label.configure(text=message)
            try:
                self.model_progress.stop()
            except Exception:
                pass
            self.model_frame.pack(fill="x", pady=(0, 10))
            self.model_progress.start()
        self.app.after(0, _show)

    def _hide_model_download_ui(self):
        """隱藏模型下載提示"""
        def _hide():
            try:
                self.model_progress.stop()
            except Exception:
                pass
            self.model_frame.pack_forget()
        self.app.after(0, _hide)

    def _ensure_model_downloaded_with_ui(self):
        """若本機快取未有模型，顯示提示並進行下載。"""
        if not HF_AVAILABLE:
            # 無 huggingface_hub，可跳過（由 transformers 自行處理下載）
            self.app.after(0, self.append_output, "ⓘ 無法偵測 huggingface_hub，將直接載入模型，首次可能較久…\n")
            return

        REPO_ID = "MediaTek-Research/Breeze-ASR-25"

        # 先檢查是否已存在（純本機檢查，不觸發下載）
        try:
            snapshot_download(REPO_ID, local_files_only=True)
            return  # 已下載，直接返回
        except Exception:
            pass

        # 顯示提示並下載
        self._show_model_download_ui("⬇️ 首次使用需下載模型（~1.5GB），請保持應用開啟，過程可能需要數分鐘…")
        self.app.after(0, self.append_output, "開始下載 Breeze-ASR-25 模型檔至快取…\n")
        try:
            # 使用預設進度（tqdm 列印到 stdout），此處提供不定進度條即可
            snapshot_download(REPO_ID)
            self.app.after(0, self.append_output, "✓ 模型下載完成，繼續轉錄…\n\n")
        except Exception as e:
            self.app.after(0, self.append_output, f"⚠ 模型下載時發生例外：{e}\n將嘗試由 transformers 自動處理（可能較久）\n")
        finally:
            self._hide_model_download_ui()
    
    def _validate_file(self, file_path):
        """驗證檔案是否存在且可讀"""
        if not os.path.exists(file_path):
            messagebox.showerror("錯誤", "選擇的檔案不存在")
            return False
        
        if not os.access(file_path, os.R_OK):
            messagebox.showerror("錯誤", "無法讀取選擇的檔案")
            return False
        
        return True
    
    def _get_file_size(self, file_path):
        """取得檔案大小的易讀格式"""
        size_bytes = os.path.getsize(file_path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"
    
    def clear_output(self):
        """清空輸出區域"""
        self.output_text.configure(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.configure(state="disabled")
    
    def append_output(self, text):
        """附加文字到輸出區域"""
        self.output_text.configure(state="normal")
        
        # 限制輸出行數（保留最後 10000 行以避免記憶體溢出）
        line_count = int(self.output_text.index('end-1c').split('.')[0])
        if line_count > 10000:
            self.output_text.delete('1.0', '101.0')
        
        self.output_text.insert("end", text)
        self.output_text.see("end")
        self.output_text.configure(state="disabled")
    
    def cancel_conversion(self):
        """取消正在進行的轉換"""
        if not self.is_converting or not self.current_process:
            messagebox.showwarning("警告", "目前沒有正在進行的轉換")
            return
        
        result = messagebox.askyesno(
            "確認取消",
            "確定要取消目前的轉換嗎？"
        )
        
        if result:
            try:
                self.current_process.terminate()  # 先嘗試溫和終止
                self.current_process.wait(timeout=2)  # 等待 2 秒
            except subprocess.TimeoutExpired:
                # 如果溫和終止失敗，強制殺死
                self.current_process.kill()
                self.current_process.wait()
            
            self.append_output("\n⛔ 轉換已被使用者取消\n")
            self.update_status("⛔ 已取消")
            self.is_converting = False
            self.current_process = None
            # 取消後允許再次轉換：啟用上傳與開始轉換，停用取消
            self.update_button_states(True, True, False)
    
    def on_closing(self):
        """應用關閉時的處理"""
        if self.is_converting:
            result = messagebox.askyesno(
                "警告",
                "轉換正在進行中，是否確定要關閉應用程式？"
            )
            if not result:
                return
            
            # 終止正在執行的程序
            if self.current_process:
                try:
                    self.current_process.terminate()
                    self.current_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.current_process.kill()
                    self.current_process.wait()
        
        # daemon=False 的執行緒會在主程式關閉前自動等待完成
        self.app.destroy()


if __name__ == "__main__":
    AudioConverterApp()