#!/usr/bin/env python3
# breeze_asr_transcribe_overlap.py
# 30s chunk + 3s overlap, resume support, processor+model.generate flow, MPS/CPU fallback
# 修正注意力遮罩 (attention_mask) 的 shape 問題

import os
import json
import shutil
import math
import numpy as np
import torch
import torchaudio
import soundfile as sf
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from transformers.utils import logging as hf_logging
import psutil
from datetime import datetime
import time
import re
import traceback
import argparse
import gc
from typing import Optional
import warnings

# ---------- Configurable ----------
CHUNK_SECONDS = 30        # 每段長度（秒）
OVERLAP_SECONDS = 3       # 每段重疊（秒）
SR = 16000
MAX_TIME_WARN = 180
PROGRESS_FILE_SUFFIX = ".progress.json"
# -----------------------------------

def load_and_prepare(audio_path, target_sr=SR):
    waveform, sr = torchaudio.load(audio_path)  # (channels, samples)
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)
    if sr != target_sr:
        waveform = torchaudio.transforms.Resample(sr, target_sr)(waveform)
    arr = waveform.squeeze(0).numpy().astype(np.float32)
    return arr, target_sr

def compute_slices_with_overlap(total_samples, sr, chunk_seconds=CHUNK_SECONDS, overlap_seconds=OVERLAP_SECONDS):
    """
    以固定長度 + 重疊切片，回傳 list of (start_sample, end_sample, start_sec, end_sec)
    不做任何磁碟 I/O，僅回傳索引資訊。
    """
    chunk_samples = int(chunk_seconds * sr)
    overlap_samples = int(overlap_seconds * sr)
    step = chunk_samples - overlap_samples
    if step <= 0:
        raise ValueError("chunk_seconds must be larger than overlap_seconds")

    slice_infos = []
    for start in range(0, total_samples, step):
        end = min(start + chunk_samples, total_samples)
        start_sec = start / sr
        end_sec = end / sr
        slice_infos.append((start, end, start_sec, end_sec))
        if end == total_samples:
            break
    return slice_infos

def normalize_text_for_matching(text):
    # 簡單正規化：去標點、多空格處理，回傳字詞列表
    s = text.strip()
    s = re.sub(r"[^\w\u4e00-\u9fff]+", " ", s)  # 保留中文與文字數字，其他替換成空格
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return []
    words = s.split(" ")
    return words

def merge_two_segments(prev_text, curr_text, max_overlap_words=30, min_overlap=3):
    """
    嘗試找 prev_text 的結尾與 curr_text 的開頭的最大相同詞序列（至多 max_overlap_words）。
    若找到長度 >= min_overlap，移除 curr_text 的前面那段重複詞。
    """
    if not prev_text:
        return curr_text
    prev_words = normalize_text_for_matching(prev_text)
    curr_words = normalize_text_for_matching(curr_text)
    if not prev_words or not curr_words:
        # 若正規化後其中一段空，直接串接
        return prev_text.rstrip() + "\n" + curr_text.lstrip()

    # 比對最大重疊片段長度
    max_k = min(len(prev_words), len(curr_words), max_overlap_words)
    found_k = 0
    # 從大到小找最大重疊
    for k in range(max_k, min_overlap - 1, -1):
        if prev_words[-k:] == curr_words[:k]:
            found_k = k
            break
    if found_k >= min_overlap:
        remaining = curr_words[found_k:]
        merged = prev_text.rstrip() + (" " + " ".join(remaining) if remaining else "")
        return merged
    else:
        # 若沒有重疊，直接用換行串接
        return prev_text.rstrip() + "\n" + curr_text.lstrip()

