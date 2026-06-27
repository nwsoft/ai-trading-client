#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI ?™ìŠµ ?„ì ¯ (CustomTkinter) - ?•ë ¬ ê°œì„  ë²„ì „
AI ?™ìŠµ ê³¼ì •ê³??°ì´?°ë? ëª¨ë‹ˆ?°ë§?˜ëŠ” ?„ìš© ?„ì ¯
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None  # ?´ë°±: ë¡œì»¬ ?œê°„?€ ?¬ìš©
import threading
from typing import Any, Callable, Dict, List, Optional
import time
import sys
import subprocess

import customtkinter as ctk
from customtkinter import CTkFrame, CTkLabel, CTkButton, CTkProgressBar, CTkScrollableFrame, CTkTextbox

class AILearningWidgetFixed(CTkFrame):
    """AI ?™ìŠµ ?„ìš© ?„ì ¯ (CustomTkinter) - ?•ë ¬ ê°œì„  ë²„ì „"""
    DEFAULT_COLORS: Dict[str, str] = {
        "text_primary": "#f9fafb",
        "text_secondary": "#9ca3af",
        "success": "#22c55e",
        "info": "#3b82f6",
        "danger": "#ef4444",
        "accent": "#9b59b6",
    }

    
    def __init__(self, parent=None, colors: Optional[Dict[str, str]] = None, exchange_name="binance", **kwargs):
        super().__init__(parent, **kwargs)
        self.logger = logging.getLogger(__name__)
        self.colors = dict(colors) if colors and isinstance(colors, dict) else {}
        self.exchange_name = exchange_name or "binance"
        
        # ì´ˆê¸°???íƒœ ?Œë˜ê·?
        self.is_initialized = False
        self._loading = False  # ì¤‘ë³µ ë¡œë”© ë°©ì?
        self._last_data_mtime: Optional[float] = None
        self._recent_cache: Optional[List[dict]] = None
        self._summary_cache: Optional[Dict[str, Any]] = None
        self._last_compact_time: Optional[float] = None
        self._data_file_path: Optional[str] = None  # ?¤ì œ ?¬ìš©?˜ëŠ” ?°ì´???Œì¼ ê²½ë¡œ
        # ?¸ë?(?€?œë³´???ë‹¨)ë¡??”ì•½ ?µê³„ë¥??„ë‹¬?˜ê¸° ?„í•œ ì½œë°±
        self.on_summary_update = None  # type: Optional[Callable[[Dict[str, Any]], None]]
        # ?ë™ ?ˆë¡œê³ ì¹¨
        self.auto_refresh_enabled = ctk.BooleanVar(value=False)
        self.auto_refresh_interval_sec: int = 60
        self._auto_refresh_job: Optional[str] = None
        # ?°ì´???Œì´ë¸?ì»¬ëŸ¼ ???¬ì–‘ (ë§ˆì?ë§?'?´ìœ '??ê°€ë³€ ?•ì¥)
        # [?œê°„, ì½”ì¸, ?œê·¸?? ? ë¢°?? ë³€?™ì„±, ?¸ë Œ?œê°•?? ì§„ì…ê°€, ?´ìœ ]
        self._col_widths = [64, 100, 70, 80, 90, 110, 90, 420]
        self._reason_max_chars = 80
        
        try:
            self.init_ui()
            self.is_initialized = True
            print(f"??AI ?™ìŠµ ?„ì ¯ ì´ˆê¸°???„ë£Œ (ê±°ë˜?? {self.exchange_name})")
        except Exception as e:
            print(f"??AI ?™ìŠµ ?„ì ¯ ì´ˆê¸°???¤íŒ¨: {e}")
            self.create_error_ui(str(e))
        
    def _color(self, key: str, fallback: Optional[str] = None) -> str:
        if fallback is None:
            fallback = self.DEFAULT_COLORS.get(key, "#9ca3af")
        try:
            value = self.colors.get(key) if isinstance(self.colors, dict) else None
            if value:
                return value
        except Exception:
            pass
        return fallback

    def init_ui(self):
        """UI ì´ˆê¸°??- ?ˆì „??ë²„ì „"""
        # ë©”ì¸ ?ˆì´?„ì›ƒ
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        
        # 1. AI ?™ìŠµ ?íƒœ ?¹ì…˜
        self.create_status_section()
        
        # 2. ?™ìŠµ ?°ì´???Œì´ë¸??¹ì…˜
        self.create_data_section()
        
        # 3. AI ?™ìŠµ ?µê³„ ?¹ì…˜
        self.create_performance_section()
        
        # ì´ˆê¸° ?°ì´?°ëŠ” ?˜ì¤‘??ë¡œë“œ
        self.after_jobs = []
        self.safe_after(1000, self.load_learning_data_safe)
    
    def safe_after(self, delay, func, *args, **kwargs):
        """?ˆì „??after() ë©”ì„œ??- ?¤ë ˆ???ˆì „"""
        try:
            import threading
            current_thread = threading.current_thread()
            main_thread = threading.main_thread()
            
            # ?„ì¬ ?¤ë ˆ?œê? ë©”ì¸ ?¤ë ˆ?œì¸ì§€ ?•ì¸
            if current_thread is main_thread:
                # ë©”ì¸ ?¤ë ˆ?œì—??ì§ì ‘ ?¸ì¶œ
                job_id = self.after(delay, func, *args, **kwargs)
                self.after_jobs.append(job_id)
                return job_id
            else:
                # ë°±ê·¸?¼ìš´???¤ë ˆ?œì—???¸ì¶œ ??ë¬´ì‹œ (?ˆì „?˜ê²Œ)
                # print(f"? ï¸ AI Learning Widget: ë°±ê·¸?¼ìš´???¤ë ˆ?œì—??UI ?…ë°?´íŠ¸ ?œë„ ë¬´ì‹œ ({current_thread.name})")  # ë¡œê·¸ ?œê±°
                return None
        except Exception as e:
            print(f"? ï¸ safe_after ?¤ë¥˜: {e}")
            return None
    
    def cleanup_after_jobs(self):
        """ëª¨ë“  after() ?‘ì—… ?•ë¦¬"""
        for job_id in self.after_jobs:
            try:
                self.after_cancel(job_id)
            except:
                pass
        self.after_jobs.clear()
        
    def create_error_ui(self, error_msg):
        """?¤ë¥˜ ë°œìƒ ???œì‹œ??UI"""
        error_frame = CTkFrame(self)
        error_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        error_frame.grid_columnconfigure(0, weight=1)
        error_frame.grid_rowconfigure(0, weight=1)
        
        error_label = ctk.CTkLabel(
            error_frame,
            text=f"??AI ?™ìŠµ ?„ì ¯ ë¡œë“œ ?¤íŒ¨\n{error_msg}",
            font=ctk.CTkFont(size=14),
            text_color=self._color("danger", "#ef4444")
        )
        error_label.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        
    def create_status_section(self):
        """AI ?™ìŠµ ?íƒœ ?¹ì…˜ ?ì„±"""
        status_frame = CTkFrame(self)
        status_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        status_frame.grid_columnconfigure(1, weight=1)
        
        # ?œëª©
        title_label = ctk.CTkLabel(
            status_frame, 
            text="?§  AI ?™ìŠµ ?íƒœ",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        # ?œê°„?€ ?ˆë‚´(ë°ì? ?Œìƒ‰) - ?íƒœ ?œëª© ?†ìœ¼ë¡??´ë™
        tz_note = ctk.CTkLabel(
            status_frame,
            text="(?œì‹œ ?œê°„?€:?œêµ­ ?œì???KST,UTC+9). ?ë³¸ ê¸°ë¡?€ ê±°ë˜??ê¸°ì?(UTC)?…ë‹ˆ??)",
            font=ctk.CTkFont(size=11),
            text_color="#95a5a6",
            fg_color="#0b1120"
        )
        tz_note.grid(row=0, column=1, sticky="w", padx=(6, 0), pady=(10, 5))
        
        # ?„ì¬ ?íƒœ
        ctk.CTkLabel(status_frame, text="?„ì¬ ?íƒœ:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.learning_status_label = ctk.CTkLabel(
            status_frame, 
            text="ì´ˆê¸°??ì¤?..",
            font=ctk.CTkFont(weight="bold")
        )
        self.learning_status_label.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        # ì§„í–‰ë¥??œì‹œ
        self.learning_progress = ctk.CTkProgressBar(status_frame)
        self.learning_progress.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        self.learning_progress.set(0)
        
    def create_data_section(self):
        """?™ìŠµ ?°ì´???Œì´ë¸??¹ì…˜ ?ì„±"""
        data_frame = CTkFrame(self)
        data_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        data_frame.grid_columnconfigure(0, weight=1)
        data_frame.grid_columnconfigure(1, weight=0)
        data_frame.grid_rowconfigure(2, weight=1)

        # ?œëª© (ì¢Œì¸¡), ?ˆë¡œê³ ì¹¨ ë²„íŠ¼ (?°ì¸¡)
        self.title_label = ctk.CTkLabel(
            data_frame,
            text=f"?“š AI ?™ìŠµ ?°ì´????{self.exchange_name.upper()}",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        self.title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))

        controls = CTkFrame(data_frame)
        controls.grid(row=0, column=1, sticky="e", padx=10, pady=(10, 5))
        
        refresh_button = ctk.CTkButton(
            controls,
            text="?”„ ?ˆë¡œê³ ì¹¨",
            command=self.refresh_learning_data_safe,
            width=100,
            height=30
        )
        refresh_button.pack(side="left", padx=(0, 6))

        self.auto_refresh_chk = ctk.CTkCheckBox(
            controls,
            text="?ë™",
            variable=self.auto_refresh_enabled,
            command=self.on_toggle_auto_refresh
        )
        self.auto_refresh_chk.pack(side="left", padx=(0, 6))

        self.interval_combo = ctk.CTkComboBox(
            controls,
            values=["15s", "30s", "60s", "300s"],
            command=self.on_interval_changed,
            width=80
        )
        self.interval_combo.set("60s")
        self.interval_combo.pack(side="left")

        # ?¤ì œ ?°ì´???Œì¼ ê²½ë¡œ ?œì‹œ ë°??¡ì…˜ ë²„íŠ¼??(1???„ì²´)
        path_row = CTkFrame(data_frame)
        path_row.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 5))
        path_row.grid_columnconfigure(0, weight=1)
        # ê²½ë¡œ ë¯¸ë¦¬ ê³„ì‚° (ExchangeLearningManager ì´ˆê¸°???†ì´ path_utilsë¡?êµ¬ì„±)
        try:
            from path_utils import get_exchange_ai_learning_data_path
            self._data_file_path = get_exchange_ai_learning_data_path(self.exchange_name)
        except Exception:
            # ?´ë°±: ???”ë ‰? ë¦¬ ê¸°ì?
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
            self._data_file_path = os.path.join(base_dir, f"ai_learning_data_{self.exchange_name}.json")

        self.data_path_label = ctk.CTkLabel(
            path_row,
            text=f"?“ ?°ì´???Œì¼: {self._shorten_path(self._data_file_path)}",
            font=ctk.CTkFont(size=11),
            text_color="#95a5a6",
            anchor="w",
        )
        self.data_path_label.grid(row=0, column=0, sticky="w", padx=0, pady=0)

        actions_frame = CTkFrame(path_row)
        actions_frame.grid(row=0, column=1, sticky="e")
        copy_btn = CTkButton(actions_frame, text="ê²½ë¡œ ë³µì‚¬", width=90, height=26, command=self._copy_data_path)
        copy_btn.grid(row=0, column=0, padx=(0, 6))
        open_btn = CTkButton(actions_frame, text="?´ë” ?´ê¸°", width=90, height=26, command=self._open_data_folder)
        open_btn.grid(row=0, column=1)

        # ?¤í¬ë¡?ê°€?¥í•œ ?°ì´???ì—­ (2???„ì²´)
        self.data_scroll = ctk.CTkScrollableFrame(data_frame)
        self.data_scroll.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=10, pady=5)
        self.data_scroll.grid_columnconfigure(0, weight=1)
        
        # ?¤ë” ?ì„±
        self.create_data_headers()
        
    # ëª©ë¡ ?˜ë‹¨ ë³´ì¡° ?µê³„ ?ì—­?€ ?¬ìš©?˜ì? ?ŠìŒ (?ë‹¨/?±ëŠ¥ ?¹ì…˜?¼ë¡œ ?´ë™)

    def set_exchange(self, exchange_name: str) -> None:
        """?„ì ¯???€??ê±°ë˜?Œë? ë³€ê²½í•˜ê³??°ì´?°ë? ?¤ì‹œ ë¡œë“œ"""
        try:
            if not exchange_name or exchange_name == self.exchange_name:
                return
            self.exchange_name = str(exchange_name).lower()

            # ?œëª© ?…ë°?´íŠ¸
            try:
                if hasattr(self, 'title_label') and self.title_label:
                    self.title_label.configure(text=f"?“š AI ?™ìŠµ ?°ì´????{self.exchange_name.upper()}")
            except Exception:
                pass

            # ê²½ë¡œ ?¬ê³„??ë°??¼ë²¨ ê°±ì‹ 
            try:
                from path_utils import get_exchange_ai_learning_data_path
                self._data_file_path = get_exchange_ai_learning_data_path(self.exchange_name)
            except Exception:
                base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')
                self._data_file_path = os.path.join(base_dir, f"ai_learning_data_{self.exchange_name}.json")
            try:
                if hasattr(self, 'data_path_label') and self.data_path_label:
                    self.data_path_label.configure(text=f"?“ ?°ì´???Œì¼: {self._shorten_path(self._data_file_path)}")
            except Exception:
                pass

            # ìºì‹œ ì´ˆê¸°?????¬ë¡œ??
            self._last_data_mtime = None
            self._recent_cache = None
            self._summary_cache = None
            self.learning_status_label.configure(text="ê±°ë˜??ë³€ê²? ?°ì´??ë¡œë”© ì¤?..")

            # ?°ì´???ì—­ ì´ˆê¸°??
            try:
                if hasattr(self, 'data_scroll') and self.data_scroll:
                    for w in self.data_scroll.winfo_children():
                        w.destroy()
                    self.create_data_headers()
            except Exception:
                pass

            self.load_learning_data_safe()
            # êµì²´ ???ë™ ?ˆë¡œê³ ì¹¨ ?¤ì?ì¤??¬ì„¤??
            try:
                if self.auto_refresh_enabled.get():
                    self._cancel_auto_refresh()
                    self._schedule_auto_refresh()
            except Exception:
                pass
        except Exception as e:
            try:
                self.learning_status_label.configure(text=f"?¤ë¥˜: {e}")
            except Exception:
                pass

    def _shorten_path(self, p: Optional[str]) -> str:
        try:
            if not p:
                return "(ê²½ë¡œ ?????†ìŒ)"
            home = os.path.expanduser('~')
            if p.startswith(home):
                return p.replace(home, '~')
            return p
        except Exception:
            return p or ""

    def _copy_data_path(self):
        try:
            if not self._data_file_path:
                return
            self.clipboard_clear()
            self.clipboard_append(self._data_file_path)
            self.learning_status_label.configure(text="?°ì´??ê²½ë¡œê°€ ?´ë¦½ë³´ë“œ??ë³µì‚¬?˜ì—ˆ?µë‹ˆ??")
        except Exception as e:
            print(f"ê²½ë¡œ ë³µì‚¬ ?¤ë¥˜: {e}")

    def _open_data_folder(self):
        try:
            if not self._data_file_path:
                return
            folder = os.path.dirname(self._data_file_path)
            if sys.platform.startswith('darwin'):
                subprocess.Popen(['open', folder])
            elif os.name == 'nt':
                os.startfile(folder)  # type: ignore[attr-defined]
            else:
                subprocess.Popen(['xdg-open', folder])
        except Exception as e:
            print(f"?´ë” ?´ê¸° ?¤ë¥˜: {e}")

    # -------------------- ?ë™ ?ˆë¡œê³ ì¹¨ --------------------
    def on_toggle_auto_refresh(self):
        try:
            if self.auto_refresh_enabled.get():
                self._schedule_auto_refresh()
                self.learning_status_label.configure(text=f"?ë™ ?ˆë¡œê³ ì¹¨: {self.auto_refresh_interval_sec}s")
            else:
                self._cancel_auto_refresh()
                self.learning_status_label.configure(text="?ë™ ?ˆë¡œê³ ì¹¨ ?´ì œ")
        except Exception:
            pass

    def on_interval_changed(self, value: str):
        try:
            v = str(value).lower().replace('s', '').strip()
            sec = int(v) if v.isdigit() else 60
            self.auto_refresh_interval_sec = max(5, sec)
            if self.auto_refresh_enabled.get():
                self._cancel_auto_refresh()
                self._schedule_auto_refresh()
        except Exception:
            self.auto_refresh_interval_sec = 60

    def _schedule_auto_refresh(self):
        try:
            # ì¤‘ë³µ ?ˆì•½ ë°©ì?
            self._cancel_auto_refresh()
            self._auto_refresh_job = self.safe_after(self.auto_refresh_interval_sec * 1000, self._auto_refresh_tick)
        except Exception:
            pass

    def _cancel_auto_refresh(self):
        try:
            if self._auto_refresh_job:
                try:
                    self.after_cancel(self._auto_refresh_job)
                except Exception:
                    pass
                self._auto_refresh_job = None
        except Exception:
            pass

    def _auto_refresh_tick(self):
        try:
            if not self.is_initialized or not self.auto_refresh_enabled.get():
                return
            if self._loading:
                # ?¤ìŒ ì£¼ê¸° ?¬ì‹œ??
                self._schedule_auto_refresh()
                return
            p = self._data_file_path
            if not p or not os.path.exists(p):
                self._schedule_auto_refresh()
                return
            mtime = os.path.getmtime(p)
            if self._last_data_mtime is None or mtime != self._last_data_mtime:
                # ë³€ê²?ê°ì? ?œë§Œ ë¡œë“œ
                self.load_learning_data_safe()
            self._schedule_auto_refresh()
        except Exception:
            # ?¤ë¥˜ ?œì—???¤ì?ì¤„ì? ? ì?
            self._schedule_auto_refresh()
        
    def create_data_headers(self):
        """?°ì´???Œì´ë¸??¤ë” ?ì„±"""
        headers = ["?œê°„", "ì½”ì¸", "?œê·¸??, "? ë¢°??, "ë³€?™ì„±", "?¸ë Œ?œê°•??, "ì§„ì…ê°€", "?´ìœ "]
        
        header_frame = CTkFrame(self.data_scroll)
        header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        # ì»¬ëŸ¼ ê°€ì¤‘ì¹˜: ë§ˆì?ë§?ì»¬ëŸ¼ë§??•ì¥
        for i in range(len(headers)):
            header_frame.grid_columnconfigure(i, weight=(1 if i == len(headers) - 1 else 0))
        for i, header in enumerate(headers):
            w = self._col_widths[i] if i < len(self._col_widths) else 100
            header_label = ctk.CTkLabel(
                header_frame,
                text=header,
                font=ctk.CTkFont(weight="bold"),
                width=w,
                anchor="w"
            )
            header_label.grid(row=0, column=i, padx=(4 if i == 0 else 2), pady=5, sticky="w")
            
    def create_stats_info(self):
        """(ë¯¸ì‚¬?? ëª©ë¡ ?ì—­ ë³´ì¡° ?µê³„ ?œê±° ? ì????”ë? ?¨ìˆ˜"""
        # ???´ìƒ ?¬ìš©?˜ì? ?ŠìŠµ?ˆë‹¤. ê¸°ì¡´ ?ˆì´?„ì›ƒ ?¸í™˜???„í•´ ?¨ê²¨?¡ë‹ˆ??
        pass
        
    def create_performance_section(self):
        """AI ?™ìŠµ ?µê³„ ?¹ì…˜ ?ì„± - ?•ë ¬ ê°œì„ """
        # ë°°ê²½ ?Œì˜ ?œê±°: ?¬ëª… ë°°ê²½ + ë³´ë” ?œê±°
        performance_frame = ctk.CTkFrame(self, fg_color="#0b1120", border_width=0)
        performance_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        # ëª¨ë“  ì»¬ëŸ¼?€ ê¸°ë³¸?ìœ¼ë¡??•ì¥?˜ì? ?ŠìŒ(ê³¼ë„??ê°„ê²© ë°©ì?)
        for col in range(3):
            performance_frame.grid_columnconfigure(col, weight=0)
        
        # ?œëª©
        # ?œëª© (?œê°„?€ ?ˆë‚´ë¥?ê´„í˜¸ë¡??¬í•¨)
        title_label = ctk.CTkLabel(
            performance_frame,
            text="?“Š AI ?™ìŠµ ?µê³„",
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color="#0b1120"
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 5))
        # ?œëª© ?‰ì—?œëŠ” ì¢Œì¸¡ ?•ë ¬ë§??¬ìš©
        
        # ?µê³„ ??ª©: ì¤‘ë³µ ?œê±°ë¥??„í•´ ì´ë¶„?ìˆ˜/?‰ê· ? ë¢°??ë§ˆì?ë§??…ë°?´íŠ¸ë§??œê¸°
        self.performance_labels = {}
        simplified_items = [
            ("ì´?ë¶„ì„ ??, "total_analysis", "0"),
            ("?‰ê·  ? ë¢°??, "avg_confidence", "0.0"),
            ("ë§ˆì?ë§??…ë°?´íŠ¸", "last_update", "N/A"),
        ]
        # ??ì¤„ë¡œ ë°°ì¹˜
        row_index = 1
        for col_index, (label, key, default) in enumerate(simplified_items):
            pair = ctk.CTkFrame(performance_frame, fg_color="#0b1120", border_width=0)
            pair.grid(row=row_index, column=col_index, sticky="w", padx=5, pady=3)
            label_widget = ctk.CTkLabel(pair, text=f"{label}:", font=ctk.CTkFont(size=12), fg_color="#0b1120")
            label_widget.pack(side="left")
            value_label = ctk.CTkLabel(pair, text=default, font=ctk.CTkFont(size=12, weight="bold"), text_color=self._color("success", "#27ae60"), fg_color="#0b1120")
            value_label.pack(side="left", padx=(6, 0))
            self.performance_labels[key] = value_label
        # ì»¬ëŸ¼ ?•ì¥ ê¸ˆì?: ì¢Œì¸¡ ?•ë ¬ ? ì?
        for col in range(3):
            performance_frame.grid_columnconfigure(col, weight=0)
            
    def load_learning_data_safe(self):
        """?™ìŠµ ?°ì´???ˆì „?˜ê²Œ ë¡œë“œ - ë¹„ë™ê¸?ì²˜ë¦¬"""
        try:
            if not self.is_initialized:
                return
            if self._loading:
                # ì¤‘ë³µ ë¡œë”© ë°©ì?
                self.learning_status_label.configure(text="?°ì´??ë¡œë”© ì¤?.. (?€ê¸?")
                return
                
            # ë¡œë”© ?íƒœ ?œì‹œ
            self.learning_status_label.configure(text="?°ì´??ë¡œë”© ì¤?..")
            self.learning_progress.set(0.1)
            
            # ë°±ê·¸?¼ìš´???¤ë ˆ?œì—???Œì¼ I/O + ?Œì‹± ?¤í–‰ (UI ë¸”ë¡ ë°©ì?)
            self._loading = True
            threading.Thread(target=self._load_data_async, daemon=True).start()
                
        except Exception as e:
            print(f"??AI ?™ìŠµ ?°ì´??ë¡œë“œ ?¤ë¥˜: {e}")
            self.learning_status_label.configure(text=f"?¤ë¥˜: {str(e)[:20]}...")
            try:
                # ?íƒœ ?¼ë²¨?€ ?„ì¬ ?”ë©´??ì§ì ‘ ?¸ì¶œ?˜ì? ?Šì?ë§? ì¡´ì¬?˜ëŠ” ê²½ìš°ë§??…ë°?´íŠ¸
                _lbl = getattr(self, 'auto_learning_label', None)
                if _lbl is not None:
                    try:
                        _lbl.configure(text="?¤– AI ?™ìŠµ ?¤ë¥˜")
                    except Exception:
                        pass
            except Exception:
                pass
    
    def _load_data_async(self):
        """ë¹„ë™ê¸??°ì´??ë¡œë“œ: ë°±ê·¸?¼ìš´?œì—???Œì¼ ?½ê¸° ??UI ê°±ì‹ ?€ ë©”ì¸?¤ë ˆ?œë¡œ ?„ì„"""
        try:
            from trading.exchange_learning_manager import ExchangeLearningManager
            exchange_manager = ExchangeLearningManager(self.exchange_name)
            data_file = exchange_manager._get_exchange_learning_path()
            print(f"?” AI ?™ìŠµ ?°ì´???Œì¼ ê²½ë¡œ: {data_file}")
            print(f"?” ?Œì¼ ì¡´ì¬ ?¬ë?: {os.path.exists(data_file)}")
            
            # UI ?ë‹¨ ê²½ë¡œ ?¼ë²¨ ìµœì‹ ??
            try:
                self._data_file_path = data_file
                self.safe_after(0, lambda: self.data_path_label.configure(text=f"?“ ?°ì´???Œì¼: {self._shorten_path(self._data_file_path)}"))
            except Exception:
                pass

            if not os.path.exists(data_file):
                print(f"? ï¸ AI ?™ìŠµ ?°ì´???Œì¼??ì°¾ì„ ???†ìŠµ?ˆë‹¤. (ê±°ë˜?? {self.exchange_name})")
                print(f"? ï¸ ì°¾ëŠ” ê²½ë¡œ: {data_file}")
                self._update_ui_from_bg([], message="?°ì´???Œì¼ ?†ìŒ", ready=False)
                return

            t0 = time.perf_counter()
            mtime = os.path.getmtime(data_file)
            # ?Œì¼??ë°”ë€Œì? ?Šì•˜?¤ë©´ ìºì‹œ ?¬ìš©
            if self._last_data_mtime is not None and mtime == self._last_data_mtime and self._recent_cache is not None and self._summary_cache is not None:
                self._update_ui_from_bg(self._recent_cache, perf_summary=self._summary_cache, message="ë³€ê²??†ìŒ - ìºì‹œ ?¬ìš©")
                return

            # ?Œì¼ I/O + JSON ?Œì‹± (ë°±ê·¸?¼ìš´??
            with open(data_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # ?°ì´???¬ê¸° ê´€ë¦?(ë°±ê·¸?¼ìš´??
            try:
                # ê³¼ë„???°ê¸° ë°©ì?ë¥??„í•´ ìµœì†Œ 10ë¶?ê°„ê²©?¼ë¡œë§??•ë¦¬
                now = time.time()
                if self._last_compact_time is None or (now - self._last_compact_time) > 600:
                    self._manage_data_size(data_file, data)
                    self._last_compact_time = now
            except Exception as ce:
                print(f"?°ì´???¬ê¸° ê´€ë¦??¤í‚µ/?¤ë¥˜: {ce}")

            recent_data = data[-50:] if len(data) > 50 else data

            # ë°±ê·¸?¼ìš´?œì—???±ëŠ¥ ?”ì•½ ê³„ì‚° (UI ?¤ë ˆ??ë¶€???œê±°)
            summary = self._calc_performance_summary(data)

            # ë©”ì¸ ?¤ë ˆ?œì—??UI ?…ë°?´íŠ¸(?”ì•½ë§?ë°˜ì˜)
            load_ms = (time.perf_counter() - t0) * 1000.0
            self._recent_cache = list(recent_data)
            self._summary_cache = dict(summary)
            self._last_data_mtime = mtime
            self._update_ui_from_bg(recent_data, perf_summary=summary, message=f"?°ì´??ë¡œë“œ ?„ë£Œ ({len(data)}ê°?ì¤?ìµœê·¼ {len(recent_data)}ê°??œì‹œ, {load_ms:.0f}ms)")

        except Exception as e:
            print(f"??AI ?™ìŠµ ?°ì´??ë¡œë“œ ?¤ë¥˜: {e}")
            self._update_ui_from_bg([], message=f"?¤ë¥˜: {str(e)[:20]}...", ready=False)

    def _update_ui_from_bg(self, recent_data: List[dict], full_data: List[dict] | None = None, perf_summary: Dict[str, Any] | None = None, message: str = "", ready: bool = True):
        """ë°±ê·¸?¼ìš´???¤ë ˆ?œì—???¸ì¶œ: UI ë³€ê²½ì? ?ˆì „?˜ê²Œ afterë¡?ë©”ì¸?¤ë ˆ?œì—???˜í–‰"""
        try:
            def _apply():
                try:
                    self.learning_progress.set(0.5 if recent_data else 0)
                    if recent_data:
                        # ìµœì‹  ??ª©???ë‹¨?¼ë¡œ ?¤ë„ë¡??œê°„ ê¸°ì? ??ˆœ ?•ë ¬
                        sorted_recent = sorted(
                            recent_data,
                            key=lambda it: (self._item_local_dt(it) or datetime.min.replace(tzinfo=self._get_display_tz())),
                            reverse=True
                        )
                        self.update_learning_table_safe(sorted_recent)
                    if perf_summary is not None:
                        self.update_performance_indicators_from_summary(perf_summary)
                    self.learning_status_label.configure(text=message or ("?°ì´??ë¡œë“œ ?„ë£Œ" if ready else "?°ì´???†ìŒ"))
                    # 'AI ?™ìŠµ ?œì„±?? ë¬¸êµ¬???ë‹¨ ë°°ì?ë¡??€ì²?
                    self.learning_progress.set(1.0 if recent_data else 0)
                except Exception as ie:
                    print(f"UI ê°±ì‹  ?¤ë¥˜: {ie}")
                finally:
                    self._loading = False
            # ë°±ê·¸?¼ìš´???¤ë ˆ?œì—??UI ?…ë°?´íŠ¸ë¥??„í•´ ì§ì ‘ ?¸ì¶œ
            try:
                import threading
                current_thread = threading.current_thread()
                main_thread = threading.main_thread()
                
                if current_thread is main_thread:
                    # ë©”ì¸ ?¤ë ˆ?œì—??ì§ì ‘ ?¤í–‰
                    _apply()
                else:
                    # ë°±ê·¸?¼ìš´???¤ë ˆ?œì—?œëŠ” after ?¬ìš©
                    self.after(0, _apply)
            except Exception as e:
                print(f"UI ?…ë°?´íŠ¸ ?¤ì?ì¤„ë§ ?¤ë¥˜: {e}")
                _apply()  # ?´ë°±: ì§ì ‘ ?¤í–‰
        except Exception as e:
            print(f"UI ê°±ì‹  ?ˆì•½ ?¤ë¥˜: {e}")
            self._loading = False

    def _calc_performance_summary(self, data: List[dict]) -> Dict[str, Any]:
        """ë°±ê·¸?¼ìš´?œì—??ê³„ì‚°??ê°„ë‹¨???±ëŠ¥ ?”ì•½ (? ì§œë³??„í„°ë§??¬í•¨)."""
        try:
            total = len(data)
            long_count = 0
            short_count = 0
            hold_count = 0
            conf_sum = 0.0
            conf_cnt = 0
            
            # ? ì§œë³??„í„°ë§ì„ ?„í•œ ê¸°ì? ?œê°„ ?¤ì •
            tz = self._get_display_tz()
            now = datetime.now(tz)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            
            today_count = 0
            weekly_count = 0
            
            for item in data:
                # ?œê·¸??ì¹´ìš´??(?€/?Œë¬¸?? ê³µë°± ?€ë¹?
                sig = str(item.get('signal', '')).strip().upper()
                if sig == 'LONG':
                    long_count += 1
                elif sig == 'SHORT':
                    short_count += 1
                elif sig == 'HOLD':
                    hold_count += 1
                
                # ? ë¢°??ê³„ì‚°
                c = item.get('confidence')
                if isinstance(c, (int, float)):
                    conf_sum += float(c)
                    conf_cnt += 1
                
                # ? ì§œë³??„í„°ë§?
                try:
                    ts = item.get('timestamp', '')
                    if ts:
                        item_dt_local = self._item_local_dt(item)
                        if item_dt_local is None:
                            continue
                        if item_dt_local >= today_start:
                            today_count += 1
                        if item_dt_local >= week_start:
                            weekly_count += 1
                            
                except Exception:
                    # ?Œì‹± ?¤íŒ¨ ??ë¬´ì‹œ
                    pass
            
            avg_conf = (conf_sum / conf_cnt) if conf_cnt > 0 else 0.0
            
            return {
                'total_analysis': total,
                'long_signals': long_count,
                'short_signals': short_count,
                'hold_signals': hold_count,
                'avg_confidence': avg_conf,
                'today_count': today_count,
                'weekly_count': weekly_count,
                'last_update': datetime.now().strftime("%H:%M:%S"),
            }
            
        except Exception as e:
            print(f"?±ëŠ¥ ?”ì•½ ê³„ì‚° ?¤ë¥˜: {e}")
            return {
                'total_analysis': 0,
                'long_signals': 0,
                'short_signals': 0,
                'hold_signals': 0,
                'avg_confidence': 0.0,
                'today_count': 0,
                'weekly_count': 0,
                'last_update': datetime.now().strftime("%H:%M:%S"),
            }
            
    def update_performance_indicators_from_summary(self, s: Dict[str, Any]):
        """UI ?¤ë ˆ?œì—???”ì•½ ê²°ê³¼ë§?ë°˜ì˜ (ë¹ ë¦„) - ? ì§œë³??µê³„ ?¬í•¨."""
        try:
            self.performance_labels['total_analysis'].configure(text=str(s.get('total_analysis', 0)))
            self.performance_labels['avg_confidence'].configure(text=f"{float(s.get('avg_confidence', 0.0)):.2f}")
            self.performance_labels['last_update'].configure(text=s.get('last_update', 'N/A'))
            
            # ? ì§œë³??µê³„???ë‹¨ ë°??¸ë?)?ì„œë§??œì‹œ
            today_count = s.get('today_count', 0)
            weekly_count = s.get('weekly_count', 0)
            # ?¸ë?(?ë‹¨ ë°?ë¡??”ì•½???„ë‹¬ (? íƒ??
            if self.on_summary_update:
                try:
                    payload = {
                        'today_count': today_count,
                        'weekly_count': weekly_count,
                        'long_signals': int(s.get('long_signals', 0)),
                        'short_signals': int(s.get('short_signals', 0)),
                        'hold_signals': int(s.get('hold_signals', 0)),
                        'total_analysis': int(s.get('total_analysis', 0)),
                        'avg_confidence': float(s.get('avg_confidence', 0.0)),
                        'last_update': s.get('last_update', 'N/A'),
                    }
                    self.on_summary_update(payload)
                except Exception:
                    pass
            
        except Exception as e:
            print(f"?±ëŠ¥ ?”ì•½ ë°˜ì˜ ?¤ë¥˜: {e}")

    # --- ?ì§„??ì²?¬) ?Œë”ë§ìœ¼ë¡?UI ?„ë¦¬ì§?ë°©ì? ---
    def _clear_data_rows(self):
        try:
            for widget in self.data_scroll.winfo_children():
                try:
                    # ?¤ë”(0)ë§??¨ê¸°ê³?ê·??´í•˜ ???œê±°
                    if isinstance(widget, CTkFrame) and widget.grid_info().get('row', 0) > 0:
                        widget.destroy()
                except Exception:
                    pass
        except Exception:
            pass

    def _render_rows_incremental(self, data: List[dict], start: int = 0, chunk: int = 15):
        try:
            end = min(start + chunk, len(data))
            for idx in range(start, end):
                # ?¤ë” ë°”ë¡œ ?„ë˜ë¶€????1) ì±„ìš°ê¸?
                self.create_data_row_safe(data[idx], idx + 1)
            if end < len(data):
                # ?¤ìŒ ì²?¬ ?ˆì•½
                self.safe_after(0, self._render_rows_incremental, data, end, chunk)
        except Exception as e:
            print(f"?ì§„ ?Œë”ë§??¤ë¥˜: {e}")
    
    def _manage_data_size(self, data_file, data):
        """?°ì´???¬ê¸° ê´€ë¦?""
        try:
            # ?Œì¼ ?¬ê¸° ?•ì¸
            file_size = os.path.getsize(data_file)
            file_size_mb = file_size / (1024 * 1024)
            
            # 5MB ?´ìƒ?´ë©´ ìµœê·¼ 2000ê°œë§Œ ? ì?
            if file_size_mb > 5.0 or len(data) > 2000:
                print(f"? ï¸ ?°ì´???¬ê¸° ê´€ë¦? {file_size_mb:.2f}MB, {len(data)}ê°???ª©")
                
                # ìµœê·¼ 2000ê°œë§Œ ? ì?
                if len(data) > 2000:
                    data = data[-2000:]
                    
                    # ë°±ì—… ?Œì¼ ?ì„±
                    backup_file = data_file.replace('.json', '_backup.json')
                    with open(backup_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    # ?ë³¸ ?Œì¼ ?…ë°?´íŠ¸
                    with open(data_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    
                    print(f"???°ì´???¬ê¸° ìµœì ???„ë£Œ: {len(data)}ê°???ª© ? ì?, ë°±ì—…: {backup_file}")
                    
        except Exception as e:
            print(f"???°ì´???¬ê¸° ê´€ë¦??¤ë¥˜: {e}")
    
    def refresh_learning_data_safe(self):
        """AI ?™ìŠµ ?°ì´???ˆì „?˜ê²Œ ?ˆë¡œê³ ì¹¨"""
        try:
            if not self.is_initialized:
                return
                
            self.learning_status_label.configure(text="?ˆë¡œê³ ì¹¨ ì¤?..")
            self.load_learning_data_safe()
            
        except Exception as e:
            print(f"??AI ?™ìŠµ ?°ì´???ˆë¡œê³ ì¹¨ ?¤ë¥˜: {e}")
            self.learning_status_label.configure(text=f"?¤ë¥˜: {str(e)[:20]}...")
    
    def update_learning_table_safe(self, data):
        """AI ?™ìŠµ ?°ì´???Œì´ë¸??ˆì „?˜ê²Œ ?…ë°?´íŠ¸"""
        try:
            if not self.is_initialized:
                return
                
            # ê¸°ì¡´ ?°ì´???‰ë“¤ ?œê±° ???ì§„???Œë”ë§??œì‘
            self._clear_data_rows()
            self._render_rows_incremental(data, start=0, chunk=20)
                
        except Exception as e:
            print(f"AI ?™ìŠµ ?Œì´ë¸??…ë°?´íŠ¸ ?¤ë¥˜: {e}")
    
    def create_data_row_safe(self, item, row):
        """?°ì´?????ˆì „?˜ê²Œ ?ì„±"""
        try:
            row_frame = CTkFrame(self.data_scroll)
            row_frame.grid(row=row, column=0, sticky="ew", padx=5, pady=2)
            # ì»¬ëŸ¼ ê°€ì¤‘ì¹˜: ë§ˆì?ë§?ì»¬ëŸ¼ë§??•ì¥
            for i in range(8):
                row_frame.grid_columnconfigure(i, weight=(1 if i == 7 else 0))
            
            # ?œê°„ (timestamp)
            ts = item.get('timestamp', 'N/A')
            time_str = str(ts)
            try:
                dt_local = self._item_local_dt(item)
                if dt_local is not None:
                    time_str = dt_local.strftime("%H:%M:%S")
                elif isinstance(ts, str):
                    time_str = ts[:5] if len(ts) >= 5 else ts
            except Exception:
                pass
            
            # ê°?ì»¬ëŸ¼ ?°ì´???œì‹œ
            symbol = str(item.get('symbol', 'N/A'))
            signal = str(item.get('signal', 'N/A'))
            confidence = item.get('confidence', 'N/A')
            volatility = item.get('market_volatility', item.get('rsi', 'N/A'))
            trend_strength = item.get('trend_strength', item.get('macd', 'N/A'))
            entry_price = item.get('entry_price', 'N/A')
            reason_text = item.get('reason', item.get('reasoning', 'N/A'))

            columns = [
                time_str,
                symbol,
                signal,
                f"{confidence:.1f}" if isinstance(confidence, (int, float)) else str(confidence),
                f"{volatility:.4f}" if isinstance(volatility, (int, float)) else str(volatility),
                f"{trend_strength:.4f}" if isinstance(trend_strength, (int, float)) else str(trend_strength),
                f"{entry_price}" if not isinstance(entry_price, (int, float)) else f"{entry_price:g}",
                (str(reason_text)[:self._reason_max_chars] + "...") if len(str(reason_text)) > self._reason_max_chars else str(reason_text)
            ]
            
            for i, col_data in enumerate(columns):
                w = self._col_widths[i] if i < len(self._col_widths) else 100
                label = ctk.CTkLabel(
                    row_frame,
                    text=col_data,
                    width=w,
                    anchor="w"
                )
                label.grid(row=0, column=i, padx=(4 if i == 0 else 2), pady=2, sticky="w")
                
        except Exception as e:
            print(f"?°ì´?????ì„± ?¤ë¥˜: {e}")
    
    def update_performance_indicators_safe(self, data):
        """AI ?™ìŠµ ?µê³„ ?ˆì „?˜ê²Œ ?…ë°?´íŠ¸"""
        try:
            if not self.is_initialized or not data:
                return
                
            # ì´?ë¶„ì„ ?°ì´????
            total = len(data)
            self.performance_labels['total_analysis'].configure(text=str(total))
            
            # ?œê·¸?ë³„ ê°œìˆ˜ ê³„ì‚° (UI ?œì‹œ???œê±°, ?ë‹¨ ?”ì•½ ì½œë°±?ë§Œ ?¬ìš©)
            long_count = sum(1 for item in data if str(item.get('signal', '')).strip().upper() == 'LONG')
            short_count = sum(1 for item in data if str(item.get('signal', '')).strip().upper() == 'SHORT')
            hold_count = sum(1 for item in data if str(item.get('signal', '')).strip().upper() == 'HOLD')
            
            # ?‰ê·  ? ë¢°??ê³„ì‚°
            confidences = [item.get('confidence', 0) for item in data if isinstance(item.get('confidence'), (int, float))]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                self.performance_labels['avg_confidence'].configure(text=f"{avg_confidence:.2f}")
            else:
                self.performance_labels['avg_confidence'].configure(text="0.0")
            
            # ë§ˆì?ë§??…ë°?´íŠ¸
            self.performance_labels['last_update'].configure(text=datetime.now().strftime("%H:%M:%S"))
            
            # ? ì§œë³??µê³„ ê³„ì‚° ë°??…ë°?´íŠ¸ (ê¸°ì¡´ ?¨ìˆ˜?ë„ ?ìš©)
            tz = self._get_display_tz()
            now = datetime.now(tz)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            
            today_count = 0
            weekly_count = 0
            
            for item in data:
                try:
                    ts = item.get('timestamp', '')
                    if ts:
                        item_dt_local = self._item_local_dt(item)
                        if item_dt_local is None:
                            continue
                        if item_dt_local >= today_start:
                            today_count += 1
                        if item_dt_local >= week_start:
                            weekly_count += 1
                except Exception:
                    pass
            
            # ? ì§œë³??¼ë²¨?€ ëª©ë¡ ?ì—­?ì„œ ?œì‹œ?˜ì? ?ŠìŒ
            # ?ë‹¨ ì½œë°± ?…ë°?´íŠ¸ (?ˆê±°??ê²½ë¡œ)
            if self.on_summary_update:
                try:
                    payload = {
                        'today_count': today_count,
                        'weekly_count': weekly_count,
                        'long_signals': long_count,
                        'short_signals': short_count,
                        'hold_signals': hold_count,
                        'total_analysis': total,
                        'avg_confidence': float(self.performance_labels['avg_confidence'].cget('text')) if self.performance_labels.get('avg_confidence') else 0.0,
                        'last_update': datetime.now(self._get_display_tz()).strftime("%H:%M:%S"),
                    }
                    self.on_summary_update(payload)
                except Exception:
                    pass
        except Exception as e:
            print(f"AI ?™ìŠµ ?µê³„ ?…ë°?´íŠ¸ ?¤ë¥˜: {e}")

    # ?¸ë?(?€?œë³´???ì„œ ?”ì•½ ?•ë³´ë¥?ë°›ì„ ì½œë°± ì§€??
    def set_summary_callback(self, cb: Callable[[Dict[str, Any]], None]):
        try:
            self.on_summary_update = cb
        except Exception:
            self.on_summary_update = None

    # -------------------- ?œê°„?€/?€?„ìŠ¤?¬í”„ ? í‹¸ --------------------
    def _get_display_tz(self):
        """?œì‹œ???œê°„?€ (KST ?°ì„ , ë¶ˆê? ??ë¡œì»¬ ?œê°„?€)"""
        try:
            if ZoneInfo is not None:
                return ZoneInfo("Asia/Seoul")
        except Exception:
            pass
        try:
            return datetime.now().astimezone().tzinfo or timezone.utc
        except Exception:
            return timezone.utc

    def _parse_ts(self, ts_val):
        """?¤ì–‘???•ì‹??timestampë¥?aware datetime(UTC ê¸°ë³¸)?¼ë¡œ ?Œì‹±"""
        try:
            if isinstance(ts_val, datetime):
                return ts_val if ts_val.tzinfo else ts_val.replace(tzinfo=timezone.utc)
            if not ts_val:
                return None
            s = str(ts_val)
            if 'T' in s:
                s2 = s.replace('Z', '+00:00')
                dt = datetime.fromisoformat(s2)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    def _item_local_dt(self, item: dict):
        """?„ì´???€?„ìŠ¤?¬í”„ë¥??œì‹œ ?œê°„?€(KST/ë¡œì»¬)ë¡?ë³€??""
        try:
            dt = self._parse_ts(item.get('timestamp'))
            if dt is None:
                return None
            return dt.astimezone(self._get_display_tz())
        except Exception:
            return None
