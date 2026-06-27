#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Alpha Arena 응답 파서

LLM 응답에서 MODEL_CHAT과 TRADING_DECISIONS를 파싱합니다.
"""

import json
import re
import logging
from typing import Dict, List, Optional, Any, Tuple


class ResponseParser:
    """Alpha Arena 응답 파서"""
    
    # Alpha Arena 고정 심볼
    ARENA_SYMBOLS = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'BNB']
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def parse_response(self, response: str) -> Dict[str, Any]:
        """
        LLM 응답 파싱
        
        Returns:
            {
                'model_chat': str,
                'trading_decisions': Dict[str, Dict],
                'parse_errors': List[str]
            }
        """
        result = {
            'model_chat': '',
            'trading_decisions': {},
            'parse_errors': []
        }
        
        try:
            # MODEL_CHAT 추출
            model_chat = self._extract_model_chat(response)
            result['model_chat'] = model_chat
            
            # TRADING_DECISIONS 추출 및 파싱
            trading_decisions, errors = self._extract_trading_decisions(response)
            result['trading_decisions'] = trading_decisions
            result['parse_errors'] = errors
            
            return result
            
        except Exception as e:
            self.logger.error(f"응답 파싱 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            result['parse_errors'].append(f"파싱 오류: {str(e)}")
            return result
    
    def _extract_model_chat(self, response: str) -> str:
        """MODEL_CHAT 섹션 추출"""
        try:
            # "MODEL_CHAT" 또는 "Model Chat" 또는 "1) MODEL_CHAT" 패턴 찾기
            patterns = [
                r'MODEL_CHAT\s*[:：]?\s*\n(.*?)(?=\n\s*TRADING_DECISIONS|$)',
                r'Model Chat\s*[:：]?\s*\n(.*?)(?=\n\s*TRADING_DECISIONS|$)',
                r'1\)\s*MODEL_CHAT\s*[:：]?\s*\n(.*?)(?=\n\s*2\)|$)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
                if match:
                    chat = match.group(1).strip()
                    if chat:
                        return chat
            
            # 패턴이 없으면 TRADING_DECISIONS 이전의 모든 텍스트를 MODEL_CHAT으로 간주
            decisions_match = re.search(r'TRADING_DECISIONS', response, re.IGNORECASE)
            if decisions_match:
                chat = response[:decisions_match.start()].strip()
                # 헤더 제거 (프롬프트 지시사항 제거)
                lines = chat.split('\n')
                filtered_lines = []
                skip_headers = True
                for line in lines:
                    if skip_headers:
                        # "You are an autonomous" 같은 헤더 건너뛰기
                        if any(keyword in line.lower() for keyword in ['you are', 'your job', 'below is']):
                            continue
                        if line.strip() and not line.startswith('---'):
                            skip_headers = False
                    if not skip_headers:
                        filtered_lines.append(line)
                return '\n'.join(filtered_lines).strip()
            
            # TRADING_DECISIONS도 없으면 전체를 MODEL_CHAT으로
            return response.strip()
            
        except Exception as e:
            self.logger.warning(f"MODEL_CHAT 추출 오류: {e}")
            return response.strip()
    
    def _extract_trading_decisions(self, response: str) -> Tuple[Dict[str, Dict], List[str]]:
        """TRADING_DECISIONS JSON 추출 및 파싱"""
        decisions = {}
        errors = []
        
        try:
            # JSON 블록 찾기
            json_patterns = [
                r'TRADING_DECISIONS\s*[:：]?\s*\n\s*(\{.*?\})',
                r'```json\s*\n(.*?)\n```',
                r'```\s*\n(.*?)\n```',
            ]
            
            json_text = None
            for pattern in json_patterns:
                match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
                if match:
                    json_text = match.group(1).strip()
                    break
            
            # JSON 블록이 없으면 전체에서 JSON 찾기
            if not json_text:
                # 중괄호로 시작하는 JSON 찾기
                brace_match = re.search(r'\{.*\}', response, re.DOTALL)
                if brace_match:
                    json_text = brace_match.group(0).strip()
            
            if not json_text:
                errors.append("TRADING_DECISIONS JSON을 찾을 수 없습니다.")
                return decisions, errors
            
            # JSON 파싱
            try:
                # JSON 텍스트 정리 (주석, 불필요한 공백 제거)
                json_text = self._clean_json_text(json_text)
                data = json.loads(json_text)
            except json.JSONDecodeError as e:
                errors.append(f"JSON 파싱 오류: {str(e)}")
                return decisions, errors
            
            # 각 심볼별 검증 및 추출
            for symbol in self.ARENA_SYMBOLS:
                # ✅ coin 필드 지원: LLM이 "coin": "BTC" 형식으로 응답할 수 있음
                symbol_data = None
                if symbol in data:
                    symbol_data = data[symbol]
                else:
                    # coin 필드로 찾기 시도
                    for key, value in data.items():
                        if isinstance(value, dict):
                            coin_name = value.get('coin', '').upper()
                            if coin_name == symbol:
                                symbol_data = value
                                break
                
                if symbol_data is None:
                    errors.append(f"{symbol}: TRADING_DECISIONS에 누락됨")
                    continue
                
                if not isinstance(symbol_data, dict):
                    errors.append(f"{symbol}: 올바르지 않은 형식 (dict가 아님)")
                    continue
                
                # 신호 검증
                signal = symbol_data.get('signal', '').upper()
                valid_signals = ['HOLD', 'CLOSE', 'ENTER_LONG', 'ENTER_SHORT']
                if signal not in valid_signals:
                    errors.append(f"{symbol}: 유효하지 않은 신호 '{signal}' (허용: {', '.join(valid_signals)})")
                    continue
                
                # 진입 신호인 경우 TP/SL 필수 검증
                if signal in ['ENTER_LONG', 'ENTER_SHORT']:
                    profit_target = symbol_data.get('profit_target')
                    stop_loss = symbol_data.get('stop_loss')
                    
                    if profit_target is None:
                        errors.append(f"{symbol}: ENTER_* 신호인데 profit_target이 누락됨")
                    if stop_loss is None:
                        errors.append(f"{symbol}: ENTER_* 신호인데 stop_loss가 누락됨")
                    
                    if profit_target is None or stop_loss is None:
                        # TP/SL 누락은 스킵하지만 decisions에는 추가 (검증용)
                        decisions[symbol] = {
                            'signal': signal,
                            'error': 'TP/SL 누락',
                            'raw_data': symbol_data
                        }
                        continue
                
                # 수량 검증 (quantity 또는 notional_usd 중 하나 필수)
                quantity = symbol_data.get('quantity')
                notional_usd = symbol_data.get('notional_usd')
                
                if not quantity and not notional_usd:
                    if signal in ['ENTER_LONG', 'ENTER_SHORT']:
                        errors.append(f"{symbol}: 수량 정보 없음 (quantity 또는 notional_usd 필요)")
                
                # 레버리지 검증 (범위는 order_executor에서 클램핑)
                leverage = symbol_data.get('leverage', 10)
                if leverage < 1 or leverage > 125:
                    errors.append(f"{symbol}: 레버리지 범위 오류 ({leverage}, 허용: 1-125)")
                
                # decisions에 추가
                decisions[symbol] = {
                    'signal': signal,
                    'quantity': quantity,
                    'notional_usd': notional_usd,
                    'profit_target': symbol_data.get('profit_target'),
                    'stop_loss': symbol_data.get('stop_loss'),
                    'invalidation_condition': symbol_data.get('invalidation_condition', ''),
                    'leverage': leverage,
                    'confidence': symbol_data.get('confidence', 0.5),
                    'risk_usd': symbol_data.get('risk_usd', 0),
                    'raw_data': symbol_data
                }
            
            return decisions, errors
            
        except Exception as e:
            self.logger.error(f"TRADING_DECISIONS 추출 오류: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            errors.append(f"추출 오류: {str(e)}")
            return decisions, errors
    
    def _clean_json_text(self, json_text: str) -> str:
        """JSON 텍스트 정리 (주석, 불필요한 공백 제거)"""
        # 한 줄 주석 제거
        lines = json_text.split('\n')
        cleaned_lines = []
        for line in lines:
            # // 주석 제거
            if '//' in line:
                line = line[:line.index('//')]
            cleaned_lines.append(line.strip())
        
        json_text = '\n'.join(cleaned_lines)
        
        # 불필요한 공백 제거 (하지만 JSON 구조는 유지)
        json_text = re.sub(r',\s*}', '}', json_text)
        json_text = re.sub(r',\s*]', ']', json_text)
        
        return json_text