def _format_duration(secs: float) -> str:
    """將秒數格式化為 HH:MM:SS。"""
    total = int(round(secs))
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def transcribe_chunk_generate(arr_or_path, processor, model, device, sr_target=SR, max_time_warn=MAX_TIME_WARN, forced_decoder_ids=None):
    try:
        # 支援直接傳入 ndarray（已是 float32/target_sr）或傳入音檔路徑
        if isinstance(arr_or_path, np.ndarray):
            arr = arr_or_path
            sr = sr_target
            path_label = "(in-memory segment)"
        else:
            path = arr_or_path
            arr, sr = load_and_prepare(path, target_sr=sr_target)
            path_label = os.path.basename(path)
        
        # ✅ 自動檢測並 padding 音訊到 30 秒（Whisper 標準輸入長度）
        min_samples = 30 * sr_target  # 480000 @ 16kHz
        original_duration = len(arr) / sr_target
        
        if len(arr) < min_samples:
            padding_needed = min_samples - len(arr)
            arr = np.pad(arr, (0, padding_needed), mode='constant', constant_values=0)
            print(f"  ⓘ 音訊 {original_duration:.1f}s → 已自動填充至 30.0s")
        
        inputs = processor(arr, sampling_rate=sr, return_tensors="pt", padding=True)

        # WhisperProcessor 已自動生成正確的 attention_mask，無需手動設置
        # 直接將輸入移至目標裝置
        inputs = {k: v.to(device) for k, v in inputs.items()}

        start = time.time()
        with torch.no_grad():
            max_target_positions = getattr(model.config, "max_target_positions", None)
            if max_target_positions is None:
                safe_max_new_tokens = 400
            else:
                # 估計 decoder prompt len = 4（保守），margin 10
                decoder_prompt_len = 4
                margin = 10
                safe_max_new_tokens = max(1, max_target_positions - decoder_prompt_len - margin)
                safe_max_new_tokens = min(safe_max_new_tokens, 400)

            gen_kwargs = dict(
                **inputs,
                max_new_tokens=safe_max_new_tokens,
                do_sample=False,
                num_beams=1
            )
            if forced_decoder_ids is not None:
                gen_kwargs["forced_decoder_ids"] = forced_decoder_ids

            tokens = model.generate(**gen_kwargs)
        elapsed = time.time() - start
        text = processor.batch_decode(tokens, skip_special_tokens=True)[0]
        text_clean = text.strip()
        print(f"本段（{path_label}）在 {str(device)} 上推論耗時：{elapsed:.1f} 秒 (max_new_tokens={safe_max_new_tokens}) ；輸出字數：{len(text_clean)}")
        if elapsed > max_time_warn:
            print(f"⚠ 本段耗時 > {max_time_warn}s（{elapsed:.1f}s），建議改短 chunk 或測試 CPU。")

        # 釋放中間張量與強制 GC（避免長任務積累）
        try:
            del inputs
            del tokens
        except Exception:
            pass
        gc.collect()
        return text_clean, str(device), elapsed
    except Exception as e:
        print(f"transcribe_chunk_generate 例外（device={device}）：{e}")
        traceback.print_exc()
        return "", str(device), None

def check_system_requirements():
    print("=== 系統檢查 ===")
    print(f"PyTorch 版本: {torch.__version__}")
    mps_ok = torch.backends.mps.is_available() and torch.backends.mps.is_built()
    if mps_ok:
        print("✓ MPS 可用")
    else:
        print("✗ MPS 不可用，使用 CPU")
    mem = psutil.virtual_memory()
    print(f"記憶體: {mem.total/(1024**3):.1f}GB (可用 {mem.available/(1024**3):.1f}GB)")
    if mem.available < 4*(1024**3):
        print("⚠ 可用記憶體低於 4GB")

