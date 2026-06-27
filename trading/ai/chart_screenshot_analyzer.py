#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chart Screenshot Analyzer

역할
- 차트 스크린샷에서 텍스트(OCR) 추출
- 심볼/타임프레임/지표값 등 간단 파싱
- OpenAI LLM을 호출해 매매 스탠스/시나리오/진입·청산·목표를 JSON으로 생성

주의
- PaddleOCR, OpenCV 미설치 환경에서도 안전하게 동작(친절한 에러 메시지 반환)
- 서버 없이 로컬에서만 동작하며, 기존 OpenAI 세션을 재사용
"""

from __future__ import annotations

from typing import Optional, Dict, Any, Tuple
import os
import re
import json

# 선택적 의존성 (미설치여도 동작)
try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - 선택 의존성
    cv2 = None  # type: ignore

try:
    from paddleocr import PaddleOCR  # type: ignore
except Exception:  # pragma: no cover - 선택 의존성
    PaddleOCR = None  # type: ignore

# RapidOCR(onnxruntime) - 크로스플랫폼 번들링에 유리
try:
    from rapidocr_onnxruntime import RapidOCR  # type: ignore
except Exception:
    RapidOCR = None  # type: ignore

from .openai_client import OpenAIClient


class ChartScreenshotAnalyzer:
    def __init__(self, openai_client: Optional[OpenAIClient] = None,
                 api_key: Optional[str] = None,
                 model: Optional[str] = None,
                 disable_ocr: Optional[bool] = None) -> None:
        # OpenAI 클라이언트: 주입 우선, 없으면 자체 생성
        self.client: Optional[OpenAIClient] = openai_client or (
            OpenAIClient(api_key=api_key or os.getenv("OPENAI_API_KEY", ""), model=(model or "gpt-4o-mini"))
            if (api_key or os.getenv("OPENAI_API_KEY")) else None
        )

        self._ocr: Optional[Any] = None
        self._rapid_ocr: Optional[Any] = None
        # 환경변수 또는 인자 기반 OCR 비활성화 플래그
        env_disable = str(os.getenv('NOAHAI_DISABLE_PADDLEOCR', '0')).strip() in ('1', 'true', 'yes')
        self.disable_ocr = bool(disable_ocr) if disable_ocr is not None else env_disable

    # --- Public API ---
    def analyze(self, image_path: str) -> Dict[str, Any]:
        """이미지 경로를 받아 OCR→특징 파싱→LLM 분석을 수행.

        반환: JSON 호환 딕셔너리(오류 시 error 필드 포함)
        """
        if not os.path.exists(image_path):
            return {"error": f"이미지 경로를 찾을 수 없습니다: {image_path}"}

        # OCR 추출(필요 시 비활성화)
        text, ocr_info = ("", {"warning": "OCR 비활성화됨 (LLM-only)"}) if self.disable_ocr else self._extract_text(image_path)
        if not text and ocr_info.get("warning"):
            # OCR 불가 경고를 곧바로 전달
            return {
                "warning": ocr_info.get("warning"),
                "raw_text": "",
                "features": {},
            }

        # 특징 파싱
        features = self._parse_features(text)

        # LLM 분석
        llm_result = self._ask_llm(features)

        result: Dict[str, Any] = {
            "raw_text": text,
            "features": features,
            "analysis": llm_result if llm_result else None,
        }
        if llm_result is None:
            result["warning"] = "LLM 분석에 실패했습니다. API 키/모델 설정을 확인하세요."
        return result

    # --- Internals ---
    def _get_ocr(self):
        if self._ocr is not None:
            return self._ocr
        if PaddleOCR is None:
            return None
        # Lazy init (첫 사용 시 생성)
        try:
            # 다중 언어 지원: 한글 + 영문
            self._ocr = PaddleOCR(use_angle_cls=True, lang='korean')
        except Exception:
            self._ocr = None
        return self._ocr

    def _extract_text(self, image_path: str) -> Tuple[str, Dict[str, Any]]:
        """OCR 엔진 자동 선택: 영문 우선 → 한글 폴백"""
        info: Dict[str, Any] = {}
        
        # 1) 영문 UI용: RapidOCR (바이낸스, 바이비트 등)
        if self._get_rapid_ocr() is not None:
            try:
                text = self._extract_text_with_rapidocr(image_path)
                if text:
                    # 한글이 많이 포함되어 있으면 PaddleOCR로 재시도
                    korean_ratio = sum(1 for c in text if ord('가') <= ord(c) <= ord('힣')) / max(len(text), 1)
                    if korean_ratio < 0.3:  # 한글 비율이 30% 미만이면 RapidOCR 결과 사용
                        return text, info
                    info["debug"] = {"rapidocr_korean_detected": True, "korean_ratio": korean_ratio}
            except Exception as e:
                info.setdefault("debug", {})["rapidocr_error"] = str(e)

        # 2) 한글 UI용: PaddleOCR (업비트, 빗썸 등)
        ocr = self._get_ocr()
        if ocr is None:
            info["warning"] = (
                "OCR 엔진이 포함되지 않아 LLM만으로 분석합니다. (관리자용: RapidOCR 또는 PaddleOCR를 빌드에 포함하면 자동 활성화)"
            )
            return "", info

        try:
            result = ocr.ocr(image_path, cls=True)
            # result: List[List[ [ [x1,y1]..[x4,y4], (text, conf) ] ]]
            texts = []
            for block in result or []:
                for line in block or []:
                    try:
                        texts.append(line[1][0])
                    except Exception:
                        pass
            return " ".join(texts).strip(), info
        except Exception as e:
            info["warning"] = f"OCR 수행 중 오류: {e}"
            return "", info

    def _get_rapid_ocr(self):
        if self._rapid_ocr is not None:
            return self._rapid_ocr
        if RapidOCR is None:
            return None
        try:
            self._rapid_ocr = RapidOCR()
        except Exception:
            self._rapid_ocr = None
        return self._rapid_ocr

    def _extract_text_with_rapidocr(self, image_path: str) -> str:
        ocr = self._get_rapid_ocr()
        if ocr is None:
            return ""
        try:
            result, _ = ocr(image_path)
            # RapidOCR 결과: [(text, score, box), ...] 또는 [(box, text, score)] 버전이 존재
            texts = []
            for item in result or []:
                if not item:
                    continue
                # 다양한 튜플 구조 방어
                if isinstance(item, (list, tuple)):
                    # text가 0 또는 1번째에 올 수 있음
                    cand = None
                    for idx in range(min(2, len(item))):
                        if isinstance(item[idx], str):
                            cand = item[idx]
                            break
                    if cand:
                        texts.append(cand)
                elif isinstance(item, dict):
                    t = item.get('text') or item.get('label')
                    if t:
                        texts.append(str(t))
            return " ".join(texts).strip()
        except Exception:
            return ""

    def _parse_features(self, text: str) -> Dict[str, Any]:
        """심볼/타임프레임/MA/가격 힌트(로버스트) 추출."""
        raw = text or ""
        t = raw.upper()

        # 심볼: BTCUSDT, BTC/USDT, ETH-PERP, KRW-BTC 등 매칭
        sym = None
        for pattern in [
            r"(KRW-[A-Z0-9]{2,15})",          # KRW-BTC (Upbit)
            r"([A-Z]{3,10}/[A-Z]{3,6})",     # BTC/USDT
            r"([A-Z]{3,10}-PERP)",           # BTC-PERP
            r"([A-Z]{3,10}USDT)",            # BTCUSDT
        ]:
            m = re.search(pattern, t)
            if m:
                sym = m.group(1)
                break

        # 심볼 보조 추론: Binance UI의 Vol(BTC), Vol(USDT) 패턴 활용
        if sym is None:
            try:
                base_m = re.search(r"VOL\(([A-Z]{2,10})\)", t)
                quote_usdt = bool(re.search(r"VOL\(USDT\)", t)) or ("USDT" in t)
                if base_m and quote_usdt:
                    base = base_m.group(1)
                    sym = f"{base}USDT"
                # KRW 힌트가 강하면 KRW-BASE로 추정
                if sym is None and (" KRW" in t or "KRW-" in t or "원" in raw):
                    if base_m:
                        base = base_m.group(1)
                        sym = f"KRW-{base}"
            except Exception:
                pass

        # 타임프레임: 여러 후보가 있으면 우선순위로 선택(1D > 12H > 4H > 2H > 1H > 30M > 15M > 5M > 3M > 1M > 3D > 1W)
        tf = None
        tf_candidates = re.findall(r"\b(1W|3D|1D|12H|4H|2H|1H|30M|15M|5M|3M|1M)\b", t)
        if tf_candidates:
            priority = ["1D","12H","4H","2H","1H","30M","15M","5M","3M","1M","3D","1W"]
            for p in priority:
                if p in tf_candidates:
                    tf = p
                    break

        # 이동평균: MA(7):117,881.9 / MA20: 1234.5 / EMA50=... / SMA200 ...
        mas: Dict[str, float] = {}
        for name in ["MA", "EMA", "SMA"]:
            # 패턴 1: MA(7):117,881.9 (바이낸스, 괄호+쉼표)
            for m in re.finditer(rf"\b{name}\s*\((\d{{1,3}})\)\s*:\s*([0-9,]+(?:\.[0-9]+)?)", t):
                try:
                    value_str = m.group(2).replace(',', '')
                    mas[f"{name}{m.group(1)}"] = float(value_str)
                except Exception:
                    pass
            # 패턴 2: MA7:117881.9 / MA 7 : 117881.9 (일반)
            for m in re.finditer(rf"\b{name}\s*(\d{{1,3}})\s*[:=]\s*([0-9,]+(?:\.[0-9]+)?)", t):
                try:
                    value_str = m.group(2).replace(',', '')
                    mas[f"{name}{m.group(1)}"] = float(value_str)
                except Exception:
                    pass

        # 가격 후보: 쉼표 천단위/소수 포함 숫자 추출 → float 변환
        # 예: 1,234.56 / 894 / 884 (단, K/M/B/% 등 단위가 뒤따르면 제외)
        nums = []
        for s in re.findall(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b(?!\s*(?:K|M|B|%))", raw, flags=re.IGNORECASE):
            try:
                nums.append(float(s.replace(',', '')))
            except Exception:
                pass

        # 로버스트 필터링: 중앙값 ± k*MAD 범위만 유지해 날짜/외부값 배제
        def _robust_filter(values):
            if not values:
                return []
            try:
                import statistics as st
                med = st.median(values)
                devs = [abs(v - med) for v in values]
                mad = st.median(devs) if devs else 0.0
                if mad <= 0:
                    # 중앙값 주변 2.0배 범위
                    lo, hi = med * 0.5, med * 2.0
                    return [v for v in values if lo <= v <= hi]
                k = 6.0  # 느슨한 아웃라이어 컷
                lo, hi = med - k * mad, med + k * mad
                return [v for v in values if lo <= v <= hi]
            except Exception:
                return values

        # 스케일 감지: 심볼 기반으로 지나치게 작은 값 제거(USDT/KRW 구분)
        is_krw = bool(sym and (str(sym).startswith('KRW-') or str(sym).endswith('KRW')))
        is_usdt = bool(sym and (str(sym).endswith('USDT') or str(sym).endswith('/USDT')))
        high_thr = 0.0
        if is_krw:
            high_thr = 10000.0
        elif is_usdt:
            high_thr = 1000.0
        # 큰 값이 존재하면 해당 스케일만 유지, 없고 심볼 미검출이면 동적 컷 적용
        if high_thr > 0 and any(v >= high_thr for v in nums):
            nums = [v for v in nums if v >= high_thr]
        else:
            # 동적 스케일 컷: 최댓값 기반 하위 노이즈 제거
            if nums:
                max_v = max(nums)
                if max_v >= 5000:  # 고가 자산 추정
                    thr = max(1000.0, max_v / 20.0)  # 상단의 5% 미만 제거
                    nums = [v for v in nums if v >= thr]
                # 0.0 제거(명백한 노이즈)
                nums = [v for v in nums if v != 0.0]

        filtered = sorted(_robust_filter(nums))
        top_prices = filtered[-3:] if filtered else []
        price_range = (filtered[0], filtered[-1]) if len(filtered) >= 2 else ((filtered[0], filtered[0]) if filtered else (None, None))
        try:
            import statistics as _st
            price_median = _st.median(filtered) if filtered else None
        except Exception:
            price_median = filtered[len(filtered)//2] if filtered else None

        # 기본 지평 산출(단기 Now-Action 가이드)
        def _map_tf_to_horizon(tf_val: Optional[str]) -> str:
            tf_val = (tf_val or '').upper()
            if tf_val in ('1M','3M','5M','15M'):
                return 'scalp'
            if tf_val in ('30M','1H'):
                return 'intraday'
            if tf_val in ('2H','4H'):
                return 'short_swing'
            if tf_val in ('12H','1D'):
                return 'swing'
            if tf_val in ('3D','1W'):
                return 'position'
            return 'intraday'

        default_horizon = _map_tf_to_horizon(tf)

        return {
            "symbol": sym,
            "timeframe": tf,
            "moving_averages": mas,
            "top_prices_hint": top_prices,
            "price_range": price_range,
            "price_median": price_median,
            "default_horizon": default_horizon,
            "analysis_bias": "now-action",
        }

    def _ask_llm(self, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.client or not self.client.is_ready():
            return None
        system = (
            "You are NoahAI's chart assistant. Analyze chart context extracted via OCR and return structured trading guidance as JSON."
            " All human-facing strings (titles, narratives, notes) MUST be in Korean. Keep outputs concise and practical."
        )
        user = (
            "다음 차트 특징(심볼/타임프레임/이동평균/가격 힌트)을 바탕으로, '지금 시점 기준' 단기 트레이딩 결정을 우선 제시하세요.\n"
            "timeframe→horizon 매핑은 features.default_horizon을 따르세요.\n"
            f"Features:\n{json.dumps(features, ensure_ascii=False, indent=2)}\n\n"
            "반드시 아래 JSON 스키마만 출력하세요(기타 텍스트 금지): {\n"
            "  \"action\": \"ENTER_LONG\"|\"ENTER_SHORT\"|\"WAIT\",\n"
            "  \"horizon\": \"scalp\"|\"intraday\"|\"short_swing\"|\"swing\"|\"position\",\n"
            "  \"stance\": \"LONG\"|\"SHORT\"|\"NEUTRAL\",\n"
            "  \"confidence\": 0..1,\n"
            "  \"confidence_basis\": string(KO),\n"
            "  \"scenarios\": [ { \"title\": string(KO), \"prob\": 0..1, \"narrative\": string(KO) } ],\n"
            "  \"plan\": { \n"
            "      \"entry\": number, \n"
            "      \"entry_zone\": [number, number], \n"
            "      \"stop\": number, \n"
            "      \"tp\": [number, number], \n"
            "      \"notes\": string(KO) \n"
            "  }\n"
            "}\n\n"
            "중요 규칙:\n"
            "- '현재 시점' 기준으로 바로 실행 가능한 플랜을 제시(가능/불가를 action으로 표시).\n"
            "- horizon은 features.default_horizon을 사용.\n"
            "\n"
            "📌 필수: entry/entry_zone/stop/tp는 **반드시 구체적인 수치**를 제공해야 합니다.\n"
            "   - action이 WAIT인 경우에도 '참고용 진입가/손절가/목표가'를 제시하세요.\n"
            "   - price_median을 중심으로 합리적인 수치를 계산하세요.\n"
            "   - 계산 방법:\n"
            "     * entry: price_median (현재가 추정)\n"
            "     * entry_zone: [price_median * 0.98, price_median * 1.02] (±2% 범위)\n"
            "     * stop(LONG): price_median * 0.95 (5% 손절) / stop(SHORT): price_median * 1.05\n"
            "     * tp[0](LONG): price_median * 1.03 (3% 목표1) / tp[0](SHORT): price_median * 0.97\n"
            "     * tp[1](LONG): price_median * 1.06 (6% 목표2) / tp[1](SHORT): price_median * 0.94\n"
            "   - 비율은 변동성/타임프레임에 따라 조정 가능하나 반드시 수치를 제공하세요.\n"
            "\n"
            "- price_range/price_median/top_prices_hint를 준수하고, 날짜/시간/연도(예: 2024, 2025 등)에서 유래한 숫자는 가격으로 사용하지 마세요.\n"
            "- entry/stop은 price_range 내에 위치하도록 하세요.\n"
            "- tp 값은 entry를 기준으로 ±30% 범위를 권장하며, price_range를 벗어나지 않도록 하세요(엄격 준수).\n"
            "- 모든 수치의 자릿수(자리수 규모)는 price_median과 동일한 차원을 유지하세요(예: 123,000대면 117/125가 아닌 117,000/125,000).\n"
            "- KRW 기반 심볼(업비트 등)은 자릿수가 크므로(예: 171,000,000) 천원/만원 단위로 반올림하세요.\n"
            "- USDT 기반 심볼(바이낸스 등)은 소수점 단위(예: 111,147.8)를 유지하세요.\n"
            "- confidence_basis에는 근거(패턴/MA/수렴·확장/변동성·추세 등)를 간결히 기술.\n"
            "- 설명(제목/서술/notes)은 한국어로 간결하게.\n"
            "\n"
            "⚠️ 주의: entry, entry_zone, stop, tp가 null이거나 빈 배열이면 안 됩니다. 반드시 수치를 제공하세요."
        )
        try:
            resp = self.client.chat_json(system, user, temperature=0.2, max_tokens=700)
            return resp
        except Exception:
            return None
