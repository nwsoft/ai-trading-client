#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""사용자 제공 전략 소스를 실행 가능한 커스텀 전략 초안으로 변환한다.

지원 입력: 일반 텍스트, Pine Script, PDF, 이미지/OCR, 로컬 영상,
YouTube 링크(자막 우선), TradingView 공개 스크립트 링크. 추출 결과는 곧바로
주문하지 않고 CustomStrategyPipeline의 승인/검증 절차로 전달된다.
"""

from __future__ import annotations

import html
import json
import logging
import re
import tempfile
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
        resolved = self.detect_kind(value, kind)
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
        sl = self._number(r"(?:stop[_\s-]*loss|손절|sl)[^\d]{0,12}(\d+(?:\.\d+)?)\s*%?", text)
        tp = self._number(r"(?:take[_\s-]*profit|익절|tp)[^\d]{0,12}(\d+(?:\.\d+)?)\s*%?", text)
        position = self._number(r"(?:position[_\s-]*size|포지션\s*크기|자산)[^\d]{0,14}(\d+(?:\.\d+)?)\s*%", text)
        leverage = self._number(r"(?:leverage|레버리지)[^\d]{0,10}(\d+(?:\.\d+)?)", text)
        indicators = sorted(set(re.findall(r"\b(RSI|MACD|EMA|SMA|ATR|ADX|VWAP|BOLLINGER|SUPERTREND)\b", text, flags=re.I)))
        rules: Dict[str, Any] = {
            "entry": " | ".join(item.strip() for item in entry_lines[:6]),
            "exit": " | ".join(item.strip() for item in exit_lines[:6]),
            "stop_loss": f"{sl}%" if sl is not None else "",
            "take_profit": f"{tp}%" if tp is not None else "",
            "position_size": f"{position}%" if position is not None else "",
            "market_conditions": f"사용 지표: {', '.join(indicators)}" if indicators else "",
            "engine_settings": {},
            "executable_entry": {"all": [], "any": []},
            "executable_exit": {"all": [], "any": []},
            "signal_mode": "confirm",
            "entry_signal": "",
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

        for sentence in re.split(r"[\n;.!?]+", text):
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
        if "strategy.long" in lower:
            rules["entry_signal"] = "LONG"
            executable["all"].append({"field": "signal", "operator": "eq", "value": "LONG"})
        elif "strategy.short" in lower:
            rules["entry_signal"] = "SHORT"
            executable["all"].append({"field": "signal", "operator": "eq", "value": "SHORT"})
        elif any("long" in item.lower() or "롱" in item for item in entry_lines):
            rules["entry_signal"] = "LONG"
        elif any("short" in item.lower() or "숏" in item for item in entry_lines):
            rules["entry_signal"] = "SHORT"
        if sl is not None:
            engine["sl_percent"] = max(0.05, min(sl, 20.0))
        if tp is not None:
            engine["tp_percent"] = max(0.05, min(tp, 50.0))
        if position is not None:
            engine["position_size"] = max(0.01, min(position / 100.0, 0.5))
        if leverage is not None:
            engine["leverage"] = int(max(1, min(leverage, 10)))
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
            "position_size": ("포지션", "position", "수량", "자산"),
            "market_conditions": ("상승", "하락", "횡보", "변동", "trend", "range", "volatility"),
        }
        fallback = text[:500]
        trace: Dict[str, Any] = {}
        for field, keywords in keyword_map.items():
            value = rules.get(field)
            matches = [
                line[:500] for line in lines
                if any(keyword in line.lower() for keyword in keywords)
            ][:3]
            trace[field] = {
                "status": "matched" if value and (matches or fallback) else "missing",
                "rule_value": value,
                "evidence": matches or ([fallback] if value and fallback else []),
                "source_kind": source.kind,
                "source_reference": source.reference,
            }
        return trace

    @staticmethod
    def infer_market_regimes(text: str, market_conditions: Any = "") -> Dict[str, Any]:
        """소스에 명시된 시장국면만 추천한다.

        LONG/SHORT 방향만으로 상승장·하락장을 추정하지 않는다. 여러 국면이
        명시되면 모두 보존하고, 근거가 없으면 사용자 확인이 필요한 all을 반환한다.
        """
        combined = f"{text or ''}\n{market_conditions or ''}".lower()
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

    def analyze(self, value: str, kind: str = "auto") -> Dict[str, Any]:
        from .custom_strategy_advisor import build_strategy_guidance

        source = self.extract(value, kind)
        evidence_available = (
            bool((source.evidence or {}).get("strategy_evidence_available"))
            if source.kind == "youtube" else bool((source.text or "").strip())
        )
        if len(source.text or "") > self.AI_CONTENT_CHAR_LIMIT:
            limit_warning = (
                f"원문 {len(source.text):,}자 중 앞 {self.AI_CONTENT_CHAR_LIMIT:,}자를 AI 구조화에 사용했습니다."
            )
            if limit_warning not in source.warnings:
                source.warnings.append(limit_warning)
        heuristic = self._heuristic_rules(source)
        result: Optional[Dict[str, Any]] = None
        if self.ai_client and self.ai_client.is_ready() and source.text.strip() and evidence_available:
            system_prompt = (
                "You convert user-owned trading material into explicit rules. Return JSON only. "
                "Never invent missing conditions. Required keys: name, summary, rules, engine_settings, "
                "missing_conditions, risks, scenarios. rules must contain entry, exit, stop_loss, "
                "take_profit, position_size, market_conditions. engine_settings may only contain "
                "leverage(1-10), tp_percent, sl_percent, position_size(0.01-0.5), signal_threshold(0-1). "
                "Also return rules.executable_entry and, only when explicitly present, rules.executable_exit "
                "with all/any arrays. Each condition may use fields signal, confidence, open, high, low, close, "
                "current_price, rsi, macd, macd_signal, macd_histogram, bb_position, bb_width, "
                "ma20, ma50, ma200, sma20, sma50, sma200, ema20, ema50, ema200, adx, atr, atr_percent, "
                "trend_strength, market_volatility, volume, volume_sma20, volume_ratio, hour, weekday "
                "and operators eq, ne, gt, gte, lt, lte, gt_field, lt_field, "
                "crosses_above, crosses_below. Cross operators must use value_field and only when "
                "the source explicitly defines crossover/crossunder. "
                "Also return rules.entry_signal as LONG, SHORT, or empty when direction is not explicit, and "
                "rules.signal_mode as confirm unless the material explicitly defines a standalone entry signal. "
                "When explicitly present, rules.risk_model may contain risk_per_trade_percent, "
                "max_margin_usage_percent, max_leverage, max_notional_percent, stop_mode, and volatility_multiplier. "
                "rules.regime_transition must be delegate_to_noah or pause and must reflect the user's material; "
                "use delegate_to_noah when it is not specified. Ask concise clarification questions for every "
                "missing condition and explain why it matters. "
                "Do not include withdrawal or transfer instructions. Explain AND/OR logic and evidence."
            )
            payload = {
                "source_kind": source.kind,
                "title": source.title,
                "reference": source.reference,
                "warnings": source.warnings,
                "heuristic": heuristic,
                "content": source.text[:self.AI_CONTENT_CHAR_LIMIT],
            }
            result = self.ai_client.chat_json(system_prompt, json.dumps(payload, ensure_ascii=False), max_tokens=2400)

        result = dict(result or {})
        rules = dict(result.get("rules") or heuristic)
        engine = dict(result.get("engine_settings") or rules.get("engine_settings") or heuristic.get("engine_settings") or {})
        if "leverage" in engine:
            engine["leverage"] = int(max(1, min(float(engine["leverage"]), 10)))
        if "position_size" in engine:
            engine["position_size"] = max(0.01, min(float(engine["position_size"]), 0.5))
        for key in ("tp_percent", "sl_percent"):
            if key in engine:
                engine[key] = max(0.05, min(float(engine[key]), 50.0 if key == "tp_percent" else 20.0))
        if "signal_threshold" in engine:
            engine["signal_threshold"] = max(0.0, min(float(engine["signal_threshold"]), 1.0))
        engine["_unit"] = "percent_points"
        rules["signal_mode"] = str(result.get("signal_mode") or rules.get("signal_mode") or "confirm").lower()
        rules["entry_signal"] = str(result.get("entry_signal") or rules.get("entry_signal") or "").upper()
        rules["regime_transition"] = str(
            result.get("regime_transition") or rules.get("regime_transition") or "delegate_to_noah"
        ).lower()
        if rules["regime_transition"] not in {"delegate_to_noah", "pause"}:
            rules["regime_transition"] = "delegate_to_noah"
        if isinstance(result.get("risk_model"), dict) and not isinstance(rules.get("risk_model"), dict):
            rules["risk_model"] = dict(result["risk_model"])
        rules["engine_settings"] = engine
        rules["source_evidence"] = asdict(source)
        rules["source_rule_trace"] = self._build_source_rule_trace(source, rules)
        missing = [key for key in self.REQUIRED_RULES if not rules.get(key)]
        missing.extend(item for item in (result.get("missing_conditions") or []) if item not in missing)
        from .declarative_strategy_engine import DeclarativeStrategyEngine
        executable_validation = DeclarativeStrategyEngine.validate_rule_spec(rules)
        unsupported_conditions = list(executable_validation.get("errors", []) or [])
        if unsupported_conditions:
            missing.append("unsupported_executable_conditions")
            source.warnings.append(
                "실행 엔진이 지원하지 않는 조건이 있어 승인할 수 없습니다: "
                + ", ".join(unsupported_conditions)
            )
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
        return {
            "name": str(result.get("name") or source.title or "사용자 전략"),
            "summary": str(result.get("summary") or "소스에서 확인 가능한 조건만 추출했습니다."),
            "source": source_payload,
            "rules": rules,
            "engine_settings": engine,
            "missing_conditions": missing,
            "guidance": guidance,
            "unsupported_conditions": unsupported_conditions,
            "risks": list(result.get("risks") or ["체결 비용과 유동성에 따라 결과가 달라질 수 있습니다."]),
            "scenarios": list(result.get("scenarios") or []),
            "market_regime_suggestion": regime_suggestion,
            "ai_analyzed": bool(result),
            "ready_for_review": bool(evidence_available and not missing),
            "strategy_ir": strategy_ir,
            "ir_level_1": NoahStrategyIR.project(strategy_ir, 1),
            "ir_level_2": NoahStrategyIR.project(strategy_ir, 2),
        }
