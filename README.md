# Breeze-ASR-Transcriber

🎤 一個基於 Breeze-ASR-25 的音檔轉逐字稿 GUI 應用，支援繁體中文語音識別。

## 功能

- 🎙️ **音檔轉逐字稿** - 支援 MP3、WAV、M4A 等常見音檔格式
- 🇹🇼 **繁體中文優化** - 使用 Breeze-ASR-25 模型，針對繁體中文語音優化
- 🖥️ **跨平台 GUI** - macOS 和 Windows 原生應用程式
- 🔄 **自動恢復** - 支援中斷後恢復進度
- 📊 **實時進度顯示** - 即時查看轉錄進度
- 💾 **自動快取** - 語言模型快取，首次下載後無需重複下載

## 下載

前往 [Release 頁面](https://github.com/xinhonglin/breeze-asr-transcriber/releases) 下載對應平台的可執行檔：

- **macOS**: `BreezASR` - 支援 Apple Silicon (M1/M2/M3/M4)
- **Windows**: `BreezASR.exe` - 支援 Windows 11 及以上

## 快速開始

### 方式 1：下載可執行檔（推薦）

1. 前往 [Release 頁面](https://github.com/xinhonglin/breeze-asr-transcriber/releases)
2. 下載對應平台的檔案
3. 解壓後雙擊執行

**首次執行會下載 ~1.5GB 的語言模型，請耐心等待。**

### 方式 2：從源碼執行（開發者）

#### 前置條件

- Python 3.11
- [uv](https://github.com/astral-sh/uv) 套件管理器

#### 安裝

```bash
# 複製專案
git clone https://github.com/xinhonglin/breeze-asr-transcriber.git
cd breeze-asr-transcriber

# 安裝依賴
uv sync

# 執行應用
uv run python gui.py
```

## 使用說明

1. **啟動應用** - 執行 BreezASR（或 `uv run python gui.py`）
2. **選擇音檔** - 點擊「選擇音檔」按鈕，選擇要轉錄的音檔
3. **開始轉錄** - 點擊「開始轉換」按鈕
4. **等待完成** - 實時進度顯示在界面上
5. **查看結果** - 轉錄完成後，逐字稿文字檔會自動保存

## 系統需求

### macOS
- OS X 10.13 或以上
- 4GB 記憶體以上（建議 8GB）
- 2GB 可用硬碟空間（用於語言模型快取）

### Windows
- Windows 11
- 4GB 記憶體以上（建議 8GB）
- 2GB 可用硬碟空間（用於語言模型快取）

## 常見問題

### Q: 首次執行很慢，是正常的嗎？
**A**: 是的。首次執行會自動下載 ~1.5GB 的 Breeze-ASR-25 語言模型，下載時間取決於網速，通常需要 5-15 分鐘。應用內會顯示「下載提示與進度條」，模型下載完成後會自動開始轉錄。模型會被快取到本機，後續執行無需重複下載。

### Q: 可以離線使用嗎？
**A**: 可以。模型首次下載後會被快取，之後即使斷網也能使用。

### Q: 支援哪些音檔格式？
**A**: 支援 WAV、MP3、M4A、FLAC 等常見音檔格式。

### Q: Windows 版本被防毒軟體誤報怎麼辦？
**A**: 這是 PyInstaller 打包的 exe 常見的問題。可以：
1. 將 exe 加入防毒軟體白名單
2. 從 GitHub Release 官方下載，確保來源安全
3. 若不放心，可從源碼執行

### Q: 支援其他語言嗎？
**A**: Breeze-ASR-25 模型主要針對繁體中文優化。若要支援其他語言，需要更換不同的模型。

### Q: 可以串接到其他應用嗎？
**A**: 可以。轉錄邏輯在 `transcribe.py` 中，你可以將其集成到其他 Python 專案。

### Q: 如何刪除已下載的 Hugging Face 模型（清除快取）？
> **注意**：刪除後下次使用會重新下載（約 3GB）。快取通常占用 **5-6GB**（包含模型本體約 3GB + hf-xet 下載快取約 2.9GB）。
> 
> ⚠️ **舊版本使用者注意**：若之前下載過模型且快取占用超過 10GB，可能包含不必要的訓練檔案（optimizer.bin 等約 12GB）。建議完整刪除快取後重新下載，新版本會自動排除訓練檔案。

**預設快取位置**（若有自訂 `HF_HOME` 環境變數，則使用該路徑）
- macOS：`~/.cache/huggingface`
- Windows：`%USERPROFILE%\.cache\huggingface`

**檢查實際快取大小**
- macOS（Terminal）
  ```bash
  # 查看總用量
  du -sh ~/.cache/huggingface
  
  # 查看各子資料夾用量
  du -sh ~/.cache/huggingface/*
  ```

- Windows（PowerShell）
  ```powershell
  # 查看總用量（若有安裝 Git for Windows 的 du）
  du -sh "$env:USERPROFILE\.cache\huggingface"
  
  # 或查看資料夾屬性
  Get-ChildItem "$env:USERPROFILE\.cache\huggingface" -Recurse | 
    Measure-Object -Property Length -Sum
  ```

**清理快取**
- macOS（Terminal）
  ```bash
  # 只刪除 hf-xet 下載快取（釋放約一半空間，推薦）
  rm -rf ~/.cache/huggingface/xet
  
  # 只刪除模型快取（hub 子資料夾）
  rm -rf ~/.cache/huggingface/hub
  
  # 刪除全部 Hugging Face 快取（包含所有模型）
  rm -rf ~/.cache/huggingface
  ```

- Windows（PowerShell）
  ```powershell
  # 只刪除 hf-xet 下載快取（釋放約一半空間，推薦）
  Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\xet"
  
  # 只刪除模型快取（hub 子資料夾）
  Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\hub"
  
  # 刪除全部 Hugging Face 快取（包含所有模型）
  Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface"
  ```

**圖形介面操作**
- macOS：Finder → 前往 → 前往資料夾… → 輸入 `~/.cache/huggingface` → 刪除資料夾或子資料夾
- Windows：檔案總管地址列輸入 `%USERPROFILE%\.cache\huggingface` → 刪除資料夾或子資料夾

## 開發

### 專案結構

```
breeze-asr-transcriber/
├── gui.py              # GUI 介面（基於 customtkinter）
├── transcribe.py       # 轉錄核心邏輯
├── pyproject.toml      # 專案配置
├── uv.lock             # 依賴鎖定檔
├── .github/
│   └── workflows/
│       └── build.yml   # GitHub Actions 自動打包
└── README.md           # 本檔案
```

### 本地開發

```bash
# 安裝開發環境
uv sync

# 執行應用
uv run python gui.py

# 打包為可執行檔
uv run pyinstaller --onefile --windowed gui.py
```

### 提交貢獻

1. Fork 本專案
2. 建立功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 開啟 Pull Request

## 依賴

主要依賴：

- **torch / torchaudio** - PyTorch 深度學習框架
- **transformers** - Hugging Face Transformers（Breeze-ASR 模型）
- **customtkinter** - 現代化 GUI 框架
- **numpy** - 數值計算
- **soundfile** - 音檔讀寫
- **psutil** - 系統資訊

詳見 `pyproject.toml`

## 許可

[MIT License](LICENSE) - 自由使用、修改和分發

## 致謝

- [Breeze-ASR](https://huggingface.co/spaces/onsol/Breeze-ASR-25) - 語音識別模型
- [PyTorch](https://pytorch.org/) - 深度學習框架
- [Hugging Face](https://huggingface.co/) - 模型託管平台
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - GUI 框架

## 聯絡方式

若有問題或建議，歡迎：
- [提出 Issue](https://github.com/xinhonglin/breeze-asr-transcriber/issues)
- 發送 Email 至 classiccrotchet@gmail.com

---

**Made with ❤️ in Taiwan**