#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
백엔드와 로그인, 신호 수신, 버전 체크 연동
"""

import requests
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio
import threading

# websockets 안전하게 import
try:
    from websockets import connect as websockets_connect
except ImportError:
    try:
        import websockets
        websockets_connect = getattr(websockets, 'connect', None)
    except Exception:
        websockets_connect = None


@dataclass
class BackendConfig:
    """백엔드 설정"""
    base_url: str
    api_key: str
    timeout: int
    retry_count: int
    retry_delay: float


@dataclass
class TradingSignal:
    """거래 신호"""
    id: str
    symbol: str
    action: str  # BUY, SELL, HOLD
    confidence: float
    price: float
    quantity: Optional[float]
    tp_price: Optional[float]
    sl_price: Optional[float]
    reason: str
    timestamp: datetime
    expires_at: Optional[datetime]


class BackendAPI:
    """백엔드 API 클라이언트"""
    
    def __init__(self, token: str, config: Optional[BackendConfig] = None):
        self.token = token
        self.config = config or BackendConfig(
            base_url="https://daltrading.net",  # 실제 백엔드 서버 URL
            api_key="",
            timeout=10,
            retry_count=3,
            retry_delay=1.0
        )
        
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        
        # 인증 헤더 설정
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        
        # WebSocket 연결
        self.websocket = None
        self.websocket_thread = None
        self.is_connected = False
        
        # 신호 콜백
        self.signal_callbacks = []
        
        # 사용자 정보
        self.user_id = None
        self.user_grade = "normal"
        self.user_email = None
        
        self.logger.info("BackendAPI 초기화 완료")
        
    def update_config(self, new_config: BackendConfig):
        """설정 업데이트"""
        self.config = new_config
        self.logger.info("백엔드 설정 업데이트 완료")
        
    def set_user_info(self, user_id: Optional[str], user_grade: Optional[str] = "normal", user_email: Optional[str] = None):
        """사용자 정보 설정"""
        # None이 들어올 수 있으므로 안전하게 문자열로 변환
        self.user_id = user_id if user_id is not None else "Unknown"
        self.user_grade = user_grade if user_grade is not None else "normal"
        self.user_email = user_email if user_email is not None else ""
        self.logger.info(f"사용자 정보 설정 완료: {self.user_id} ({self.user_grade})")
        
    def check_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/health",
                timeout=self.config.timeout
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"연결 상태 확인 오류: {e}")
            return False
            
    def get_version_info(self) -> Dict:
        """버전 정보 조회"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/version",
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"버전 정보 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"버전 정보 조회 오류: {e}")
            return {}
            
    def check_for_updates(self) -> Dict:
        """업데이트 확인"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/updates/check",
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"업데이트 확인 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"업데이트 확인 오류: {e}")
            return {}
            
    def get_user_info(self) -> Dict:
        """사용자 정보 조회"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/user/info",
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"사용자 정보 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"사용자 정보 조회 오류: {e}")
            return {}
            
    def get_trading_signals(self, limit: int = 10) -> List[TradingSignal]:
        """거래 신호 조회"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/signals",
                params={'limit': limit},
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                signals_data = response.json()
                signals = []
                
                for signal_data in signals_data:
                    signal = TradingSignal(
                        id=signal_data['id'],
                        symbol=signal_data['symbol'],
                        action=signal_data['action'],
                        confidence=signal_data['confidence'],
                        price=signal_data['price'],
                        quantity=signal_data.get('quantity'),
                        tp_price=signal_data.get('tp_price'),
                        sl_price=signal_data.get('sl_price'),
                        reason=signal_data.get('reason', ''),
                        timestamp=datetime.fromisoformat(signal_data['timestamp']),
                        expires_at=datetime.fromisoformat(signal_data['expires_at']) if signal_data.get('expires_at') else None
                    )
                    signals.append(signal)
                    
                return signals
            else:
                self.logger.error(f"거래 신호 조회 실패: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"거래 신호 조회 오류: {e}")
            return []
            
    def send_trade_result(self, trade_data: Dict) -> bool:
        """거래 결과 전송"""
        try:
            response = self.session.post(
                f"{self.config.base_url}/api/trades/result",
                json=trade_data,
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                self.logger.info("거래 결과 전송 성공")
                return True
            else:
                self.logger.error(f"거래 결과 전송 실패: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"거래 결과 전송 오류: {e}")
            return False
            
    def send_performance_data(self, performance_data: Dict) -> bool:
        """성과 데이터 전송"""
        try:
            response = self.session.post(
                f"{self.config.base_url}/api/performance/update",
                json=performance_data,
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                self.logger.info("성과 데이터 전송 성공")
                return True
            else:
                self.logger.error(f"성과 데이터 전송 실패: {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.error(f"성과 데이터 전송 오류: {e}")
            return False
            
    def get_ai_analysis(self, symbol: str) -> Dict:
        """AI 분석 결과 조회"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/ai/analysis/{symbol}",
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"AI 분석 결과 조회 실패: {response.status_code}")
                return {}
                
        except Exception as e:
            self.logger.error(f"AI 분석 결과 조회 오류: {e}")
            return {}
            
    def get_market_data(self, symbol: str, interval: str = "1m", limit: int = 100) -> List[Dict]:
        """시장 데이터 조회"""
        try:
            response = self.session.get(
                f"{self.config.base_url}/api/market/data/{symbol}",
                params={'interval': interval, 'limit': limit},
                timeout=self.config.timeout
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                self.logger.error(f"시장 데이터 조회 실패: {response.status_code}")
                return []
                
        except Exception as e:
            self.logger.error(f"시장 데이터 조회 오류: {e}")
            return []
            
    def start_websocket_connection(self):
        """WebSocket 연결 시작"""
        try:
            if self.websocket_thread and self.websocket_thread.is_alive():
                self.logger.warning("WebSocket 연결이 이미 실행 중입니다.")
                return
                
            self.websocket_thread = threading.Thread(target=self._websocket_worker)
            self.websocket_thread.daemon = True
            self.websocket_thread.start()
            
            self.logger.info("WebSocket 연결 시작")
            
        except Exception as e:
            self.logger.error(f"WebSocket 연결 시작 오류: {e}")
            
    def stop_websocket_connection(self):
        """WebSocket 연결 중지"""
        try:
            self.is_connected = False
            if self.websocket:
                asyncio.run(self.websocket.close())
                
            self.logger.info("WebSocket 연결 중지")
            
        except Exception as e:
            self.logger.error(f"WebSocket 연결 중지 오류: {e}")
            
    def _websocket_worker(self):
        """WebSocket 워커 스레드"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._websocket_handler())
        except Exception as e:
            self.logger.error(f"WebSocket 워커 오류: {e}")
            
    async def _websocket_handler(self):
        """WebSocket 핸들러"""
        try:
            if websockets_connect is None:
                self.logger.error("websockets 모듈을 사용할 수 없습니다.")
                return
                
            ws_url = self.config.base_url.replace('http', 'ws') + '/ws/signals'
            
            async with websockets_connect(ws_url) as websocket:
                self.websocket = websocket
                self.is_connected = True
                
                self.logger.info("WebSocket 연결 성공")
                
                # 연결 상태 전송
                await websocket.send(json.dumps({
                    'type': 'auth',
                    'token': self.token
                }))
                
                # 메시지 수신 루프
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        await self._handle_websocket_message(data)
                    except json.JSONDecodeError:
                        self.logger.error("잘못된 JSON 메시지 수신")
                    except Exception as e:
                        self.logger.error(f"WebSocket 메시지 처리 오류: {e}")
                        
        except Exception as e:
            self.logger.error(f"WebSocket 핸들러 오류: {e}")
        finally:
            self.is_connected = False
            
    async def _handle_websocket_message(self, data: Dict):
        """WebSocket 메시지 처리"""
        try:
            message_type = data.get('type')
            
            if message_type == 'trading_signal':
                signal = TradingSignal(
                    id=data['id'],
                    symbol=data['symbol'],
                    action=data['action'],
                    confidence=data['confidence'],
                    price=data['price'],
                    quantity=data.get('quantity'),
                    tp_price=data.get('tp_price'),
                    sl_price=data.get('sl_price'),
                    reason=data.get('reason', ''),
                    timestamp=datetime.fromisoformat(data['timestamp']),
                    expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None
                )
                
                # 콜백 함수들 호출
                for callback in self.signal_callbacks:
                    try:
                        callback(signal)
                    except Exception as e:
                        self.logger.error(f"신호 콜백 실행 오류: {e}")
                        
            elif message_type == 'system_message':
                self.logger.info(f"시스템 메시지: {data.get('message', '')}")
                
            elif message_type == 'error':
                self.logger.error(f"서버 오류: {data.get('message', '')}")
                
        except Exception as e:
            self.logger.error(f"WebSocket 메시지 처리 오류: {e}")
            
    def add_signal_callback(self, callback):
        """신호 콜백 함수 추가"""
        self.signal_callbacks.append(callback)
        
    def remove_signal_callback(self, callback):
        """신호 콜백 함수 제거"""
        if callback in self.signal_callbacks:
            self.signal_callbacks.remove(callback)
            
    def _make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Optional[Dict]:
        """HTTP 요청 실행"""
        try:
            url = f"{self.config.base_url}{endpoint}"
            
            for attempt in range(self.config.retry_count):
                try:
                    if method.upper() == 'GET':
                        response = self.session.get(url, params=params, timeout=self.config.timeout)
                    elif method.upper() == 'POST':
                        response = self.session.post(url, json=data, timeout=self.config.timeout)
                    elif method.upper() == 'PUT':
                        response = self.session.put(url, json=data, timeout=self.config.timeout)
                    elif method.upper() == 'DELETE':
                        response = self.session.delete(url, timeout=self.config.timeout)
                    else:
                        raise ValueError(f"지원하지 않는 HTTP 메서드: {method}")
                        
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 401:
                        self.logger.error("인증 실패 - 토큰이 만료되었을 수 있습니다.")
                        return None
                    else:
                        self.logger.warning(f"요청 실패 (시도 {attempt + 1}/{self.config.retry_count}): {response.status_code}")
                        
                except requests.exceptions.RequestException as e:
                    self.logger.warning(f"요청 오류 (시도 {attempt + 1}/{self.config.retry_count}): {e}")
                    
                if attempt < self.config.retry_count - 1:
                    time.sleep(self.config.retry_delay)
                    
            self.logger.error(f"최대 재시도 횟수 초과: {endpoint}")
            return None
            
        except Exception as e:
            self.logger.error(f"요청 실행 오류: {e}")
            return None
            
    def get_connection_status(self) -> Dict:
        """연결 상태 정보"""
        return {
            'is_connected': self.is_connected,
            'base_url': self.config.base_url,
            'websocket_active': self.websocket_thread and self.websocket_thread.is_alive(),
            'last_check': datetime.now()
        }
        
    def test_connection(self) -> Dict:
        """연결 테스트"""
        try:
            start_time = time.time()
            is_connected = self.check_connection()
            response_time = time.time() - start_time
            
            return {
                'success': is_connected,
                'response_time': round(response_time, 3),
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'timestamp': datetime.now()
            }

    # ──────────────────────────────────────────────────────────────────────
    # 커뮤니티 QnA / Chat 실시간 연동
    # ──────────────────────────────────────────────────────────────────────

    def get_community_qna_list(self, limit: int = 20, offset: int = 0,
                                category: Optional[str] = None) -> Dict[str, Any]:
        """커뮤니티 QnA 목록 조회.
        
        Args:
            limit: 페이지당 항목 수 (기본 20)
            offset: 시작 오프셋
            category: 카테고리 필터 (예: 'trading', 'etf', 'general')
        
        Returns:
            {
                'status': 'ok' | 'error',
                'total': int,
                'items': [{
                    'id': str,
                    'title': str,
                    'content': str,
                    'author': str,
                    'category': str,
                    'answer_count': int,
                    'created_at': str,
                    'updated_at': str,
                    'is_answered': bool,
                }],
            }
        """
        try:
            params: Dict[str, Any] = {'limit': limit, 'offset': offset}
            if category:
                params['category'] = category
            data = self._make_request('GET', '/api/community/qna', params=params)
            if not data:
                return {'status': 'error', 'error': 'no_response', 'items': [], 'total': 0}
            return {
                'status': 'ok',
                'total': data.get('total', 0),
                'items': data.get('items', []),
            }
        except Exception as e:
            self.logger.error(f"커뮤니티 QnA 목록 조회 실패: {e}")
            return {'status': 'error', 'error': str(e), 'items': [], 'total': 0}

    def get_community_qna_detail(self, qna_id: str) -> Dict[str, Any]:
        """커뮤니티 QnA 상세 조회 (질문 + 답변 목록).
        
        Returns:
            {
                'status': 'ok' | 'error',
                'question': { id, title, content, author, category, created_at },
                'answers': [{ id, content, author, created_at, is_accepted }],
            }
        """
        try:
            data = self._make_request('GET', f'/api/community/qna/{qna_id}')
            if not data:
                return {'status': 'error', 'error': 'not_found', 'question': {}, 'answers': []}
            return {
                'status': 'ok',
                'question': data.get('question', {}),
                'answers': data.get('answers') or [],
            }
        except Exception as e:
            self.logger.error(f"커뮤니티 QnA 상세 조회 실패: {qna_id} - {e}")
            return {'status': 'error', 'error': str(e), 'question': {}, 'answers': []}

    def post_community_question(self, title: str, content: str,
                                 category: str = 'general') -> Dict[str, Any]:
        """커뮤니티 질문 등록.
        
        Returns:
            { 'status': 'ok' | 'error', 'qna_id': str }
        """
        try:
            if not title or not content:
                return {'status': 'error', 'error': 'title_and_content_required'}
            payload = {'title': title[:200], 'content': content[:5000], 'category': category}
            data = self._make_request('POST', '/api/community/qna', data=payload)
            if not data:
                return {'status': 'error', 'error': 'post_failed'}
            return {'status': 'ok', 'qna_id': data.get('id', '')}
        except Exception as e:
            self.logger.error(f"커뮤니티 질문 등록 실패: {e}")
            return {'status': 'error', 'error': str(e)}

    def post_community_answer(self, qna_id: str, content: str) -> Dict[str, Any]:
        """커뮤니티 답변 등록.
        
        Returns:
            { 'status': 'ok' | 'error', 'answer_id': str }
        """
        try:
            if not qna_id or not content:
                return {'status': 'error', 'error': 'qna_id_and_content_required'}
            payload = {'content': content[:5000]}
            data = self._make_request('POST', f'/api/community/qna/{qna_id}/answers', data=payload)
            if not data:
                return {'status': 'error', 'error': 'post_failed'}
            return {'status': 'ok', 'answer_id': data.get('id', '')}
        except Exception as e:
            self.logger.error(f"커뮤니티 답변 등록 실패: {qna_id} - {e}")
            return {'status': 'error', 'error': str(e)}

    def get_community_chat_recent(self, room: str = 'general',
                                   limit: int = 50) -> Dict[str, Any]:
        """커뮤니티 채팅방 최근 메시지 조회.
        
        Args:
            room: 채팅방 식별자 ('general' | 'trading' | 'etf' | 'crypto')
            limit: 최근 메시지 수
        
        Returns:
            {
                'status': 'ok' | 'error',
                'room': str,
                'messages': [{ 'id', 'author', 'content', 'timestamp' }],
            }
        """
        try:
            params = {'room': room, 'limit': max(1, min(limit, 200))}
            data = self._make_request('GET', '/api/community/chat/messages', params=params)
            if not data:
                return {'status': 'error', 'error': 'no_response', 'room': room, 'messages': []}
            return {
                'status': 'ok',
                'room': room,
                'messages': data.get('messages', []),
            }
        except Exception as e:
            self.logger.error(f"커뮤니티 채팅 조회 실패: {room} - {e}")
            return {'status': 'error', 'error': str(e), 'room': room, 'messages': []}

    def send_community_chat_message(self, content: str,
                                     room: str = 'general') -> Dict[str, Any]:
        """커뮤니티 채팅 메시지 전송.
        
        Args:
            content: 메시지 내용 (최대 500자)
            room: 채팅방 식별자
        
        Returns:
            { 'status': 'ok' | 'error', 'message_id': str }
        """
        try:
            if not content or not content.strip():
                return {'status': 'error', 'error': 'empty_message'}
            payload = {'content': content.strip()[:500], 'room': room}
            data = self._make_request('POST', '/api/community/chat/messages', data=payload)
            if not data:
                return {'status': 'error', 'error': 'send_failed'}
            return {'status': 'ok', 'message_id': data.get('id', '')}
        except Exception as e:
            self.logger.error(f"커뮤니티 채팅 전송 실패: {e}")
            return {'status': 'error', 'error': str(e)}

    def get_community_notices(self, limit: int = 10) -> Dict[str, Any]:
        """커뮤니티 공지사항 조회.
        
        Returns:
            {
                'status': 'ok' | 'error',
                'notices': [{ 'id', 'title', 'content', 'pinned', 'created_at' }],
            }
        """
        try:
            params = {'limit': limit}
            data = self._make_request('GET', '/api/community/notices', params=params)
            if not data:
                return {'status': 'error', 'error': 'no_response', 'notices': []}
            return {'status': 'ok', 'notices': data.get('notices', [])}
        except Exception as e:
            self.logger.error(f"커뮤니티 공지사항 조회 실패: {e}")
            return {'status': 'error', 'error': str(e), 'notices': []}