def save_progress_json(prog_path, data):
    with open(prog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_progress_json(prog_path):
    if not os.path.exists(prog_path):
        return {}
    try:
        with open(prog_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _suppress_noisy_warnings():
    """抑制常見但無害的第三方警告訊息（可選）。"""
    # torchaudio 的未來變更提醒
    warnings.filterwarnings(
        "ignore",
        category=UserWarning,
        module=r"torchaudio\._backend\.utils"
    )
    # transformers 關於 forced_decoder_ids 的棄用提醒
    warnings.filterwarnings(
        "ignore",
        message=r"Using custom `forced_decoder_ids` from the \(generation\) config.*",
        category=UserWarning,
    )
    # Whisper 預設語言偵測的提醒
    warnings.filterwarnings(
        "ignore",
        message=r"Transcription using a multilingual Whisper will default to language detection.*",
        category=UserWarning,
    )
    # 一般化 attention_mask 的提醒（Whisper 通常不需要）
    warnings.filterwarnings(
        "ignore",
        message=r"The attention mask is not set and cannot be inferred.*",
        category=UserWarning,
    )
    # 降低 transformers 的日誌層級
    hf_logging.set_verbosity_error()


def main(input_audio, output_text, non_interactive=False, auto_clean_progress=False, language: Optional[str]=None, suppress_warnings: bool=False):
    if suppress_warnings:
        _suppress_noisy_warnings()

    # ✅ 最先處理路徑，展開 ~ 為完整路徑，確保後續所有操作使用完整路徑
    input_audio = os.path.expanduser(input_audio)
    output_text = os.path.expanduser(output_text)


    total_start = time.time()
    check_system_requirements()
    print("載入 Breeze-ASR-25 模型與處理器...")
    processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    device = torch.device("mps" if (torch.backends.mps.is_available() and torch.backends.mps.is_built()) else "cpu")
    print("使用裝置：", device)
    model = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(device).eval()
    model_cpu = None  # 延遲初始化並重用 CPU 模型（僅在需要時）
    forced_decoder_ids = None
    if language:
        try:
            forced_decoder_ids = processor.get_decoder_prompt_ids(language=language, task="transcribe")
            print(f"已設定語言為：{language}")
        except Exception as e:
            print(f"⚠ 語言設定失敗（{language}）：{e}，改用自動偵測")

    print("開始分段處理與轉錄（含重疊，流式切片）...")
    if not os.path.exists(input_audio):
        print(f"錯誤：找不到 {input_audio}")
        return

    # 預先載入整段音訊並重採樣，後續以記憶體切片（不落地暫存檔）
    file_size_mb = os.path.getsize(input_audio) / (1024**2)
    if file_size_mb > 500:
        print(f"⚠️  音檔較大（{file_size_mb:.1f}MB），可能需要較多記憶體")
    arr_full, sr = load_and_prepare(input_audio, target_sr=SR)
    total_samples = arr_full.shape[0]
    slice_list = compute_slices_with_overlap(total_samples, sr, CHUNK_SECONDS, OVERLAP_SECONDS)
    if not slice_list:
        print("分段失敗，結束")
        return

    prog_path = output_text + PROGRESS_FILE_SUFFIX
    progress = load_progress_json(prog_path)
    # progress format: { "chunks": { idx_str: {"start":..., "end":..., "text":..., "device":..., "elapsed":... } }, "meta": {...} }
    if "chunks" not in progress:
        progress = {"chunks": {}, "meta": {"input_audio": input_audio, "created": datetime.now().isoformat()}}

    results_ordered = []
    n_total = len(slice_list)
    for idx, (start_sample, end_sample, start_sec, end_sec) in enumerate(slice_list):
        idx_str = str(idx)
        if idx_str in progress["chunks"] and progress["chunks"][idx_str].get("text"):
            print(f"跳過第 {idx+1}/{n_total} 段（已完成）")
            results_ordered.append((idx, progress["chunks"][idx_str]["text"], progress["chunks"][idx_str].get("device","unknown")))
            continue

        print(f"轉錄第 {idx+1}/{n_total} 段... ({start_sec:.1f}s - {end_sec:.1f}s)")
        seg = arr_full[start_sample:end_sample]
        txt, used_dev, elapsed = transcribe_chunk_generate(seg, processor, model, device, forced_decoder_ids=forced_decoder_ids)
        if (not txt.strip()) and (str(device) != "cpu"):
            print("在 MPS 上失敗或無結果，嘗試用 CPU 重試一次...")
            cpu_device = torch.device("cpu")
            if model_cpu is None:
                # 延遲初始化 CPU 模型並重用
                model_cpu = WhisperForConditionalGeneration.from_pretrained("MediaTek-Research/Breeze-ASR-25").to(cpu_device).eval()
            txt_cpu, used_dev_cpu, elapsed_cpu = transcribe_chunk_generate(seg, processor, model_cpu, cpu_device, forced_decoder_ids=forced_decoder_ids)
            if txt_cpu.strip():
                txt = txt_cpu
                used_dev = used_dev_cpu
                elapsed = elapsed_cpu

        if not txt:
            txt = "[無法轉錄]"

        # save into progress
        progress["chunks"][idx_str] = {"start": start_sec, "end": end_sec, "text": txt, "device": used_dev, "elapsed": elapsed}
        save_progress_json(prog_path, progress)
        results_ordered.append((idx, txt, used_dev))

    # 合併所有段落並處理重疊去重
    # 先按 index 排序
    results_ordered.sort(key=lambda x: x[0])
    merged_text = ""
    for i, txt, used_dev in results_ordered:
        if not merged_text:
            merged_text = txt
        else:
            merged_text = merge_two_segments(merged_text, txt)

    # 最終寫檔（包含 metadata header）
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_elapsed = time.time() - total_start
    total_hms = _format_duration(total_elapsed)
    header = [
        "# 會議逐字稿",
        f"**轉錄時間：** {timestamp}",
        f"**音檔來源：** {input_audio}",
        f"**分段數量：** {len(slice_list)}",
        f"**分段長度（秒）：** {CHUNK_SECONDS}",
        f"**重疊（秒）：** {OVERLAP_SECONDS}",
        f"**使用模型：** Breeze-ASR-25",
        f"**使用裝置（優先）：** {str(device).upper()}",
        f"**總耗時：** {total_hms}（{total_elapsed:.1f} 秒）",
        "---\n"
    ]
    with open(output_text, "w", encoding="utf-8") as out_f:
        out_f.write("\n".join(header) + "\n")
        out_f.write(merged_text)

    print(f"已儲存最終結果 → {output_text}")
    print(f"進度檔保存在 → {prog_path}")

    # 非互動模式或旗標控制：是否刪除進度檔
    if os.path.exists(prog_path):
        if non_interactive:
            if auto_clean_progress:
                try:
                    os.remove(prog_path)
                    print("✓ 已刪除進度檔（非互動模式）")
                except Exception:
                    print("⚠ 無法刪除進度檔（非互動模式）")
        else:
            try:
                response = input("\n是否刪除進度檔？(y/n，預設 n): ").strip().lower()
                if response == 'y':
                    os.remove(prog_path)
                    print("✓ 已刪除進度檔")
            except (EOFError, KeyboardInterrupt):
                print("\n保留進度檔")

    print("\n✅ 完成")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Breeze-ASR-25 逐字稿（30s chunk + 3s overlap, 流式切片）")
    parser.add_argument("input_audio", help="輸入音檔路徑")
    parser.add_argument("output_text", help="輸出文字檔路徑")
    parser.add_argument("--non-interactive", action="store_true", help="非互動模式（不使用 input 提示）")
    parser.add_argument("--auto-clean-progress", action="store_true", help="非互動模式下自動刪除進度檔")
    parser.add_argument("--language", type=str, default=None, help="強制指定語言（例如 zh、en）；預設自動偵測")
    parser.add_argument("--suppress-warnings", action="store_true", help="抑制第三方套件的常見警告訊息（torchaudio/transformers）")
    args = parser.parse_args()

    main(
        args.input_audio,
        args.output_text,
        non_interactive=args.non_interactive,
        auto_clean_progress=args.auto_clean_progress,
        language=args.language,
        suppress_warnings=args.suppress_warnings,
    )