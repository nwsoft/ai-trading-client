#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사용자 제공 전략 소스를 실행 가능한 커스텀 전략 초안으로 변환한다.

지원 입력: 일반 텍스트, Pine Script, PDF, 이미지/OCR, 로컬 영상,
YouTube 링크(자막 우선), TradingView 공개 스크립트 링크. 추출 결과는 곧바로
주문하지 않고 CustomStrategyPipeline의 승인/검증 절차로 전달된다.
"""

from __future__ import annotations

import html
import hashlib
import json
import logging
import re
import tempfile
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

try:
    import requests
except Exception:  # 텍스트/Pine/로컬 파일은 네트워크 패키지 없이도 동작
    requests = None  # type: ignore

from trading.ai.chart_screenshot_analyzer import ChartScreenshotAnalyzer
from trading.ai.openai_client import OpenAIClient


@dataclass
class ExtractedStrategySource:
    kind: str
    reference: str
    title: str
    text: str
    warnings: List[str]
    evidence: Dict[str, Any]


class StrategySourceIngestor:
    """소스를 추출하고 AI가 누락 조건을 숨기지 않는 전략 초안을 만든다."""

    REQUIRED_RULES = (
        "entry", "exit", "stop_loss", "take_profit", "position_size", "market_conditions"
    )
    YOUTUBE_HOSTS = {
        "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
        "youtu.be", "youtube-nocookie.com", "www.youtube-nocookie.com",
    }
    PDF_MAX_PAGES = 100
    AI_CONTENT_CHAR_LIMIT = 60000
    VIDEO_SAMPLE_FRAMES = 9
    YOUTUBE_AUDIO_MAX_BYTES = 24 * 1024 * 1024
    YOUTUBE_AUDIO_MAX_DURATION_SECONDS = 45 * 60

    def __init__(
        self,
        ai_client: Optional[OpenAIClient] = None,
        logger: Optional[logging.Logger] = None,
        *,
        transcription_client: Optional[Any] = None,
        transcription_enabled: bool = True,
        transcription_model: str = "gpt-4o-mini-transcribe",
        audio_max_duration_minutes: int = 45,
        audio_max_file_mb: int = 24,
    ):
        self.ai_client = ai_client
        self.transcription_client = transcription_client or ai_client
        self.logger = logger or logging.getLogger(__name__)
        self.transcription_enabled = bool(transcription_enabled)
        self.transcription_model = str(transcription_model or "gpt-4o-mini-transcribe")
        self.youtube_audio_max_duration_seconds = max(1, int(audio_max_duration_minutes)) * 60
        self.youtube_audio_max_bytes = max(1, int(audio_max_file_mb)) * 1024 * 1024

    @staticmethod
    def detect_kind(value: str, explicit_kind: str = "auto") -> str:
        if explicit_kind and explicit_kind != "auto":
            return explicit_kind.lower().strip()
        raw = str(value or "").strip()
        lower = raw.lower()
        if lower.startswith(("http://", "https://")):
            host = urlparse(lower).netloc
            if host in StrategySourceIngestor.YOUTUBE_HOSTS:
                return "youtube"
            if "tradingview.com" in host:
                return "tradingview"
            return "url"
        suffix = Path(raw).suffix.lower()
        if suffix in {'.csv', '.tsv', '.xlsx', '.docx'}:
            return 'document'
        if suffix == ".pdf":
            return "pdf"
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            return "image"
        if suffix in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            return "video"
        if suffix in {".pine", ".pinescript"} or "strategy.entry" in lower or "indicator(" in lower:
            return "pine"
        return "text"

    def extract(self, value: str, kind: str = "auto") -> ExtractedStrategySource:
        if str(value).startswith('noah-bundle:'):
            from .strategy_source_bundle import extract_bundle,MAX_BYTES
            paths = json.loads(str(value)[12:])
            if not isinstance(paths,list) or not 1 <= len(paths) <= 40: raise ValueError('자료는 1~40개입니다.')
            if any(not Path(p).is_file() or Path(p).stat().st_size>24*1024*1024 for p in paths) or sum(Path(p).stat().st_size for p in paths)>MAX_BYTES:
                raise ValueError('파일 크기/경로를 확인하세요.')
            return extract_bundle(self,[{'value':p,'name':Path(p).name,'kind':'auto'} for p in paths])
        resolved = self.detect_kind(value, kind)
        if resolved == 'document':
            from .strategy_source_bundle import office_text
            path = Path(value)
            text = office_text(path) if path.suffix.lower() in {'.xlsx','.docx'} else path.read_text(encoding='utf-8-sig')
            return ExtractedStrategySource('document', str(path), path.name, text, [], {'file_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
        if resolved in {"text", "pine"}:
            raw_value = str(value or "").strip()
            path = Path(raw_value)
            try:
                is_file = "\n" not in raw_value and len(raw_value) < 1024 and path.exists() and path.is_file()
            except OSError:
                is_file = False
            if is_file:
                text = path.read_text(encoding="utf-8", errors="replace")
                return ExtractedStrategySource(resolved, str(path), path.stem, text, [], {"path": str(path)})
            return ExtractedStrategySource(resolved, "pasted", "사용자 입력 전략", str(value or ""), [], {})
        if resolved == "pdf":
            return self._extract_pdf(value)
        if resolved == "image":
            return self._extract_image(value)
        if resolved == "video":
            return self._extract_video(value)
        if resolved == "youtube":
            return self._extract_youtube(value)
        if resolved in {"tradingview", "url"}:
            return self._extract_web(value, tradingview=(resolved == "tradingview"))
        raise ValueError(f"지원하지 않는 전략 입력 형식입니다: {resolved}")

    def _extract_pdf(self, value: str) -> ExtractedStrategySource:
        path = Path(value).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"PDF 파일을 찾을 수 없습니다: {path}")
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise RuntimeError("PDF 분석 구성요소(pypdf)가 설치되지 않았습니다.") from exc
        reader = PdfReader(str(path))
        total_pages = len(reader.pages)
        analyzed_pages = min(total_pages, self.PDF_MAX_PAGES)
        pages = [(reader.pages[index].extract_text() or "").strip() for index in range(analyzed_pages)]
        text = "\n\n".join(item for item in pages if item)
        warnings = [] if text else ["텍스트가 없는 스캔 PDF입니다. 페이지를 이미지로 저장해 OCR 입력을 이용하세요."]
        if total_pages > self.PDF_MAX_PAGES:
            warnings.append(
                f"PDF {total_pages}쪽 중 앞 {self.PDF_MAX_PAGES}쪽까지만 추출했습니다. 나머지는 파일을 나눠 입력하세요."
            )
        if len(text) > self.AI_CONTENT_CHAR_LIMIT:
            warnings.append(
                f"추출 텍스트 {len(text):,}자 중 앞 {self.AI_CONTENT_CHAR_LIMIT:,}자를 AI 구조화에 사용합니다."
            )
        return ExtractedStrategySource(
            "pdf", str(path), path.stem, text, warnings,
            {"pages": total_pages, "analyzed_pages": analyzed_pages, "extracted_characters": len(text)},
        )

    def _vision_strategy_text(self, image_path: str, title: str) -> str:
        """OCR만으로 알 수 없는 선·마커·지표 배치를 비전 모델로 구조화한다."""
        if not self.ai_client or not self.ai_client.is_ready() or not hasattr(self.ai_client, "vision_json"):
            return ""
        result = self.ai_client.vision_json(
            (
                "You inspect user-owned trading chart material. Return JSON only. "
                "Describe only visible evidence; never invent hidden rules or exact values."
            ),
            (
                f"자료: {title}\n"
                "화면에서 보이는 차트 종류, 타임프레임, 지표와 파라미터, 선/영역, "
                "매수·매도·손절·익절 마커, 진입/청산 관계를 한국어로 구조화하세요. "
                "명확하지 않은 항목은 unknown으로 표시하세요."
            ),
            [image_path],
            max_tokens=1600,
        )
        return json.dumps(result, ensure_ascii=False) if isinstance(result, dict) and result else ""

    def _extract_image(self, value: str) -> ExtractedStrategySource:
        path = Path(value).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {path}")
        analyzer = ChartScreenshotAnalyzer(openai_client=self.ai_client)
        text, info = analyzer._extract_text(str(path))  # 기존 차트 OCR 엔진을 단일 경로로 재사용
        vision_text = self._vision_strategy_text(str(path), path.stem)
        warnings = [str(info["warning"])] if info.get("warning") else []
        if self.ai_client and self.ai_client.is_ready() and not vision_text:
            warnings.append("비전 AI가 차트 화면을 구조화하지 못해 OCR 텍스트만 사용했습니다.")
        combined = f"OCR:\n{text}\n\n비전 AI 화면 근거:\n{vision_text}".strip()
        return ExtractedStrategySource(
            "image", str(path), path.stem, combined, warnings,
            {"ocr": info, "vision_ai_available": bool(vision_text)},
        )

    @staticmethod
    def _write_contact_sheet(cv2_module: Any, frames: List[Any], output_path: Path) -> bool:
        """대표 프레임을 한 장으로 묶어 비전 AI 호출 횟수와 비용을 제한한다."""
        if not frames:
            return False
        try:
            columns = 3
            width, height = 480, 270
            thumbnails = [cv2_module.resize(frame, (width, height)) for frame in frames]
            while len(thumbnails) % columns:
                import numpy as np
                thumbnails.append(np.zeros((height, width, 3), dtype="uint8"))
            rows = [cv2_module.hconcat(thumbnails[index:index + columns]) for index in range(0, len(thumbnails), columns)]
            sheet = cv2_module.vconcat(rows)
            return bool(cv2_module.imwrite(str(output_path), sheet))
        except Exception:
            return False

    def _extract_video(self, value: str) -> ExtractedStrategySource:
        path = Path(value).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"영상 파일을 찾을 수 없습니다: {path}")
        try:
            import cv2
        except Exception as exc:
            raise RuntimeError("영상 프레임 분석 구성요소(OpenCV)가 설치되지 않았습니다.") from exc

        capture = cv2.VideoCapture(str(path))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 1.0)
        duration = frame_count / max(fps, 1.0)
        sample_seconds = sorted({
            max(0.0, duration * index / max(self.VIDEO_SAMPLE_FRAMES - 1, 1))
            for index in range(self.VIDEO_SAMPLE_FRAMES)
        })
        analyzer = ChartScreenshotAnalyzer(openai_client=self.ai_client)
        extracted: List[str] = []
        warnings: List[str] = []
        visual_text = ""
        sampled_frames: List[Any] = []
        with tempfile.TemporaryDirectory(prefix="noahai_strategy_video_") as temp_dir:
            for index, second in enumerate(sample_seconds):
                capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                sampled_frames.append(frame)
                frame_path = Path(temp_dir) / f"frame_{index}.jpg"
                cv2.imwrite(str(frame_path), frame)
                text, info = analyzer._extract_text(str(frame_path))
                if text:
                    extracted.append(f"[화면 {second:.1f}초] {text}")
                if info.get("warning") and str(info["warning"]) not in warnings:
                    warnings.append(str(info["warning"]))
            contact_sheet = Path(temp_dir) / "representative_frames.jpg"
            if self._write_contact_sheet(cv2, sampled_frames, contact_sheet):
                visual_text = self._vision_strategy_text(str(contact_sheet), f"{path.stem} 대표 장면")
        capture.release()
        if not extracted and not visual_text:
            warnings.append("샘플 프레임에서 전략 문자를 찾지 못했습니다. 자막/설명 텍스트를 함께 입력하세요.")
        if self.ai_client and self.ai_client.is_ready() and not visual_text:
            warnings.append("대표 장면 비전 분석을 수행하지 못해 화면 OCR만 사용했습니다.")
        return ExtractedStrategySource(
            "video", str(path), path.stem,
            f"화면 OCR:\n{' '.join(extracted)}\n\n비전 AI 대표 장면:\n{visual_text}".strip(), warnings,
            {
                "duration_seconds": round(duration, 2),
                "sampled_frames": len(sampled_frames),
                "vision_ai_available": bool(visual_text),
                "audio_transcript_available": False,
            },
        )

    @staticmethod
    def _youtube_id(url: str) -> str:
        """watch, Shorts, 공유, embed, live 주소를 동일한 영상 ID로 정규화한다."""
        raw = str(url or "").strip()
        if not raw:
            return ""
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        host = parsed.netloc.lower().split(":", 1)[0]
        path_parts = [part for part in parsed.path.split("/") if part]
        candidate = ""
        if host == "youtu.be" and path_parts:
            candidate = path_parts[0]
        elif host in StrategySourceIngestor.YOUTUBE_HOSTS:
            candidate = str((parse_qs(parsed.query).get("v") or [""])[0])
            if not candidate and len(path_parts) >= 2 and path_parts[0].lower() in {
                "shorts", "embed", "live", "v",
            }:
                candidate = path_parts[1]
        candidate = candidate.strip()
        return candidate if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", candidate) else ""

    @staticmethod
    def _youtube_canonical_url(video_id: str) -> str:
        return f"https://www.youtube.com/watch?v={video_id}"

    @staticmethod
    def _brief_error(exc: Exception) -> str:
        text = str(exc or "").strip()
        return (text.splitlines()[0] if text else exc.__class__.__name__)[:300]

    @staticmethod
    def _transcript_to_text(transcript: Any) -> str:
        items: List[str] = []
        for item in transcript or []:
            if isinstance(item, dict):
                value = item.get("text", "")
            else:
                value = getattr(item, "text", "")
            value = html.unescape(str(value or "")).replace("\n", " ").strip()
            if value:
                items.append(value)
        return " ".join(items).strip()

    def _fetch_youtube_transcript(self, video_id: str) -> tuple[str, str]:
        """수동/자동 자막을 언어 우선순위대로 찾고 구·신 API를 모두 지원한다."""
        from youtube_transcript_api import YouTubeTranscriptApi

        languages = ["ko", "ko-KR", "en", "en-US", "en-GB"]
        api = YouTubeTranscriptApi()
        try:
            transcript = api.fetch(video_id, languages=languages)
            return self._transcript_to_text(transcript), "youtube_transcript_api"
        except (AttributeError, TypeError):
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=languages)
            return self._transcript_to_text(transcript), "youtube_transcript_api"
        except Exception as first_error:
            # 선호 언어가 없더라도 영상에 공개된 수동/자동 자막이 있으면 사용한다.
            try:
                transcript_list = api.list(video_id)
                available = list(transcript_list)
                if not available:
                    raise first_error
                preference = {code: index for index, code in enumerate(languages)}
                available.sort(key=lambda item: (
                    preference.get(str(getattr(item, "language_code", "")), len(preference)),
                    bool(getattr(item, "is_generated", False)),
                ))
                return self._transcript_to_text(available[0].fetch()), "youtube_transcript_api_fallback"
            except Exception:
                raise first_error

    @staticmethod
    def _caption_candidates(info: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        language_rank = ("ko", "ko-kr", "en", "en-us", "en-gb")
        for source_name in ("subtitles", "automatic_captions"):
            captions = info.get(source_name) or {}
            for language, formats in captions.items():
                if str(language).lower() == "live_chat":
                    continue
                for item in formats or []:
                    if not isinstance(item, dict) or not item.get("url"):
                        continue
                    lang = str(language).lower()
                    rank = next(
                        (index for index, preferred in enumerate(language_rank)
                         if lang == preferred or lang.startswith(preferred + "-")),
                        len(language_rank),
                    )
                    ext = str(item.get("ext") or "").lower()
                    format_rank = {"json3": 0, "vtt": 1, "srv3": 2, "ttml": 3}.get(ext, 9)
                    candidates.append({**item, "language": language, "rank": (rank, format_rank)})
        return sorted(candidates, key=lambda item: item["rank"])

    def _transcript_from_ytdlp_info(self, info: Dict[str, Any]) -> tuple[str, str]:
        if requests is None:
            return "", ""
        headers = dict(info.get("http_headers") or {})
        for candidate in self._caption_candidates(info)[:12]:
            try:
                response = requests.get(candidate["url"], headers=headers, timeout=15)
                response.raise_for_status()
                ext = str(candidate.get("ext") or "").lower()
                if ext == "json3":
                    payload = response.json()
                    text = " ".join(
                        str(segment.get("utf8") or "").replace("\n", " ").strip()
                        for event in payload.get("events", [])
                        for segment in event.get("segs", [])
                        if str(segment.get("utf8") or "").strip()
                    )
                else:
                    raw = re.sub(r"<[^>]+>", " ", response.text)
                    raw = re.sub(r"^WEBVTT.*$|^\d+$|^\d{2}:\d{2}:[\d.,]+\s+-->.*$", " ", raw, flags=re.M)
                    text = re.sub(r"\s+", " ", html.unescape(raw)).strip()
                if text:
                    return text, f"yt_dlp_{candidate.get('language', 'caption')}"
            except Exception:
                continue
        return "", ""

    @staticmethod
    def _video_stream_url(info: Dict[str, Any]) -> str:
        if info.get("url"):
            return str(info["url"])
        requested = list(info.get("requested_formats") or [])
        formats = list(info.get("formats") or [])
        for item in requested + list(reversed(formats)):
            if isinstance(item, dict) and item.get("url") and str(item.get("vcodec") or "none") != "none":
                return str(item["url"])
        return ""

    def _transcribe_youtube_audio(self, url: str, duration: float) -> str:
        if not self.transcription_enabled:
            return ""
        if (
            not self.transcription_client
            or not self.transcription_client.is_ready()
            or not hasattr(self.transcription_client, "transcribe_audio")
        ):
            return ""
        if duration and duration > self.youtube_audio_max_duration_seconds:
            return ""
        from yt_dlp import YoutubeDL

        with tempfile.TemporaryDirectory(prefix="noahai_youtube_audio_") as temp_dir:
            output_template = str(Path(temp_dir) / "strategy_audio.%(ext)s")
            options = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "socket_timeout": 20,
                "retries": 1,
                "fragment_retries": 1,
                "format": "worstaudio[ext=m4a]/worstaudio[ext=webm]/worstaudio/worst",
                "outtmpl": output_template,
                "max_filesize": self.youtube_audio_max_bytes,
            }
            with YoutubeDL(options) as ydl:
                ydl.download([url])
            audio_files = [path for path in Path(temp_dir).iterdir() if path.is_file()]
            if not audio_files:
                return ""
            audio_path = max(audio_files, key=lambda path: path.stat().st_size)
            if audio_path.stat().st_size > self.youtube_audio_max_bytes:
                return ""
            if self.transcription_client is None:
                return ""
            return str(
                self.transcription_client.transcribe_audio(
                    str(audio_path),
                    model=self.transcription_model,
                ) or ""
            ).strip()

    def _extract_youtube(self, url: str) -> ExtractedStrategySource:
        video_id = self._youtube_id(url)
        if not video_id:
            raise ValueError("YouTube 영상 ID를 확인할 수 없습니다. watch, Shorts, youtu.be 주소인지 확인하세요.")
        canonical_url = self._youtube_canonical_url(video_id)
        warnings: List[str] = []
        transcript_text = ""
        transcript_source = ""
        screen_text = ""
        screen_evidence: Dict[str, Any] = {}
        try:
            transcript_text, transcript_source = self._fetch_youtube_transcript(video_id)
        except Exception as exc:
            warnings.append(f"YouTube 공개 자막을 가져오지 못했습니다: {self._brief_error(exc)}")

        title = f"YouTube {video_id}"
        description = ""
        try:
            if requests is None:
                raise RuntimeError("requests 패키지가 설치되지 않았습니다.")
            response = requests.get(
                "https://www.youtube.com/oembed",
                params={"url": canonical_url, "format": "json"}, timeout=12,
                headers={"User-Agent": "NoahAI/3.9.0.0"},
            )
            response.raise_for_status()
            metadata = response.json()
            title = str(metadata.get("title") or title)
            description = f"제목: {title}\n제작자: {metadata.get('author_name', '')}"
        except Exception as exc:
            warnings.append(f"영상 메타데이터를 가져오지 못했습니다: {exc}")

        try:
            from yt_dlp import YoutubeDL
            ydl_options = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
                "socket_timeout": 20,
                "retries": 1,
                "fragment_retries": 1,
                "format": "worst[height<=480][ext=mp4]/worst[height<=480]/worst",
            }
            with YoutubeDL(ydl_options) as ydl:
                info = dict(ydl.extract_info(canonical_url, download=False) or {})
            if not transcript_text:
                transcript_text, transcript_source = self._transcript_from_ytdlp_info(info)
            if not transcript_text:
                transcript_text = self._transcribe_youtube_audio(
                    canonical_url, float(info.get("duration") or 0.0)
                )
                if transcript_text:
                    transcript_source = "openai_audio_transcription"
            if transcript_text and transcript_source.startswith(("yt_dlp_", "openai_audio_")):
                warnings = [
                    warning for warning in warnings
                    if not warning.startswith("YouTube 공개 자막을 가져오지 못했습니다:")
                ]
            stream_url = self._video_stream_url(info)
            if stream_url:
                screen_evidence = self._sample_remote_video_evidence(stream_url)
                if screen_evidence.get("ocr_text") or screen_evidence.get("vision_text"):
                    screen_text = (
                        f"화면 OCR:\n{screen_evidence.get('ocr_text', '')}\n\n"
                        f"비전 AI 대표 장면:\n{screen_evidence.get('vision_text', '')}"
                    ).strip()
        except Exception as exc:
            warnings.append(f"영상·음성 대체 분석을 수행하지 못했습니다: {self._brief_error(exc)}")
        if not screen_text:
            warnings.append("영상 화면의 차트/지표 문자를 확인하지 못했습니다. 중요한 장면 스크린샷을 추가하면 함께 분석합니다.")
        if not transcript_text and not screen_text:
            warnings.append("자막과 화면 근거가 없어 진입·청산 조건을 자동 확정하지 않습니다. 영상 파일/스크린샷 또는 조건 텍스트를 추가하세요.")
        evidence_available = bool(transcript_text or screen_text)
        return ExtractedStrategySource(
            "youtube", canonical_url, title,
            f"{description}\n\n자막/음성 전사:\n{transcript_text}\n\n화면 OCR/비전:\n{screen_text}".strip(), warnings,
            {
                "video_id": video_id,
                "original_url": url,
                "canonical_url": canonical_url,
                "transcript_available": bool(transcript_text),
                "transcript_source": transcript_source,
                "audio_transcript_available": transcript_source == "openai_audio_transcription",
                "transcription_model": self.transcription_model if transcript_source == "openai_audio_transcription" else "",
                "transcription_limit_minutes": self.youtube_audio_max_duration_seconds // 60,
                "transcription_limit_mb": self.youtube_audio_max_bytes // (1024 * 1024),
                "screen_ocr_available": bool(screen_evidence.get("ocr_text")),
                "sampled_frames": int(screen_evidence.get("sampled_frames", 0) or 0),
                "vision_ai_available": bool(screen_evidence.get("vision_text")),
                "strategy_evidence_available": evidence_available,
            },
        )

    def _sample_remote_video_evidence(self, stream_url: str) -> Dict[str, Any]:
        """YouTube 읽기 전용 스트림의 대표 화면을 OCR+비전 AI로 분석한다."""
        try:
            import cv2
        except Exception:
            return {"ocr_text": "", "vision_text": "", "sampled_frames": 0}
        capture = cv2.VideoCapture(stream_url)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 1.0)
        duration = frame_count / max(fps, 1.0)
        seconds = [0.0, 30.0, 90.0]
        if duration > 0:
            seconds = sorted({
                max(0.0, duration * index / max(self.VIDEO_SAMPLE_FRAMES - 1, 1))
                for index in range(self.VIDEO_SAMPLE_FRAMES)
            })
        analyzer = ChartScreenshotAnalyzer(openai_client=self.ai_client)
        texts: List[str] = []
        frames: List[Any] = []
        vision_text = ""
        with tempfile.TemporaryDirectory(prefix="noahai_youtube_frames_") as temp_dir:
            for index, second in enumerate(seconds[:self.VIDEO_SAMPLE_FRAMES]):
                capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
                ok, frame = capture.read()
                if not ok:
                    continue
                frames.append(frame)
                frame_path = Path(temp_dir) / f"youtube_{index}.jpg"
                cv2.imwrite(str(frame_path), frame)
                text, _ = analyzer._extract_text(str(frame_path))
                if text:
                    texts.append(f"[{second:.1f}초] {text}")
            contact_sheet = Path(temp_dir) / "youtube_representative_frames.jpg"
            if self._write_contact_sheet(cv2, frames, contact_sheet):
                vision_text = self._vision_strategy_text(str(contact_sheet), "YouTube 대표 장면")
        capture.release()
        return {
            "ocr_text": "\n".join(texts),
            "vision_text": vision_text,
            "sampled_frames": len(frames),
        }

    def _extract_web(self, url: str, *, tradingview: bool) -> ExtractedStrategySource:
        if requests is None:
            raise RuntimeError("웹 링크 분석 구성요소(requests)가 설치되지 않았습니다.")
        response = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0 NoahAI/3.9.0.0"})
        response.raise_for_status()
        body = response.text
        title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.I | re.S)
        title = html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1))).strip() if title_match else url
        descriptions = re.findall(
            r"<meta[^>]+(?:name|property)=[\"'](?:description|og:description)[\"'][^>]+content=[\"'](.*?)[\"']",
            body, flags=re.I | re.S,
        )
        code_blocks = re.findall(r"(?:strategy|indicator)\s*\([^<]{0,12000}", html.unescape(body), flags=re.I)
        text = "\n".join([title] + [html.unescape(item) for item in descriptions[:3]] + code_blocks[:2])
        warnings: List[str] = []
        if tradingview and not code_blocks:
            warnings.append("공개 페이지에서 Pine 원문이 노출되지 않았습니다. 작성자가 공개한 Pine 코드를 붙여 넣으면 정확히 규칙화할 수 있습니다.")
        return ExtractedStrategySource(
            "tradingview" if tradingview else "url", url, title, text, warnings,
            {"http_status": response.status_code, "pine_found": bool(code_blocks)},
        )

    @staticmethod
    def _number(pattern: str, text: str) -> Optional[float]:
        match = re.search(pattern, text, flags=re.I)
        return float(match.group(1)) if match else None

    @staticmethod
    def _explicit_percent(label_pattern: str, text: str) -> tuple[Optional[float], bool]:
        """Return a percent only when the source explicitly contains `%`.

        A unitless TP/SL number may be a price, ATR multiple, fraction, or percent.
        Guessing here changes the strategy, so the second return value records an
        ambiguous unit that must be clarified by the user.
        """
        explicit = re.search(
            rf"(?:{label_pattern})[^\d]{{0,16}}(\d+(?:\.\d+)?)\s*%",
            text,
            flags=re.I,
        )
        if explicit:
            return float(explicit.group(1)), False
        ambiguous = re.search(
            rf"(?:{label_pattern})[^\d]{{0,16}}(\d+(?:\.\d+)?)",
            text,
            flags=re.I,
        )
        return None, bool(ambiguous)

    @staticmethod
    def _risk_budget_percent(text: str) -> Optional[float]:
        """Read an explicitly stated per-trade account-loss budget.

        The number must carry a percent sign and be tied to both one trade and
        account loss/risk.  This deliberately does not infer a budget from TP,
        SL, leverage, or a generic position percentage.
        """
        patterns = (
            r"(?:거래\s*(?:당|한\s*번(?:에서)?)|1\s*회)[^\n%]{0,48}?"
            r"(?:계좌(?:의)?\s*)?(?:최대\s*)?(?:손실|위험|허용\s*손실)[^\d%]{0,12}"
            r"(\d+(?:\.\d+)?)\s*%",
            r"(?:거래\s*(?:당|한\s*번(?:에서)?)|1\s*회)[^\n%]{0,48}?"
            r"(\d+(?:\.\d+)?)\s*%\s*(?:까지\s*)?(?:의\s*)?(?:손실|위험)",
            r"(?:risk\s*per\s*trade|per[\s_-]*trade\s*(?:account\s*)?(?:loss|risk))"
            r"[^\d%]{0,16}(\d+(?:\.\d+)?)\s*%",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return float(match.group(1))
        return None

    @staticmethod
    def _margin_budget_percent(text: str) -> Optional[float]:
        """Read an explicit maximum margin/position allocation percentage."""
        match = re.search(
            r"(?:증거금(?:\s*사용(?:률|은|을)?)?|최대\s*증거금|"
            r"포지션\s*(?:크기|비중)|자산\s*(?:사용|비중)?|종목당\s*투자\s*비중)"
            r"[^\d%]{0,20}(\d+(?:\.\d+)?)\s*%",
            text,
            flags=re.I,
        )
        return float(match.group(1)) if match else None

    @staticmethod
    def _pine_operand_field(value: str) -> str:
        normalized = re.sub(r"\s+", "", str(value or "").lower())
        if normalized == "close":
            return "current_price"
        match = re.fullmatch(r"(?:ta\.)?(ema|sma)\(close,(20|50|200)\)", normalized)
        return f"{match.group(1)}{match.group(2)}" if match else ""

    def _heuristic_rules(self, source: ExtractedStrategySource) -> Dict[str, Any]:
        text = source.text or ""
        lower = text.lower()
        sentences = [item.strip() for item in re.split(r"[\n;.!?]+", text) if item.strip()]
        entry_lines = [
            item for item in sentences
            if re.search(r"strategy\.entry|진입|매수|\bentry\b|longcondition|shortcondition", item, flags=re.I)
        ]
        exit_lines = [
            item for item in sentences
            if re.search(r"strategy\.exit|strategy\.close|청산|매도|종료|\bexit\b|\bclose\b|exitcondition", item, flags=re.I)
        ]
        sl, sl_unit_ambiguous = self._explicit_percent(r"stop[_\s-]*loss|손절|\bsl\b", text)
        tp, tp_unit_ambiguous = self._explicit_percent(r"take[_\s-]*profit|익절|\btp\b", text)
        position = self._number(r"(?:position[_\s-]*size|포지션\s*크기|자산)[^\d]{0,14}(\d+(?:\.\d+)?)\s*%", text)
        risk_per_trade = self._risk_budget_percent(text)
        margin_budget = self._margin_budget_percent(text)
        if margin_budget is not None:
            position = margin_budget
        leverage = self._number(r"(?:leverage|레버리지)[^\d]{0,10}(\d+(?:\.\d+)?)", text)
        indicators = sorted(set(re.findall(r"\b(RSI|MACD|EMA|SMA|ATR|ADX|VWAP|BOLLINGER|SUPERTREND)\b", text, flags=re.I)))
        rules: Dict[str, Any] = {
            "entry": " | ".join(item.strip() for item in entry_lines[:6]),
            "exit": " | ".join(item.strip() for item in exit_lines[:6]),
            "stop_loss": f"{sl}%" if sl is not None else "",
            "take_profit": f"{tp}%" if tp is not None else "",
            "position_size": f"{position}%" if position is not None else "",
            "market_conditions": "",
            "engine_settings": {},
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "signal_mode": "confirm",
            "entry_signal": "",
            "compiler_issues": [],
            "source_evidence": asdict(source),
        }
        engine = rules["engine_settings"]
        executable = rules["executable_entry"]
        executable_exit = rules["executable_exit"]

        def natural_rsi_condition(sentence: str) -> Optional[Dict[str, Any]]:
            normalized = str(sentence or "")
            symbolic = re.search(
                r"\brsi(?:\s*\(\s*\d+\s*\))?\s*(?:값?이|가|는)?\s*"
                r"(<=|>=|<|>)\s*(\d+(?:\.\d+)?)",
                normalized,
                flags=re.I,
            )
            if symbolic:
                operator, threshold = symbolic.groups()
                return {
                    "field": "rsi",
                    "operator": {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[operator],
                    "value": float(threshold),
                }
            korean = re.search(
                r"\brsi(?:\s*\(\s*\d+\s*\))?\s*(?:값?이|가|는)?\s*"
                r"(\d+(?:\.\d+)?)\s*(이하|미만|이상|초과)",
                normalized,
                flags=re.I,
            )
            if korean:
                threshold, comparison = korean.groups()
                return {
                    "field": "rsi",
                    "operator": {"이하": "lte", "미만": "lt", "이상": "gte", "초과": "gt"}[comparison],
                    "value": float(threshold),
                }
            english = re.search(
                r"\brsi(?:\s*\(\s*\d+\s*\))?\s*(?:is\s*)?"
                r"(below|under|above|over)\s*(\d+(?:\.\d+)?)",
                normalized,
                flags=re.I,
            )
            if english:
                comparison, threshold = english.groups()
                return {
                    "field": "rsi",
                    "operator": "lt" if comparison.lower() in {"below", "under"} else "gt",
                    "value": float(threshold),
                }
            return None

        natural_branches: Dict[str, List[Dict[str, Any]]] = {"LONG": [], "SHORT": []}
        for sentence in re.split(r"[,\n;.!?]+", text):
            condition = natural_rsi_condition(sentence)
            if not condition:
                continue
            sentence_lower = sentence.lower()
            target = (
                executable_exit
                if any(token in sentence_lower for token in ("청산", "매도", "종료", "exit", "close"))
                else executable
                if any(token in sentence_lower for token in ("진입", "매수", "entry", "long", "short"))
                else None
            )
            if target is not None and condition not in target["all"]:
                target["all"].append(condition)
            if target is executable:
                sentence_lower = sentence.lower()
                direction = (
                    "LONG" if ("long" in sentence_lower or "롱" in sentence or "매수" in sentence)
                    else "SHORT" if ("short" in sentence_lower or "숏" in sentence or "공매도" in sentence)
                    else ""
                )
                if direction and condition not in natural_branches[direction]:
                    natural_branches[direction].append(condition)

        rsi_match = re.search(r"(?:ta\.)?rsi\([^\)]*\)\s*(<=|>=|<|>)\s*(\d+(?:\.\d+)?)", text, flags=re.I)
        if rsi_match:
            op = {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[rsi_match.group(1)]
            condition = {"field": "rsi", "operator": op, "value": float(rsi_match.group(2))}
            if condition not in executable["all"]:
                executable["all"].append(condition)
        for match in re.finditer(
            r"close\s*(<=|>=|<|>)\s*(?:ta\.)?(ema|sma)\s*\(\s*close\s*,\s*(20|50|200)\s*\)",
            text,
            flags=re.I,
        ):
            comparison, average_type, period = match.groups()
            field = f"{average_type.lower()}{period}"
            operator = {"<": "lt_field", "<=": "lt_field", ">": "gt_field", ">=": "gt_field"}[comparison]
            executable["all"].append({
                "field": "current_price", "operator": operator, "value_field": field,
            })
        for match in re.finditer(
            r"(?:ta\.)?(ema|sma)\s*\(\s*close\s*,\s*(20|50|200)\s*\)\s*"
            r"(<=|>=|<|>)\s*(?:ta\.)?(ema|sma)\s*\(\s*close\s*,\s*(20|50|200)\s*\)",
            text,
            flags=re.I,
        ):
            left_type, left_period, comparison, right_type, right_period = match.groups()
            executable["all"].append({
                "field": f"{left_type.lower()}{left_period}",
                "operator": "lt_field" if comparison.startswith("<") else "gt_field",
                "value_field": f"{right_type.lower()}{right_period}",
            })
        pine_operand = (
            r"(?:close|(?:ta\.)?(?:ema|sma)\s*\(\s*close\s*,\s*(?:20|50|200)\s*\))"
        )
        for match in re.finditer(
            rf"(?:ta\.)?(crossover|crossunder)\s*\(\s*({pine_operand})\s*,\s*"
            rf"({pine_operand})\s*\)",
            text,
            flags=re.I,
        ):
            cross_type, left_operand, right_operand = match.groups()
            left_field = self._pine_operand_field(left_operand)
            right_field = self._pine_operand_field(right_operand)
            if left_field and right_field:
                executable["all"].append({
                    "field": left_field,
                    "operator": (
                        "crosses_above" if cross_type.lower() == "crossover"
                        else "crosses_below"
                    ),
                    "value_field": right_field,
                })
        # Resolve the common Pine alias shape instead of treating `if alias` as
        # an unconditional direction. Unknown data-flow remains fail-closed.
        pine_rsi_aliases = {
            name: "rsi"
            for name in re.findall(
                r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*(?:ta\.)?rsi\s*\([^\)]*\)\s*$",
                text,
                flags=re.I,
            )
        }
        pine_conditions: Dict[str, List[Dict[str, Any]]] = {}
        for alias, operand, operator, threshold in re.findall(
            r"\b([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*(<=|>=|<|>)\s*(\d+(?:\.\d+)?)",
            text,
            flags=re.I,
        ):
            field = pine_rsi_aliases.get(operand)
            if field:
                pine_conditions[alias] = [{
                    "field": field,
                    "operator": {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[operator],
                    "value": float(threshold),
                }]
        # Compile a common Pine boolean alias when every AND term is supported.
        # A partially understood expression must never be marked executable.
        for alias, expression in re.findall(
            r"(?m)^\s*([A-Za-z_]\w*)\s*=\s*(.+?)\s*$", text,
        ):
            if alias in pine_rsi_aliases or alias in pine_conditions:
                continue
            if re.search(r"\bor\b|\|\|", expression, flags=re.I):
                continue
            compiled_terms: List[Dict[str, Any]] = []
            terms = [item.strip() for item in re.split(r"\band\b|&&", expression, flags=re.I) if item.strip()]
            for term in terms:
                condition: Optional[Dict[str, Any]] = None
                direct_rsi = re.fullmatch(
                    r"(?:ta\.)?rsi\s*\([^\)]*\)\s*(<=|>=|<|>)\s*(\d+(?:\.\d+)?)",
                    term,
                    flags=re.I,
                )
                alias_rsi = re.fullmatch(
                    r"([A-Za-z_]\w*)\s*(<=|>=|<|>)\s*(\d+(?:\.\d+)?)",
                    term,
                    flags=re.I,
                )
                price_average = re.fullmatch(
                    r"close\s*(<=|>=|<|>)\s*(?:ta\.)?(ema|sma)\s*\(\s*close\s*,\s*(20|50|200)\s*\)",
                    term,
                    flags=re.I,
                )
                if direct_rsi:
                    operator, threshold = direct_rsi.groups()
                    condition = {
                        "field": "rsi",
                        "operator": {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[operator],
                        "value": float(threshold),
                    }
                elif alias_rsi and alias_rsi.group(1) in pine_rsi_aliases:
                    operand, operator, threshold = alias_rsi.groups()
                    condition = {
                        "field": pine_rsi_aliases[operand],
                        "operator": {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}[operator],
                        "value": float(threshold),
                    }
                elif price_average:
                    operator, average_type, period = price_average.groups()
                    condition = {
                        "field": "current_price",
                        "operator": "lt_field" if operator.startswith("<") else "gt_field",
                        "value_field": f"{average_type.lower()}{period}",
                    }
                if condition is None:
                    compiled_terms = []
                    break
                compiled_terms.append(condition)
            if compiled_terms and len(compiled_terms) == len(terms):
                pine_conditions[alias] = compiled_terms
        for alias in re.findall(r"\bif\s+([A-Za-z_]\w*)\s*\n\s*strategy\.entry", text, flags=re.I):
            conditions = pine_conditions.get(alias)
            if conditions:
                for condition in conditions:
                    if condition not in executable["all"]:
                        executable["all"].append(condition)
            else:
                rules["compiler_issues"].append(f"pine_entry_condition_unresolved:{alias}")

        has_long_entry = "strategy.long" in lower or bool(natural_branches["LONG"])
        has_short_entry = "strategy.short" in lower or bool(natural_branches["SHORT"])
        if has_long_entry and has_short_entry:
            if natural_branches["LONG"] and natural_branches["SHORT"]:
                rules["signal_mode"] = "independent"
                rules["independent_entries"] = {
                    direction: {"all": conditions, "any": []}
                    for direction, conditions in natural_branches.items()
                }
                rules["entry_signal"] = ""
                executable["all"] = []
            else:
                # 양방향 Pine 조건이 분리되지 않으면 한 방향으로 축소하지 않는다.
                rules["entry_signal"] = ""
                rules["compiler_issues"].append("dual_direction_conditions_not_separated")
        elif has_long_entry:
            rules["entry_signal"] = "LONG"
            signal_condition = {"field": "signal", "operator": "eq", "value": "LONG"}
            if signal_condition not in executable["all"]:
                executable["all"].append(signal_condition)
        elif has_short_entry:
            rules["entry_signal"] = "SHORT"
            signal_condition = {"field": "signal", "operator": "eq", "value": "SHORT"}
            if signal_condition not in executable["all"]:
                executable["all"].append(signal_condition)
        elif any("long" in item.lower() or "롱" in item for item in entry_lines):
            rules["entry_signal"] = "LONG"
        elif any("short" in item.lower() or "숏" in item for item in entry_lines):
            rules["entry_signal"] = "SHORT"
        if sl_unit_ambiguous:
            rules["compiler_issues"].append("stop_loss_unit_missing")
        if tp_unit_ambiguous:
            rules["compiler_issues"].append("take_profit_unit_missing")
        if sl is not None:
            engine["sl_percent"] = sl
        if tp is not None:
            engine["tp_percent"] = tp
        if position is not None:
            engine["position_size"] = position / 100.0
        effective_margin_budget = margin_budget if margin_budget is not None else position
        if risk_per_trade is not None or effective_margin_budget is not None or leverage is not None:
            risk_model: Dict[str, Any] = {}
            if risk_per_trade is not None:
                risk_model["risk_per_trade_percent"] = risk_per_trade
            if effective_margin_budget is not None:
                risk_model["max_margin_usage_percent"] = effective_margin_budget
            if leverage is not None:
                risk_model["max_leverage"] = int(leverage) if float(leverage).is_integer() else leverage
            rules["risk_model"] = risk_model
        if leverage is not None:
            engine["leverage"] = int(leverage) if float(leverage).is_integer() else leverage
            if not float(leverage).is_integer() or not 1 <= leverage <= 10:
                rules["compiler_issues"].append("leverage_out_of_supported_range")
        regime_hint = self.infer_market_regimes(text)
        if regime_hint.get("auto_select"):
            rules["market_conditions"] = list(regime_hint.get("labels") or [])
        is_pine = source.kind == "pine" or "//@version" in lower or "strategy(" in lower
        if is_pine:
            unsupported_pine = (
                (r"\brequest\.security\s*\(", "pine_multitimeframe_request_not_supported"),
                (r"\binput\.(?:int|float|string|bool|timeframe|source)\s*\(", "pine_dynamic_input_requires_user_confirmation"),
                (r"\b(?:array|matrix|map)\.", "pine_collection_not_supported"),
                (r"(?m)^\s*[A-Za-z_]\w*\s*\([^\n]*\)\s*=>", "pine_custom_function_not_supported"),
                (r"\bta\.(?:highest|lowest|valuewhen|barssince)\s*\(", "pine_rolling_state_not_supported"),
                (r"\bstrategy\.position_avg_price\b", "pine_position_price_exit_not_supported"),
            )
            for pattern, issue in unsupported_pine:
                if re.search(pattern, text, flags=re.I) and issue not in rules["compiler_issues"]:
                    rules["compiler_issues"].append(issue)
        # 텍스트 자체가 충분한 경우에도 근거 문장을 보존한다.
        if not rules["entry"] and any(token in lower for token in ("cross", "돌파", "다이버전스")):
            rules["entry"] = "소스에 진입 단서가 있으나 정확한 AND/OR 조건은 사용자 확인 필요"
        return rules

    def _coverage_summary(self, source: ExtractedStrategySource) -> str:
        evidence = source.evidence or {}
        if source.kind == "pdf":
            return (
                f"PDF {evidence.get('analyzed_pages', 0)}/{evidence.get('pages', 0)}쪽 · "
                f"추출 {int(evidence.get('extracted_characters', 0) or 0):,}자 · "
                f"AI 입력 최대 {self.AI_CONTENT_CHAR_LIMIT:,}자"
            )
        if source.kind in {"video", "youtube"}:
            parts = [f"대표 장면 {int(evidence.get('sampled_frames', 0) or 0)}개"]
            if source.kind == "youtube":
                transcript_source = str(evidence.get("transcript_source") or "")
                if transcript_source == "openai_audio_transcription":
                    parts.append("영상 음성 AI 전사")
                else:
                    parts.append("자막 있음" if evidence.get("transcript_available") else "자막 없음")
            elif not evidence.get("audio_transcript_available"):
                parts.append("로컬 영상 음성 전사 미포함")
            parts.append("비전 AI 사용" if evidence.get("vision_ai_available") else "화면 OCR 중심")
            return " · ".join(parts)
        if source.kind == "image":
            return "차트 OCR + 비전 AI" if evidence.get("vision_ai_available") else "차트 OCR"
        if source.kind == "tradingview":
            return "공개 Pine 원문 확인" if evidence.get("pine_found") else "공개 설명/메타데이터만 확인"
        return f"입력 텍스트 {len(source.text or ''):,}자"

    @staticmethod
    def _build_source_rule_trace(source: ExtractedStrategySource, rules: Dict[str, Any]) -> Dict[str, Any]:
        """원문 근거와 실행 규칙의 연결을 저장해 조용한 조건 변환을 막는다."""
        text = str(source.text or "").strip()
        lines = [line.strip() for line in re.split(r"[\n;]+", text) if line.strip()]
        keyword_map = {
            "entry": ("진입", "매수", "entry", "long", "short", "crossover", "crossunder"),
            "exit": ("청산", "매도", "exit", "close"),
            "stop_loss": ("손절", "stop", "sl"),
            "take_profit": ("익절", "take profit", "tp"),
            "position_size": ("포지션", "position", "수량", "자산", "위험예산", "계좌 손실", "증거금"),
            "market_conditions": ("상승", "하락", "횡보", "변동", "trend", "range", "volatility"),
        }
        trace: Dict[str, Any] = {}
        for field, keywords in keyword_map.items():
            value = rules.get(field)
            matches = [
                line[:500] for line in lines
                if any(keyword in line.lower() for keyword in keywords)
            ][:3]
            trace[field] = {
                "status": "matched" if value and matches else "missing",
                "rule_value": value,
                "evidence": matches,
                "source_kind": source.kind,
                "source_reference": source.reference,
            }
        return trace

    @staticmethod
    def _execution_contract_digest(rules: Dict[str, Any]) -> str:
        """Hash only fields that can change signal direction or order risk."""
        engine = dict(rules.get("engine_settings") or {})
        payload = {
            "entry": rules.get("entry"),
            "exit": rules.get("exit"),
            "stop_loss": rules.get("stop_loss"),
            "take_profit": rules.get("take_profit"),
            "position_size": rules.get("position_size"),
            "market_conditions": rules.get("market_conditions"),
            "signal_mode": rules.get("signal_mode"),
            "entry_signal": rules.get("entry_signal"),
            "executable_entry": rules.get("executable_entry"),
            "executable_exit": rules.get("executable_exit"),
            "independent_entries": rules.get("independent_entries"),
            "exit_policy": rules.get("exit_policy"),
            "risk_model": rules.get("risk_model"),
            "engine_settings": {
                key: engine.get(key)
                for key in ("_unit", "tp_percent", "sl_percent", "position_size", "leverage", "signal_threshold")
                if key in engine
            },
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @classmethod
    def _ai_execution_diff(cls, proposed: Dict[str, Any], compiled: Dict[str, Any]) -> List[str]:
        """Report AI-proposed execution fields that the deterministic compiler did not prove.

        The proposal is never copied into the executable draft.  This comparison is
        retained for XAI so a user can see that a fluent model response was rejected.
        """
        proposed_engine = dict(proposed.get("engine_settings") or {})
        compiled_engine = dict(compiled.get("engine_settings") or {})
        paths = (
            "signal_mode", "entry_signal", "executable_entry", "executable_exit",
            "independent_entries", "exit_policy", "risk_model",
        )
        rejected = [path for path in paths if proposed.get(path) not in (None, "", {}, []) and proposed.get(path) != compiled.get(path)]
        for key in ("tp_percent", "sl_percent", "position_size", "leverage", "signal_threshold"):
            if key in proposed_engine and proposed_engine.get(key) != compiled_engine.get(key):
                rejected.append(f"engine_settings.{key}")
        return rejected

    @staticmethod
    def _user_supplement_conflicts(
        original: Dict[str, Any],
        supplement: Dict[str, Any],
    ) -> List[str]:
        """Reject a confirmation overlay that changes an already-declared rule.

        Guided clarification may fill a missing field.  It is not a hidden edit
        channel for replacing source-owned direction, entry/exit semantics, or
        risk.  A user who wants to change an existing value must edit the source
        (or create a declared override version) and run analysis again.
        """
        def meaningful(path: str, value: Any) -> bool:
            if value in (None, "", [], {}):
                return False
            if path in {"executable_entry", "executable_exit"} and isinstance(value, dict):
                return bool(value.get("all") or value.get("any") or value.get("expression"))
            if path == "independent_entries" and isinstance(value, dict):
                return any(
                    meaningful("executable_entry", branch)
                    for branch in value.values()
                    if isinstance(branch, dict)
                )
            return True

        conflicts: List[str] = []
        for key in (
            "entry", "exit", "stop_loss", "take_profit", "position_size",
            "market_conditions", "entry_signal", "executable_entry",
            "executable_exit", "independent_entries", "risk_model",
        ):
            original_value = original.get(key)
            supplement_value = supplement.get(key)
            if not meaningful(key, original_value):
                continue
            if not meaningful(key, supplement_value):
                continue
            if supplement_value != original_value:
                conflicts.append(key)

        original_engine = dict(original.get("engine_settings") or {})
        supplement_engine = dict(supplement.get("engine_settings") or {})
        for key in ("tp_percent", "sl_percent", "position_size", "leverage", "signal_threshold"):
            if key not in original_engine or key not in supplement_engine:
                continue
            if original_engine.get(key) != supplement_engine.get(key):
                conflicts.append(f"engine_settings.{key}")
        return sorted(set(conflicts))

    @staticmethod
    def infer_market_regimes(text: str, market_conditions: Any = "") -> Dict[str, Any]:
        """소스에 명시된 시장국면만 추천한다.

        LONG/SHORT 방향만으로 상승장·하락장을 추정하지 않는다. 여러 국면이
        명시되면 모두 보존하고, 근거가 없으면 사용자 확인이 필요한 all을 반환한다.
        """
        combined = f"{text or ''}\n{market_conditions or ''}".lower()
        explicit_all_market = bool(re.search(
            r"사용\s*시장상황\s*:\s*(?:모든|전체)\s*시장(?:상황)?",
            combined,
            flags=re.I,
        ))
        definitions = (
            ("bull", "상승장", (r"상승장", r"강세장", r"상승\s*추세", r"\bbull(?:ish)?(?:\s+market|\s+regime)?\b", r"\buptrend\b")),
            ("bear", "하락장", (r"하락장", r"약세장", r"하락\s*추세", r"\bbear(?:ish)?(?:\s+market|\s+regime)?\b", r"\bdowntrend\b")),
            ("range", "횡보장", (r"횡보장", r"횡보\s*구간", r"박스권", r"\bsideways\b", r"\brange(?:\s+bound)?\b")),
            ("volatile", "고변동성", (r"고변동", r"높은\s*변동성", r"\bhigh[\s_-]*vol(?:atility)?\b")),
            ("calm", "저변동성", (r"저변동", r"낮은\s*변동성", r"\blow[\s_-]*vol(?:atility)?\b")),
        )
        regimes: List[str] = []
        labels: List[str] = []
        evidence: List[str] = []
        excluded_regimes: List[str] = []
        excluded_labels: List[str] = []
        exclusion_pattern = re.compile(
            r"(진입하지|사용하지|거래하지|제외|회피|금지|차단|피한다|"
            r"\bno[\s_-]*trade\b|\bavoid\b|\bexclude\b|\bdo\s+not\b|\bdon't\b)",
            flags=re.I,
        )
        matches = []
        for regime, label, patterns in definitions:
            match = next(
                (found for pattern in patterns if (found := re.search(pattern, combined, flags=re.I))),
                None,
            )
            if match:
                matches.append((match.start(), match.end(), regime, label))
        matches.sort(key=lambda item: item[0])
        excluded_match_indexes = set()
        for exclusion in exclusion_pattern.finditer(combined):
            sentence_start = max(
                combined.rfind(delimiter, 0, exclusion.start())
                for delimiter in (".", "\n", "!", "?", ";", "。")
            ) + 1
            sentence_end_candidates = [
                position
                for delimiter in (".", "\n", "!", "?", ";", "。")
                if (position := combined.find(delimiter, exclusion.end())) >= 0
            ]
            sentence_end = min(sentence_end_candidates) if sentence_end_candidates else len(combined)
            candidates = [
                (index, item)
                for index, item in enumerate(matches)
                if sentence_start <= item[0] < sentence_end
            ]
            if not candidates:
                candidates = [
                    (index, item)
                    for index, item in enumerate(matches)
                    if min(abs(exclusion.start() - item[1]), abs(item[0] - exclusion.end())) <= 60
                ]
            if candidates:
                closest_index, _ = min(
                    candidates,
                    key=lambda indexed: min(
                        abs(exclusion.start() - indexed[1][1]),
                        abs(indexed[1][0] - exclusion.end()),
                    ),
                )
                excluded_match_indexes.add(closest_index)
        for index, (start, end, regime, label) in enumerate(matches):
            if index in excluded_match_indexes:
                excluded_regimes.append(regime)
                excluded_labels.append(label)
                continue
            regimes.append(regime)
            labels.append(label)
            evidence.append(label)
        if not regimes and explicit_all_market:
            return {
                "regimes": ["all"],
                "labels": ["모든 시장상황"],
                "confidence": "explicit_text_match",
                "evidence": "소스의 포함 표현: 모든 시장상황 (실행 시 NoahAI 국면 적합성 재검사)",
                "auto_select": True,
                "excluded_regimes": excluded_regimes,
                "excluded_labels": excluded_labels,
            }
        if not regimes:
            return {
                "regimes": ["all"],
                "labels": ["모든 시장상황"],
                "confidence": "needs_user_confirmation",
                "evidence": (
                    "포함할 시장상황이 명시되지 않았습니다."
                    + (f" 제외 표현 감지: {', '.join(excluded_labels)}." if excluded_labels else "")
                ),
                "auto_select": False,
                "excluded_regimes": excluded_regimes,
                "excluded_labels": excluded_labels,
            }
        return {
            "regimes": regimes,
            "labels": labels,
            "confidence": "explicit_text_match",
            "evidence": (
                "소스의 포함 표현: " + ", ".join(evidence)
                + (f" / 제외 표현: {', '.join(excluded_labels)}" if excluded_labels else "")
            ),
            "auto_select": True,
            "excluded_regimes": excluded_regimes,
            "excluded_labels": excluded_labels,
        }

    def analyze(
        self,
        value: str,
        kind: str = "auto",
        *,
        supplemental_text: str = "",
        authoring_mode: str = "source_faithful",
        extracted_source: Optional[ExtractedStrategySource] = None,
    ) -> Dict[str, Any]:
        from .custom_strategy_advisor import (
            build_clarification_questions,
            build_strategy_guidance,
            build_validation_issue_details,
        )

        source = deepcopy(extracted_source) if extracted_source is not None else self.extract(value, kind)
        original_source = deepcopy(source)
        normalized_authoring_mode = str(authoring_mode or "source_faithful").strip().lower()
        if normalized_authoring_mode not in {
            "source_faithful", "guided_clarification", "noah_delegate",
        }:
            normalized_authoring_mode = "source_faithful"
        confirmed_supplement = str(supplemental_text or "").strip()
        if len(confirmed_supplement) > 20_000:
            raise ValueError("사용자 확인 보완 답변은 20,000자 이하여야 합니다.")
        if confirmed_supplement:
            original_text = str(source.text or "")
            source.evidence = dict(source.evidence or {})
            source.evidence.update({
                "original_content_sha256": hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
                "user_confirmation_present": True,
                "user_confirmation_sha256": hashlib.sha256(
                    confirmed_supplement.encode("utf-8")
                ).hexdigest(),
                "authoring_mode": normalized_authoring_mode,
            })
            source.text = (
                f"{original_text.rstrip()}\n\n"
                "[사용자가 직접 확인한 보완 답변]\n"
                f"{confirmed_supplement}"
            ).strip()
            source.warnings.append(
                "원본 파일은 변경하지 않고 사용자가 확인한 보완 답변을 별도 근거로 함께 분석했습니다."
            )
        else:
            source.evidence = dict(source.evidence or {})
            source.evidence["authoring_mode"] = normalized_authoring_mode
        evidence_available = (
            bool((source.evidence or {}).get("strategy_evidence_available"))
            or bool(confirmed_supplement)
            if source.kind == "youtube" else bool((source.text or "").strip())
        )
        if len(source.text or "") > self.AI_CONTENT_CHAR_LIMIT:
            limit_warning = (
                f"원문 {len(source.text):,}자 중 앞 {self.AI_CONTENT_CHAR_LIMIT:,}자를 AI 구조화에 사용했습니다."
            )
            if limit_warning not in source.warnings:
                source.warnings.append(limit_warning)
        heuristic = self._heuristic_rules(source)
        if confirmed_supplement:
            supplement_rules = self._heuristic_rules(ExtractedStrategySource(
                kind="text",
                reference="user-confirmation",
                title="사용자 확인 보완 답변",
                text=confirmed_supplement,
                warnings=[],
                evidence={"user_confirmation_present": True},
            ))
            original_rules = self._heuristic_rules(original_source)
            for path in self._user_supplement_conflicts(original_rules, supplement_rules):
                issue = f"user_confirmation_conflicts_with_original:{path}"
                if issue not in heuristic["compiler_issues"]:
                    heuristic["compiler_issues"].append(issue)
        result: Optional[Dict[str, Any]] = None
        ai_budget_fallback = False
        if self.ai_client and self.ai_client.is_ready() and source.text.strip() and evidence_available:
            system_prompt = (
                "You explain and propose a structured reading of user-owned trading material. Return JSON only. "
                "Never invent missing conditions. Required keys: name, summary, rules, engine_settings, "
                "missing_conditions, clarification_questions, risks, scenarios. rules must contain entry, exit, stop_loss, "
                "take_profit, position_size, market_conditions. engine_settings may only contain "
                "_unit='percent_points', leverage(1-5), tp_percent, sl_percent, "
                "position_size(0.01-0.5), signal_threshold(0-1). tp_percent and sl_percent are "
                "percentage points: source TP 0.3% must be JSON 0.3, never 0.003. "
                "Also return rules.executable_entry and, only when explicitly present, rules.executable_exit "
                "with all/any arrays. Each condition may use fields signal, confidence, open, high, low, close, "
                "current_price, rsi, macd, macd_signal, macd_histogram, bb_position, bb_width, "
                "ma20, ma50, ma200, sma20, sma50, sma200, ema20, ema50, ema200, adx, atr, atr_percent, "
                "trend_strength, market_volatility, volume, volume_sma20, volume_ratio, hour, weekday "
                "and operators eq, ne, gt, gte, lt, lte, gt_field, lt_field, "
                "crosses_above, crosses_below. Cross operators must use value_field and only when "
                "the source explicitly defines crossover/crossunder. "
                "Also return rules.entry_signal as LONG, SHORT, or empty when direction is not explicit. "
                "If the source explicitly defines separate LONG and SHORT conditions, return "
                "rules.independent_entries={LONG:{all/any/expression},SHORT:{all/any/expression}} instead "
                "of mixing both directions into one executable_entry. "
                "rules.signal_mode as confirm unless the material explicitly defines a standalone entry signal. "
                "When explicitly present, rules.risk_model may contain risk_per_trade_percent, "
                "max_margin_usage_percent, max_leverage, max_notional_percent, stop_mode, and volatility_multiplier. "
                "rules.regime_transition must be delegate_to_noah or pause and must reflect the user's material; "
                "use delegate_to_noah when it is not specified. clarification_questions may only ask concise "
                "questions for missing conditions and explain why they matter; never answer those questions, "
                "invent defaults, or mark an AI proposal as user-confirmed. "
                "Do not include withdrawal or transfer instructions. Explain AND/OR logic and evidence. "
                "Your execution proposal is advisory: NoahAI's deterministic source compiler is the only authority."
            )
            payload = {
                "source_kind": source.kind,
                "title": source.title,
                "reference": source.reference,
                "warnings": source.warnings,
                "heuristic": heuristic,
                "content": source.text[:self.AI_CONTENT_CHAR_LIMIT],
            }
            try:
                result = self.ai_client.chat_json(
                    system_prompt,
                    json.dumps(payload, ensure_ascii=False),
                    max_tokens=2400,
                )
            except RuntimeError as exc:
                # The deterministic compiler is the execution authority.  An
                # exhausted *interactive* AI budget must therefore remove only
                # the optional explanation layer, never block text/Pine source
                # analysis or the five-minute guided authoring flow.
                if str(exc).strip() != "interactive_ai_budget_exceeded":
                    raise
                ai_budget_fallback = True
                source.warnings.append(
                    "오늘의 외부 AI 심층분석 사용 한도에 도달해 앱 내부 규칙 분석으로 계속했습니다. "
                    "실행 가능 여부와 누락 조건은 동일한 결정형 컴파일러가 판정합니다."
                )

        result = dict(result or {})
        proposed_rules = dict(result.get("rules") or {})
        if isinstance(result.get("engine_settings"), dict):
            proposed_rules["engine_settings"] = dict(result["engine_settings"])
        # Order-affecting values always come from the deterministic compiler.
        # External AI may explain the source, but it cannot silently add a rule,
        # direction, TP/SL, leverage, or position size that the source parser did
        # not prove.
        rules = deepcopy(heuristic)
        engine = dict(rules.get("engine_settings") or {})
        if "leverage" in engine:
            engine["leverage"] = int(float(engine["leverage"]))
        if "position_size" in engine:
            engine["position_size"] = float(engine["position_size"])
        for key in ("tp_percent", "sl_percent"):
            if key in engine:
                engine[key] = float(engine[key])
        if "signal_threshold" in engine:
            engine["signal_threshold"] = float(engine["signal_threshold"])
        engine["_unit"] = "percent_points"
        rules["signal_mode"] = str(rules.get("signal_mode") or "confirm").lower()
        rules["entry_signal"] = str(rules.get("entry_signal") or "").upper()
        rules["regime_transition"] = str(
            rules.get("regime_transition") or "delegate_to_noah"
        ).lower()
        if rules["regime_transition"] not in {"delegate_to_noah", "pause"}:
            rules["regime_transition"] = "delegate_to_noah"
        rules["engine_settings"] = engine
        has_declared_exit_rates = any(engine.get(key) is not None for key in ("tp_percent", "sl_percent"))
        rules["exit_policy"] = {
            "mode": (
                "strategy_owned"
                if rules["signal_mode"] == "independent" or has_declared_exit_rates
                else "inherit_noah_base"
            )
        }
        rules["source_evidence"] = asdict(source)
        rules["source_rule_trace"] = self._build_source_rule_trace(source, rules)
        rejected_ai_paths = self._ai_execution_diff(proposed_rules, rules) if proposed_rules else []
        rules["source_grounding"] = {
            "status": "compiler_authoritative",
            "compiler_contract_sha256": self._execution_contract_digest(rules),
            "ai_execution_rules_accepted": bool(proposed_rules and not rejected_ai_paths),
            "rejected_ai_paths": rejected_ai_paths,
            "authoring_mode": normalized_authoring_mode,
            "user_confirmation_present": bool(confirmed_supplement),
            "user_confirmation_sha256": (
                hashlib.sha256(confirmed_supplement.encode("utf-8")).hexdigest()
                if confirmed_supplement else ""
            ),
        }
        if rejected_ai_paths:
            source.warnings.append(
                "외부 AI가 제안했지만 원문 컴파일러가 증명하지 못해 실행 규칙에서 제외한 항목: "
                + ", ".join(rejected_ai_paths)
            )
        missing = [key for key in self.REQUIRED_RULES if not rules.get(key)]
        if source.kind == 'bundle' and source.evidence.get('coverage_complete') is not True:
            missing.append('source_coverage_incomplete')
            rules.setdefault('compiler_issues', []).append('source_coverage_incomplete')
        for issue in list(rules.get("compiler_issues") or []):
            if issue not in missing:
                missing.append(issue)
        # AI의 누락 제안은 설명용이다. 모델 응답이 실행 가능 여부를 임의로
        # 바꾸지 않도록 실제 차단 사유는 컴파일러와 공통 계약에서만 만든다.
        from .declarative_strategy_engine import DeclarativeStrategyEngine
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(rules)
        unsupported_conditions = list(executable_validation.get("errors", []) or [])
        if unsupported_conditions:
            missing.append("unsupported_executable_conditions")
            source.warnings.append(
                "실행 엔진이 지원하지 않는 조건이 있어 승인할 수 없습니다: "
                + ", ".join(unsupported_conditions)
            )
        from .custom_strategy_runtime import ExitRateContractError, validate_stored_exit_rates
        try:
            validate_stored_exit_rates(engine)
        except ExitRateContractError as exc:
            if "exit_rate_contract_missing_or_invalid" not in missing:
                missing.append("exit_rate_contract_missing_or_invalid")
            source.warnings.append(str(exc))
        if not evidence_available:
            missing.extend(key for key in self.REQUIRED_RULES if key not in missing)
        guidance = build_strategy_guidance(rules, self.REQUIRED_RULES)
        for item in missing:
            if item not in guidance["missing_conditions"]:
                guidance["missing_conditions"].append(item)
        guidance["complete"] = not guidance["missing_conditions"]
        source_payload = asdict(source)
        source_payload["coverage_summary"] = self._coverage_summary(source)
        regime_suggestion = self.infer_market_regimes(
            source.text,
            rules.get("market_conditions", ""),
        )
        from .noah_strategy_ir import NoahStrategyIR

        strategy_ir = NoahStrategyIR.compile(
            rules,
            source_kind=source.kind,
            source_reference=source.reference,
            missing_conditions=missing,
        )
        # 문서/IR 완성과 실제 실행 가능성은 별도 게이트다. 여기서 미리
        # 표시해 사용자가 승인 또는 PAPER 시작 후에야 실패를 알지 않게 한다.
        from .custom_strategy_pipeline import CustomStrategyPipeline
        execution_readiness = CustomStrategyPipeline.paper_execution_readiness({
            "rules": rules,
            "missing_conditions": missing,
        })
        blocking_details = build_validation_issue_details(
            [*missing, *list(execution_readiness.get("reasons") or [])],
            unsupported_conditions,
        )
        clarification_questions = build_clarification_questions(blocking_details)
        return {
            "name": str(result.get("name") or source.title or "사용자 전략"),
            "summary": str(result.get("summary") or "소스에서 확인 가능한 조건만 추출했습니다."),
            "source": source_payload,
            "source_manifest": source.evidence.get('sources', []) if source.kind == 'bundle' else [],
            "rules": rules,
            "engine_settings": engine,
            "missing_conditions": missing,
            "guidance": guidance,
            "unsupported_conditions": unsupported_conditions,
            "risks": list(result.get("risks") or ["체결 비용과 유동성에 따라 결과가 달라질 수 있습니다."]),
            "scenarios": list(result.get("scenarios") or []),
            "ai_advisory_missing_conditions": list(result.get("missing_conditions") or []),
            "ai_execution_suggestion_rejected": bool(rejected_ai_paths),
            "market_regime_suggestion": regime_suggestion,
            "ai_analyzed": bool(result),
            "ai_budget_fallback": ai_budget_fallback,
            "ready_for_review": bool(evidence_available and not missing),
            "ready_for_execution": bool(
                evidence_available and not missing and execution_readiness.get("ready")
            ),
            "execution_readiness": execution_readiness,
            "blocking_details": blocking_details,
            "clarification_questions": clarification_questions,
            "authoring_contract": {
                "mode": normalized_authoring_mode,
                "source_faithful": True,
                "user_confirmation_present": bool(confirmed_supplement),
                "ai_proposals_are_executable": False,
                "auto_saved": False,
                "auto_approved": False,
                "auto_paper_started": False,
                "auto_live_started": False,
            },
            "strategy_ir": strategy_ir,
            "ir_level_1": NoahStrategyIR.project(strategy_ir, 1),
            "ir_level_2": NoahStrategyIR.project(strategy_ir, 2),
        }
