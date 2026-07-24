#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
바이낸스 REST API 및 WebSocket 클라이언트 구성
시세, 호가, 거래 요청, 청산, 잔고 확인 등
"""
# 표준 라이브러리
import asyncio
import hmac
import hashlib
import json
import logging
import math
import threading
import time
import traceback
import websocket
import websockets
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple, Set
from urllib.parse import urlencode

# 서드파티 라이브러리
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException, BinanceOrderException


@dataclass
class BinanceConfig:
    """바이낸스 설정"""
    api_key: str
    secret_key: str
    testnet: bool = False
    timeout: int = 30  # 타임아웃을 30초로 증가
    recv_window: int = 5000


@dataclass
class OrderRequest:
    """주문 요청"""
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT, STOP_MARKET, TAKE_PROFIT_MARKET
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"  # GTC, IOC, FOK


@dataclass
class Position:
    """포지션 정보"""
    symbol: str
    side: str  # LONG, SHORT
    size: float
    entry_price: float
    mark_price: float
    unrealized_pnl: float
    liquidation_price: float
    leverage: int
    margin_type: str


class BinanceWebSocketManager:
    """실제 작동하는 바이낸스 WebSocket 매니저"""

    _instance = None
    _initialized = False

    def __new__(cls, api_key: str, secret_key: str):
        """싱글톤 패턴으로 중복 생성 방지"""
        if cls._instance is None:
            cls._instance = super(BinanceWebSocketManager, cls).__new__(cls)
        return cls._instance

    def __init__(self, api_key: str, secret_key: str):
        # 🔥 싱글톤 패턴: 이미 초기화된 경우 연결 상태 확인 후 스킵
        if BinanceWebSocketManager._initialized:
            # 연결 상태 확인 - 연결이 끊어진 경우 재연결 (비동기)
            if hasattr(self, '_connected') and not self._connected:
                self.log_event('system', "🔄 WebSocket 연결 끊어짐 감지 - 재연결 시도", level='WARNING')
                # 비동기 재연결 시작
                def async_reconnect():
                    try:
                        self._reconnect_websocket()
                        self.log_event('system', "✅ WebSocket 재연결 성공")
                    except Exception as e:
                        self.log_event('system', f"❌ WebSocket 재연결 실패: {str(e)}", level='ERROR')

                reconnect_thread = threading.Thread(target=async_reconnect)
                reconnect_thread.daemon = True
                reconnect_thread.start()
            return

        self.logger = logging.getLogger(__name__)

        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange='binance': log_event(category, msg, exchange=exchange, level=level)

        # 🔥 생성자에서는 초기화 로그 출력하지 않음 (initialize_market_data에서 출력)
        # self.log_event('system', "🔄 BinanceWebSocketManager initialization started...")

        # 데이터 구조 통합
        self.connection_status = {}
        self.market_data = {}
        self.orderbooks = {}
        self.tickers = {}
        self.funding_rates = {}

        # 🔥 활성 구독 관리
        self.active_subscriptions = set()
        # 🔇 Invalid symbol 중복 로그 억제를 위한 캐시
        self._invalid_ws_symbols_logged: Set[str] = set()

        self.last_ping_time = time.time()
        self.ping_interval = 30  # 30초마다 ping
        self.ping_thread = None
        self._stop_ping = threading.Event()

        # 🔥 데이터 구조 중복 제거 - tickers, orderbooks만 사용

        self.lock = threading.RLock()  # 재진입 가능한 락 유지
        self._connected = False
        self._connection_event = threading.Event()

        # 🔥 설정 기반 DEBUG 로그 제어를 위한 설정 로드
        self._load_debug_settings()

        self.log_event('system', "✅ BinanceWebSocketManager data structures initialized", level='DEBUG')

        # 🔥 WebSocket 연결을 비동기로 처리하여 대시보드 열림 지연 방지
        self.log_event('system', "🔄 WebSocket 연결을 백그라운드에서 시작합니다...")

        # 비동기 연결 시작 (재시도 로직 포함)
        def async_connect():
            max_retries = 3
            retry_interval = 30  # 30초 간격

            for attempt in range(max_retries):
                try:
                    self._reconnect_websocket()
                    self.log_event('system', "✅ Binance Futures WebSocket client connected successfully")
                    return
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.log_event('system', f"🔄 WebSocket 연결 재시도 {attempt + 1}/{max_retries} ({retry_interval}초 후)", level='WARNING')
                        time.sleep(retry_interval)
                    else:
                        self.log_event('system', f"❌ WebSocket connection failed after {max_retries} attempts: {str(e)}", level='ERROR')
                        self._connected = False

        # 백그라운드에서 연결 시작
        connect_thread = threading.Thread(target=async_connect)
        connect_thread.daemon = True
        connect_thread.start()

        # 🔥 싱글톤 초기화 완료 플래그 설정 (연결 성공/실패와 관계없이)
        BinanceWebSocketManager._initialized = True

    def _load_debug_settings(self):
        """🔥 설정 기반 DEBUG 로그 제어를 위한 설정 로드"""
        try:
            import json
            import os
            from path_utils import get_config_dir

            # 🔥 PyInstaller 환경 대응: path_utils 사용
            config_dir = get_config_dir()
            settings_path = os.path.join(config_dir, 'settings.json')

            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)

                # 상세로그 설정 확인
                self.verbose_trade_logging = settings.get('verbose_trade_logging', False)
                self.detailed_logs_enabled = settings.get('detailed_logs_enabled', False)
                self.log_level = settings.get('log_level', 'INFO')

                # DEBUG 로그 활성화 조건
                self.debug_logs_enabled = (
                    self.verbose_trade_logging or
                    self.detailed_logs_enabled or
                    self.log_level == 'DEBUG' or
                    self.log_level == 'ALL'
                )

                self.logger.info(f"설정 로드 완료 - DEBUG 로그: {self.debug_logs_enabled}, 상세로그: {self.detailed_logs_enabled}")
            else:
                # 기본값: DEBUG 로그 비활성화
                self.debug_logs_enabled = False
                self.verbose_trade_logging = False
                self.detailed_logs_enabled = False
                self.log_level = 'INFO'
                self.logger.warning(f"설정 파일을 찾을 수 없음: {settings_path}")

        except Exception as e:
            # 오류 시 기본값 사용
            self.debug_logs_enabled = False
            self.verbose_trade_logging = False
            self.detailed_logs_enabled = False
            self.log_level = 'INFO'
            self.logger.warning(f"설정 로드 실패, 기본값 사용: {e}")

    def _should_log_debug(self):
        """🔥 DEBUG 로그 출력 여부 결정"""
        return self.debug_logs_enabled

    def start_ping_thread(self):
        """Ping 스레드 시작"""
        if self.ping_thread is None or not self.ping_thread.is_alive():
            self._stop_ping.clear()
            self.ping_thread = threading.Thread(target=self._ping_loop)
            self.ping_thread.daemon = True
            self.ping_thread.start()
            self.log_event('system', "WebSocket connection maintenance thread started")

    def _ping_loop(self):
        """주기적으로 ping을 보내는 루프"""
        consecutive_failures = 0
        max_consecutive_failures = 3
        last_reconnect_time = 0

        while not self._stop_ping.is_set():
            try:
                current_time = time.time()
                if current_time - self.last_ping_time > self.ping_interval:
                    if self._connected and hasattr(self, 'ws') and self.ws.sock:
                        self.ws.sock.ping()
                        self.last_ping_time = current_time
                        consecutive_failures = 0
                        # WebSocket ping 성공 로그 제거 (반복적이고 불필요)
                    else:
                        consecutive_failures += 1
                        self.logger.warning(f"WebSocket connection lost, consecutive failures: {consecutive_failures}")

                        if consecutive_failures >= max_consecutive_failures:
                            if current_time - last_reconnect_time >= 1800:  # 30분 대기
                                self.logger.error(f"WebSocket connection lost after {consecutive_failures} consecutive failures, attempting reconnection")
                                # 비동기 재연결
                                def async_reconnect():
                                    try:
                                        self._reconnect_websocket()
                                        self.logger.info("WebSocket reconnection successful")
                                    except Exception as e:
                                        self.logger.error(f"WebSocket reconnection failed: {e}")

                                reconnect_thread = threading.Thread(target=async_reconnect)
                                reconnect_thread.daemon = True
                                reconnect_thread.start()
                                consecutive_failures = 0
                                last_reconnect_time = current_time
                                time.sleep(300)
                            else:
                                self.logger.warning(f"WebSocket reconnection skipped, waiting for 30 minutes...")
                                time.sleep(60)
            except Exception as e:
                consecutive_failures += 1
                self.logger.error(f"Ping loop error: {str(e)}, consecutive failures: {consecutive_failures}")
                if consecutive_failures >= max_consecutive_failures:
                    time.sleep(300)
            time.sleep(1)

    def _reconnect_websocket(self):
        """WebSocket 재연결"""
        try:
            self.logger.info("🔄 WebSocket reconnection process started...")
            with self.lock:
                if hasattr(self, 'ws'):
                    self.logger.info("🔄 Closing existing WebSocket connection...")
                    self.ws.close()

                self._connection_event.clear()
                self._connected = False

                self.logger.info("🔄 Creating new WebSocket connection to wss://fstream.binance.com/ws...")
                self.ws = websocket.WebSocketApp(
                    "wss://fstream.binance.com/ws/btcusdt@ticker",
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                    on_open=self.on_open,
                    on_ping=self.on_ping,
                    on_pong=self.on_pong
                )

                self.logger.info("🔄 Starting WebSocket thread...")
                self.ws_thread = threading.Thread(target=self.ws.run_forever)
                self.ws_thread.daemon = True
                self.ws_thread.start()

                self.logger.info("🔄 Waiting for WebSocket connection (timeout: 15s)...")
                if not self._connection_event.wait(timeout=15):
                    raise Exception("WebSocket connection timeout")

                self.logger.info("🔄 Starting ping thread...")
                self.start_ping_thread()
                self.logger.info("✅ WebSocket reconnection successful")

        except Exception as e:
            self.logger.error(f"❌ WebSocket reconnection failed: {str(e)}")
            self.logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            self._connected = False
            raise

    def on_ping(self, ws, message):
        """Ping 수신 시 처리"""
        self.logger.debug("Server ping received")
        self.last_ping_time = time.time()

    def on_pong(self, ws, message):
        """Pong 수신 시 처리"""
        self.logger.debug("Server pong received")
        self.last_ping_time = time.time()

    def start_ticker_socket(self, symbol):
        """티커 웹소켓 구독 시작"""
        if not symbol or symbol == 'USDT':
            sym = str(symbol) if symbol else 'None'
            if sym not in self._invalid_ws_symbols_logged:
                self._invalid_ws_symbols_logged.add(sym)
                # 첫 발생은 warning, 이후는 debug로 억제
                self.logger.warning(f"[WebSocket] Invalid symbol (구독 건너뜀): {sym}")
            else:
                self.logger.debug(f"[WebSocket] Invalid symbol (중복, 억제됨): {sym}")
            return False

        if self.connection_status.get(symbol, {}).get("ticker", False):
            self.logger.debug(f"[WebSocket] {symbol} ticker already connected")
            return True

        if symbol not in self.connection_status:
            self.connection_status[symbol] = {'ticker': False, 'orderbook': False}
        else:
            self.connection_status[symbol]["ticker"] = False

        try:
            if not self.ws or not self.ws.sock or not self._connected:
                self.logger.warning(f"[WebSocket] {symbol} connection lost, reconnecting")
                self._reconnect_websocket()
                if not self._connection_event.wait(timeout=10):
                    self.logger.error(f"[WebSocket] {symbol} reconnection timeout")
                    return False

            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@ticker"],
                "id": int(time.time())
            }

            self.ws.send(json.dumps(subscribe_message))
            self.logger.debug(f"[WebSocket] {symbol} ticker subscription sent")

            timeout = time.time() + 10
            check_interval = 0.1

            while time.time() < timeout:
                if not self._connected:
                    self.logger.error(f"[WebSocket] {symbol} connection lost during subscription")
                    return False

                if self.connection_status[symbol].get("ticker"):
                    ticker_data = self.get_latest_ticker(symbol)
                    if ticker_data and isinstance(ticker_data, dict) and 'price' in ticker_data:
                        self.logger.debug(f"[WebSocket] {symbol} ticker data received successfully")
                        return True
                    else:
                        self.logger.debug(f"[WebSocket] {symbol} ticker data incomplete, waiting...")

                time.sleep(check_interval)

            self.logger.warning(f"[WebSocket] {symbol} ticker connection timeout after 10s")
            return False

        except Exception as e:
            self.logger.error(f"[WebSocket] {symbol} ticker subscription failed: {str(e)}")
            return False

    def on_open(self, ws):
        """웹소켓 연결 성공 시 호출"""
        self._connected = True
        self._connection_event.set()
        self.logger.info("✅ WebSocket connected successfully to Binance Futures")

    def on_message(self, ws, message):
        try:
            msg = json.loads(message)

            if isinstance(msg, dict) and 'result' in msg:
                return

            if isinstance(msg, dict) and msg.get('e') in ['24hrTicker', 'ticker']:
                symbol = msg.get('s', 'unknown')
                price = msg.get('c', 'N/A')
                self.handle_ticker_message(msg)
                return

            if isinstance(msg, dict) and msg.get('e') == 'bookTicker':
                symbol = msg.get('s', 'unknown')
                bid = msg.get('b', 'N/A')
                ask = msg.get('a', 'N/A')
                self.handle_orderbook_message(msg)
                return

        except Exception as e:
            self.logger.error(f"[WebSocket] Message processing error: {str(e)}")

    def on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")
        self._connected = False

    def on_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket closed: status_code={close_status_code}, message={close_msg}")
        self._connected = False

    def handle_ticker_message(self, msg):
        with self.lock:
            try:
                if not isinstance(msg, dict) or 's' not in msg:
                    return

                symbol = msg['s']

                if not symbol or symbol == 'USDT':
                    return

                price = msg.get('c') or msg.get('p') or msg.get('lastPrice')
                if not price:
                    return

                try:
                    price = float(price)
                    if price <= 0:
                        return
                except (ValueError, TypeError):
                    return

                volume = 0.0
                try:
                    volume = float(msg.get('v', 0.0))
                except (ValueError, TypeError):
                    pass

                price_change = 0.0
                try:
                    raw_change = msg.get('P', '0')
                    price_change = float(raw_change)
                    if abs(price_change) > 100:
                        price_change = 0.0
                except (ValueError, TypeError):
                    pass

                ticker_data = {
                    'price': price,
                    'v': volume,
                    'P': price_change,
                    'timestamp': time.time()
                }

                self.tickers[symbol] = ticker_data

                if symbol not in self.connection_status:
                    self.connection_status[symbol] = {'ticker': False, 'orderbook': False}

                if not self.connection_status[symbol].get('ticker'):
                    self.connection_status[symbol]['ticker'] = True
                    self.logger.info(f"[WebSocket] ✅ {symbol} ticker connection established")

            except Exception as e:
                self.logger.error(f"Ticker message processing error for {msg.get('s', 'Unknown')}: {str(e)}")

    def get_latest_ticker(self, symbol):
        """최신 티커 데이터 조회"""
        with self.lock:
            if not symbol or symbol == 'USDT':
                return None

            data = self.tickers.get(symbol)

            if data and isinstance(data, dict):
                timestamp = data.get('timestamp', 0)
                age = time.time() - timestamp

                if age < 30:
                    return data
                else:
                    self.logger.debug(f"[WebSocket] ❌ {symbol} ticker data outdated: age={age:.1f}s (limit: 30s)")
            else:
                connection_status = self.connection_status.get(symbol, {})
                ticker_status = connection_status.get('ticker', False)
                self.logger.debug(f"[WebSocket] ❌ {symbol} ticker data not found - subscription status: {ticker_status}, connected: {self._connected}")

            return None

    def start_orderbook_socket(self, symbol):
        """오더북 웹소켓 구독 시작"""
        if not symbol or symbol == 'USDT':
            sym = str(symbol) if symbol else 'None'
            if sym not in self._invalid_ws_symbols_logged:
                self._invalid_ws_symbols_logged.add(sym)
                self.logger.warning(f"[WebSocket] Invalid symbol (구독 건너뜀): {sym}")
            else:
                self.logger.debug(f"[WebSocket] Invalid symbol (중복, 억제됨): {sym}")
            return False

        if self.connection_status.get(symbol, {}).get("orderbook", False):
            self.logger.debug(f"[WebSocket] {symbol} orderbook already connected")
            return True

        if symbol not in self.connection_status:
            self.connection_status[symbol] = {'ticker': False, 'orderbook': False}
        else:
            self.connection_status[symbol]["orderbook"] = False

        try:
            if not self.ws or not self.ws.sock or not self._connected:
                self.logger.warning(f"[WebSocket] {symbol} connection lost, reconnecting")
                self._reconnect_websocket()
                if not self._connection_event.wait(timeout=10):
                    self.logger.error(f"[WebSocket] {symbol} reconnection timeout")
                    return False

            subscribe_message = {
                "method": "SUBSCRIBE",
                "params": [f"{symbol.lower()}@bookTicker"],
                "id": int(time.time())
            }
            self.ws.send(json.dumps(subscribe_message))
            self.logger.debug(f"[WebSocket] {symbol} orderbook subscription sent")

            timeout = time.time() + 10
            check_interval = 0.1

            while time.time() < timeout:
                if not self._connected:
                    self.logger.error(f"[WebSocket] {symbol} connection lost during subscription")
                    return False

                if self.connection_status[symbol].get("orderbook"):
                    orderbook_data = self.get_latest_orderbook(symbol)
                    if orderbook_data and isinstance(orderbook_data, dict) and 'bids' in orderbook_data and 'asks' in orderbook_data:
                        self.logger.debug(f"[WebSocket] {symbol} orderbook data received successfully")
                        return True
                    else:
                        self.logger.debug(f"[WebSocket] {symbol} orderbook data incomplete, waiting...")

                time.sleep(check_interval)

            self.logger.warning(f"[WebSocket] {symbol} orderbook connection timeout after 10s")
            return False

        except Exception as e:
            self.logger.error(f"[WebSocket] {symbol} orderbook subscription failed: {str(e)}")
            return False

    def handle_orderbook_message(self, msg):
        with self.lock:
            try:
                if not isinstance(msg, dict) or 's' not in msg:
                    return

                symbol = msg['s']

                if not symbol or symbol == 'USDT':
                    return

                required_fields = ['b', 'B', 'a', 'A']
                if not all(key in msg for key in required_fields):
                    return

                try:
                    bid_price = float(msg['b'])
                    bid_quantity = float(msg['B'])
                    ask_price = float(msg['a'])
                    ask_quantity = float(msg['A'])

                    if bid_price <= 0 or ask_price <= 0 or bid_quantity <= 0 or ask_quantity <= 0:
                        return

                except (ValueError, TypeError):
                    return

                orderbook_data = {
                    'bids': [[bid_price, bid_quantity]],
                    'asks': [[ask_price, ask_quantity]],
                    'timestamp': time.time()
                }

                self.orderbooks[symbol] = orderbook_data

                if symbol not in self.connection_status:
                    self.connection_status[symbol] = {'ticker': False, 'orderbook': False}

                if not self.connection_status[symbol].get('orderbook'):
                    self.connection_status[symbol]['orderbook'] = True
                    self.logger.info(f"[WebSocket] ✅ {symbol} orderbook connection established")

            except Exception as e:
                self.logger.error(f"Orderbook message processing error for {msg.get('s', 'Unknown')}: {str(e)}")

    def get_latest_orderbook(self, symbol):
        """최신 오더북 데이터 조회"""
        with self.lock:
            if not symbol or symbol == 'USDT':
                return None

            data = self.orderbooks.get(symbol)

            if data and isinstance(data, dict):
                timestamp = data.get('timestamp', 0)
                age = time.time() - timestamp

                if age < 30:
                    return data
                else:
                    self.logger.debug(f"[WebSocket] ❌ {symbol} orderbook data outdated: age={age:.1f}s (limit: 30s)")
            else:
                connection_status = self.connection_status.get(symbol, {})
                orderbook_status = connection_status.get('orderbook', False)
                self.logger.debug(f"[WebSocket] ❌ {symbol} orderbook data not found - subscription status: {orderbook_status}, connected: {self._connected}")

            return None

    def initialize_market_data(self, symbols, max_wait_time=10):
        """시장 데이터 초기화 및 웹소켓 설정"""
        start_time = time.time()

        # 🔥 싱글톤 패턴: WebSocket 연결은 한 번만, 하지만 심볼 구독은 매번 가능
        if BinanceWebSocketManager._initialized:
            self.logger.debug(f"WebSocket already initialized, subscribing to symbols: {symbols}")
            # WebSocket 연결 상태 확인
            self.logger.info(f"🔍 WebSocket 상태 확인 - 연결됨: {self._connected}, 스레드 활성: {hasattr(self, 'ws_thread') and self.ws_thread and self.ws_thread.is_alive()}")
            # WebSocket은 이미 초기화되었지만 심볼 구독은 진행
        else:
            # 🔥 초기화 로그는 여기서만 출력
            self.log_event('system', "🔄 BinanceWebSocketManager initialization started...")
            self.logger.info(f"Market data initialization started - target symbols: {symbols}")

        successful_symbols = []
        retry_symbols = []

        if not self._connected:
            self.logger.warning("WebSocket connection lost, reconnecting")
            self._reconnect_websocket()
            if not self._connection_event.wait(timeout=10):
                self.logger.error("WebSocket reconnection failed")
                return ['BTCUSDT', 'ETHUSDT']

        def initialize_symbol(symbol, is_retry=False):
            try:
                # 🔥 WebSocket 데이터가 없으면 무조건 구독 시도
                ticker_data = self.get_latest_ticker(symbol)
                orderbook_data = self.get_latest_orderbook(symbol)

                # 데이터가 있고 최신이면 스킵
                if ticker_data and orderbook_data:
                    ticker_age = time.time() - ticker_data.get('timestamp', 0)
                    if ticker_age < 30:  # 30초 이내 데이터면 스킵
                        self.logger.debug(f"✅ {symbol} already has fresh data (age: {ticker_age:.1f}s)")
                        return True
                    else:
                        self.logger.info(f"🔄 {symbol} data outdated (age: {ticker_age:.1f}s), reinitializing...")
                else:
                    self.logger.info(f"🔄 {symbol} no data found, initializing...")

                if symbol not in self.connection_status:
                    self.connection_status[symbol] = {'ticker': False, 'orderbook': False}
                else:
                    current_status = self.connection_status[symbol]
                    if current_status.get('ticker', False) and current_status.get('orderbook', False):
                        self.logger.debug(f"{symbol} already has active connections, skipping reinitialization")
                        return True
                    else:
                        self.connection_status[symbol] = {'ticker': False, 'orderbook': False}

                ticker_success = False
                for attempt in range(3):
                    self.logger.info(f"🔄 {symbol} ticker 구독 시도 {attempt + 1}/3")
                    if self.start_ticker_socket(symbol):
                        timeout = time.time() + 8
                        self.logger.info(f"⏳ {symbol} ticker 데이터 대기 중... (8초 타임아웃)")
                        while time.time() < timeout:
                            if self.connection_status[symbol]['ticker'] and self.get_latest_ticker(symbol):
                                ticker_success = True
                                self.logger.info(f"✅ {symbol} ticker 연결 성공!")
                                break
                            time.sleep(0.1)

                        if ticker_success:
                            self.logger.debug(f"{symbol} ticker connection established")
                            break
                        else:
                            self.logger.warning(f"{symbol} ticker data reception failed (attempt {attempt + 1}/3)")
                    else:
                        self.logger.warning(f"{symbol} ticker socket start failed (attempt {attempt + 1}/3)")
                    time.sleep(0.2)

                if not ticker_success:
                    self.logger.error(f"{symbol} ticker initialization failed after 3 attempts")
                    return False

                orderbook_success = False
                for attempt in range(3):
                    self.logger.info(f"🔄 {symbol} orderbook 구독 시도 {attempt + 1}/3")
                    if self.start_orderbook_socket(symbol):
                        timeout = time.time() + 8
                        self.logger.info(f"⏳ {symbol} orderbook 데이터 대기 중... (8초 타임아웃)")
                        while time.time() < timeout:
                            if self.connection_status[symbol]['orderbook'] and self.get_latest_orderbook(symbol):
                                orderbook_success = True
                                self.logger.info(f"✅ {symbol} orderbook 연결 성공!")
                                break
                            time.sleep(0.1)

                        if orderbook_success:
                            self.logger.debug(f"{symbol} orderbook connection established")
                            break
                        else:
                            self.logger.warning(f"{symbol} orderbook data reception failed (attempt {attempt + 1}/3)")
                    else:
                        self.logger.warning(f"{symbol} orderbook socket start failed (attempt {attempt + 1}/3)")
                    time.sleep(0.2)

                if not orderbook_success:
                    self.logger.error(f"{symbol} orderbook initialization failed after 3 attempts")
                    return False

                # 🔥 활성 구독 목록에 추가 (대문자로 정규화)
                self.active_subscriptions.add(symbol.upper())
                self.logger.info(f"✅ {symbol} initialization completed")
                return True

            except Exception as e:
                self.logger.error(f"[{symbol}] initialization error: {str(e)}")
                return False

        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_symbol = {executor.submit(initialize_symbol, symbol): symbol for symbol in symbols}
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                try:
                    if future.result():
                        successful_symbols.append(symbol)
                    else:
                        retry_symbols.append(symbol)
                except Exception as e:
                    self.logger.error(f"{symbol} processing error: {str(e)}")
                    retry_symbols.append(symbol)

        retry_count = 0
        while retry_symbols and retry_count < 3:
            retry_count += 1
            self.logger.warning(f"WebSocket initialization retry {retry_count}/3")

            current_retry = retry_symbols.copy()
            retry_symbols = []

            for symbol in current_retry:
                if initialize_symbol(symbol, is_retry=True):
                    successful_symbols.append(symbol)
                else:
                    retry_symbols.append(symbol)

        elapsed_time = time.time() - start_time
        self.logger.info(f"Market data initialization completed")

        # 🔥 초기화 완료 플래그 설정
        self._initialization_completed = True

        if len(successful_symbols) >= 3:
            return [s for s in symbols if s in successful_symbols]
        else:
            self.logger.warning(f"WebSocket initialization partially failed (success: {len(successful_symbols)} symbols)")
            return ['BTCUSDT', 'ETHUSDT']

    def stop(self):
        """웹소켓 연결 종료"""
        try:
            self.logger.info("WebSocket manager shutdown attempt")
            if hasattr(self, 'ws'):
                self.ws.close()
            self.logger.info("WebSocket manager shutdown completed")
        except Exception as e:
            self.logger.error(f"WebSocket shutdown error: {str(e)}")

    def subscribe_symbol(self, symbol: str) -> bool:
        """🔥 개별 심볼 구독 추가"""
        try:
            # 심볼 정규화(저장/상태는 대문자 기준, 전송은 내부에서 lower 처리)
            symbol = str(symbol).strip().upper()
            # 심볼 정규화
            symbol = str(symbol).strip().upper()

            # 가능 시 서버에 구독 해제 전송
            try:
                if hasattr(self, 'ws') and getattr(self, 'ws', None) and getattr(self.ws, 'sock', None) and self._connected:
                    for stream in (f"{symbol.lower()}@ticker", f"{symbol.lower()}@bookTicker"):
                        msg = {"method": "UNSUBSCRIBE", "params": [stream], "id": int(time.time())}
                        try:
                            self.ws.send(json.dumps(msg))
                            self.logger.debug(f"[WebSocket] {symbol} unsubscribe sent for {stream}")
                        except Exception as e:
                            self.logger.debug(f"[WebSocket] {symbol} unsubscribe send failed for {stream}: {e}")
            except Exception:
                # 전송 실패는 치명적이지 않음
                pass
            if symbol not in self.connection_status:
                self.connection_status[symbol] = {'ticker': False, 'orderbook': False}

            # ticker 소켓 시작
            if self.start_ticker_socket(symbol):
                self.logger.info(f"✅ {symbol} ticker 구독 추가 성공")
            else:
                self.logger.error(f"❌ {symbol} ticker 구독 추가 실패")
                return False

            # orderbook 소켓 시작
            if self.start_orderbook_socket(symbol):
                self.logger.info(f"✅ {symbol} orderbook 구독 추가 성공")
            else:
                self.logger.error(f"❌ {symbol} orderbook 구독 추가 실패")
                return False

            # 활성 구독 목록에 추가 (대문자로 정규화)
            if not hasattr(self, 'active_subscriptions'):
                self.active_subscriptions = set()
            self.active_subscriptions.add(symbol.upper())

            return True

        except Exception as e:
            self.logger.error(f"{symbol} 구독 추가 오류: {e}")
            return False

    # === WS 책임 이관: 채널별 구독/헬스/보장/추천 간격 ===
    # 🔥 중복된 래퍼 메서드들 제거됨 - ensure_ws_for에서 직접 start_ticker_socket, start_orderbook_socket 호출

    def is_stream_alive(self, symbol: str, channel: str) -> bool:
        """채널별 구독 생존 여부 조회: channel in {'ticker','depth'}"""
        try:
            symbol = str(symbol).strip().upper()
            status = getattr(self, 'connection_status', {}).get(symbol, {})
            if channel == 'ticker':
                return bool(status.get('ticker'))
            if channel in ('depth', 'orderbook'):
                return bool(status.get('orderbook'))
            return False
        except Exception:
            return False

    def ensure_ws_for(self, symbol: str) -> bool:
        """심볼에 대해 필요한 채널 구독을 보장하고 헬스체크/재구독 수행."""
        try:
            symbol = str(symbol).strip().upper()

            # 🔥 중복 구독 방지: 이미 구독된 채널 확인
            ticker_ok = self.is_stream_alive(symbol, 'ticker')
            depth_ok = self.is_stream_alive(symbol, 'depth')

            # 필요한 채널만 구독 (중복 방지)
            if not ticker_ok and hasattr(self, 'start_ticker_socket'):
                ticker_ok = self.start_ticker_socket(symbol)
                if ticker_ok:
                    self.logger.info(f"✅ {symbol} ticker 구독 성공")
                else:
                    self.logger.warning(f"❌ {symbol} ticker 구독 실패")

            if not depth_ok and hasattr(self, 'start_orderbook_socket'):
                depth_ok = self.start_orderbook_socket(symbol)
                if depth_ok:
                    self.logger.info(f"✅ {symbol} orderbook 구독 성공")
                else:
                    self.logger.warning(f"❌ {symbol} orderbook 구독 실패")

            # 최종 헬스체크
            final_ticker_ok = self.is_stream_alive(symbol, 'ticker')
            final_depth_ok = self.is_stream_alive(symbol, 'depth')

            self.logger.info(f"[{symbol}] WebSocket health: ticker={'✓' if final_ticker_ok else '✗'}, depth={'✓' if final_depth_ok else '✗'}")

            return final_ticker_ok or final_depth_ok

        except Exception as e:
            self.logger.warning(f"[{symbol}] ensure_ws_for 오류: {e}")
            return False

    def recommended_monitor_interval(self, symbol: Optional[str] = None, default_interval: int = 10) -> int:
        """WS가 살아있으면 2초, 아니면 기본 간격."""
        try:
            if symbol and (self.is_stream_alive(symbol, 'depth') or self.is_stream_alive(symbol, 'ticker')):
                return 2
        except Exception:
            pass
        return default_interval

    def unsubscribe_symbol(self, symbol: str) -> bool:
        """🔥 개별 심볼 구독 해제"""
        try:
            # 심볼 정규화
            symbol = str(symbol).strip().upper()

            # 서버에 구독 해제 전송 (가능 시)
            try:
                if hasattr(self, 'ws') and getattr(self, 'ws', None) and getattr(self.ws, 'sock', None) and self._connected:
                    for stream in (f"{symbol.lower()}@ticker", f"{symbol.lower()}@bookTicker"):
                        msg = {"method": "UNSUBSCRIBE", "params": [stream], "id": int(time.time())}
                        try:
                            self.ws.send(json.dumps(msg))
                            self.logger.debug(f"[WebSocket] {symbol} unsubscribe sent for {stream}")
                        except Exception as e:
                            self.logger.debug(f"[WebSocket] {symbol} unsubscribe send failed for {stream}: {e}")
            except Exception:
                pass

            # 활성 구독 목록에서 제거 (대문자로 정규화)
            if hasattr(self, 'active_subscriptions'):
                self.active_subscriptions.discard(symbol.upper())

            # 연결 상태 초기화
            if symbol in self.connection_status:
                self.connection_status[symbol] = {'ticker': False, 'orderbook': False}

            # 데이터 정리
            if symbol in self.tickers:
                del self.tickers[symbol]
            if symbol in self.orderbooks:
                del self.orderbooks[symbol]

            self.logger.info(f"✅ {symbol} 구독 해제 완료")
            return True

        except Exception as e:
            self.logger.error(f"{symbol} 구독 해제 오류: {e}")
            return False

    def get_active_subscriptions(self) -> set:
        """🔥 현재 활성 구독 목록 반환"""
        return getattr(self, 'active_subscriptions', set())


class BinanceClient:
    """바이낸스 API 클라이언트"""

    def _should_log_debug(self):
        """🔥 로그 호출 버그 수정: _should_log_debug 메서드 추가"""
        try:
            import logging
            return getattr(self, "logger", None) and self.logger.isEnabledFor(logging.DEBUG)
        except Exception:
            return False

    def __init__(self, config: BinanceConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 🔥 로그 시스템 통일을 위한 헬퍼 메서드
        from log_system.log_adapter import log_event
        self.log_event = lambda category, msg, level='INFO', exchange='binance': log_event(category, msg, exchange=exchange, level=level)

        # 바이낸스 클라이언트 초기화 (타임아웃 설정)
        self.client = Client(
            api_key=config.api_key,
            api_secret=config.secret_key,
            testnet=config.testnet,
            requests_params={'timeout': config.timeout}
        )
        # 라이브러리 레벨 기본값 설정(가능한 경우): 시간 오프셋/recvWindow/고정 타임스탬프
        # Pylance 오류 방지: Client 객체에 없는 속성 할당 금지
        # (python-binance 최신 버전은 RECV_WINDOW, TIME_OFFSET 등 속성 없음)
        # 대신, 모든 요청에 recvWindow/timestamp 파라미터를 명시적으로 전달함
        # FIXED_TIMESTAMP도 실제 지원 여부 확인 필요
        # 아래 코드는 안전하게 주석 처리
        # try:
        #     if hasattr(self.client, 'RECV_WINDOW'):
        #         self.client.RECV_WINDOW = config.recv_window
        #     if hasattr(self.client, 'FIXED_TIMESTAMP'):
        #         self.client.FIXED_TIMESTAMP = True
        # except Exception:
        #     pass

        # WebSocket 매니저 초기화
        self.websocket_manager = BinanceWebSocketManager(config.api_key, config.secret_key)
        # backward-compat alias
        self.ws_manager = self.websocket_manager

        # 실시간 데이터 콜백
        self.price_callbacks = []
        self.kline_callbacks = []
        self.trade_callbacks = []
        # 구독 심볼 추적(정지/정리 시 안전하게 비우기 위함)
        self.subscribed_symbols: Set[str] = set()

        # 캐시
        self.price_cache = {}
        self.cache_timeout = 1  # 초

        # 🔥 autotrade.py와 동일하게 시간 동기화 변수 추가
        self.time_offset = 0  # 서버 시간과 로컬 시간 차이
        self.last_sync_time = 0  # 마지막 동기화 시간

        self.logger.info("BinanceClient 초기화 완료")

        # 연결 상태 속성 추가
        self.is_connected = True  # 기본값으로 True 설정

        # 🔥 즉시 연결 테스트 및 시간 동기화 수행 (API 키 없으면 계정 조회 생략)
        try:
            self.logger.info("바이낸스 API 연결 테스트 및 시간 동기화 시작")
            self._sync_server_time()
            # 시간 동기화 후 클라이언트에 오프셋 적용(가능한 경우)
            # Pylance 오류 방지: TIME_OFFSET 속성 할당 금지
            # 대신 self.time_offset을 내부적으로 사용
            if self._has_api_keys():
                try:
                    futures_account = self.client.futures_account()
                    self.logger.info(f"선물 계정 정보 조회 성공: 잔고 {futures_account.get('totalWalletBalance', 0)} USDT")
                except Exception as e:
                    self.logger.warning(f"선물 계정 정보 조회 실패: {e}")
            else:
                self.logger.info("API 키 없음: 계정 정보 조회 건너뜀")
            self.logger.info("바이낸스 API 연결 테스트 및 시간 동기화 완료")
        except Exception as e:
            self.logger.error(f"바이낸스 API 연결 테스트 실패: {e}")
            # 연결 실패 시에도 계속 진행 (재시도 로직이 있으므로)

        # 심볼 유효성 캐시 (Invalid symbol 소음 방지)
        self._valid_symbols = set()          # type: Set[str]
        self._invalid_symbols = set()        # type: Set[str]
        self._symbols_last_loaded = 0.0
        # 반복 Invalid symbol / recent trades 에러 억제용 (최초 1회 warning 이후 debug)
        self._recent_trade_invalid_symbol_warned = set()  # type: Set[str]

    def _has_api_keys(self) -> bool:
        """API 키 존재 여부"""
        try:
            return bool(self.config.api_key and self.config.secret_key)
        except Exception:
            return False

    def _sync_server_time(self):
        """서버 시간과 로컬 시간 동기화 (autotrade.py와 동일)"""
        try:
            # 서버 시간 조회
            server_time = self.client.get_server_time()
            server_timestamp = server_time['serverTime']

            # 로컬 시간과 비교하여 오프셋 계산
            local_timestamp = int(time.time() * 1000)  # 밀리초 단위
            self.time_offset = server_timestamp - local_timestamp

            # 동기화 시간 기록
            self.last_sync_time = time.time()

            self.logger.info(f"✅ 시간 동기화 완료: 서버시간={server_timestamp}, 로컬시간={local_timestamp}, 오프셋={self.time_offset}ms")

            # 오프셋이 1000ms(1초) 이상이면 경고
            if abs(self.time_offset) > 1000:
                self.logger.warning(f"⚠️ 시간 차이가 큽니다: {self.time_offset}ms (1초 이상)")

            # 라이브러리 클라이언트에도 오프셋 반영(가능한 경우)
                pass

        except Exception as e:
            self.logger.error(f"❌ 시간 동기화 실패: {e}")
            self.time_offset = 0  # 기본값으로 설정

    # ---- 심볼 유효성 관리 ----
    def _normalize_symbol(self, symbol: str) -> str:
        try:
            if not symbol:
                return ''
            s = str(symbol).strip().upper()
            if '/' in s:
                s = s.replace('/', '')
            return s
        except Exception:
            return str(symbol).upper() if symbol else ''

    def _refresh_valid_symbols(self, force: bool = False) -> None:
        try:
            # 30분 캐시
            if not force and (time.time() - self._symbols_last_loaded) < 1800 and self._valid_symbols:
                return
            info = self.client.futures_exchange_info()
            valid: Set[str] = set()
            for s in info.get('symbols', []) or []:
                try:
                    if s.get('status') == 'TRADING' and s.get('contractType') == 'PERPETUAL':
                        sym = str(s.get('symbol', '')).upper()
                        if sym:
                            valid.add(sym)
                except Exception:
                    continue
            if valid:
                self._valid_symbols = valid
                self._symbols_last_loaded = time.time()
                # invalid 캐시는 보존하여 중복 로그 억제
        except Exception as e:
            # 심볼 목록 로드 실패는 치명적이지 않음
            self.logger.debug(f"심볼 목록 갱신 실패(무시): {e}")

    def is_valid_symbol(self, symbol: str) -> bool:
        s = self._normalize_symbol_safe(symbol)
        if not s or s == 'USDT':
            return False
        if s in self._invalid_symbols:
            return False
        if s in self._valid_symbols:
            return True
        # 로드 후 재확인
        self._refresh_valid_symbols()
        if s in self._valid_symbols:
            return True
        # 최종 미확인 → 임시로 invalid 표기하여 중복 호출 억제
        self._invalid_symbols.add(s)
        return False

    def get_synced_timestamp(self):
        """동기화된 타임스탬프 반환 (autotrade.py와 동일)"""
        try:
            # 5분마다 시간 동기화 갱신
            if time.time() - self.last_sync_time > 300:  # 5분
                self._sync_server_time()

            # 동기화된 타임스탬프 반환
            synced_timestamp = int(time.time() * 1000) + self.time_offset
            return synced_timestamp

        except Exception as e:
            self.logger.error(f"동기화된 타임스탬프 생성 실패: {e}")
            # 기본값으로 로컬 시간 반환
            return int(time.time() * 1000)

    def update_config(self, new_config: BinanceConfig):
        """설정 업데이트"""
        self.config = new_config
        self.client = Client(
            api_key=new_config.api_key,
            api_secret=new_config.secret_key,
            testnet=new_config.testnet,
            requests_params={'timeout': new_config.timeout}
        )
        self.logger.info("바이낸스 설정 업데이트 완료")

    def test_connection(self) -> bool:
        """연결 테스트"""
        try:
            # 서버 시간 조회
            server_time = self.client.get_server_time()
            self.logger.info(f"바이낸스 서버 시간: {server_time}")
            return True
        except Exception as e:
            self.logger.error(f"바이낸스 연결 테스트 실패: {e}")
            return False

    def validate_credentials(self) -> bool:
        """API 키 유효성 검증 (다른 거래소 어댑터와 일관성 유지)
        
        ExchangeManager.validate_exchange_connection()에서 호출됨.
        다른 거래소 어댑터들의 validate_credentials()와 동일한 인터페이스를 제공하여
        모듈화된 거래소 관리 시스템과 일관성을 유지합니다.
        
        Returns:
            bool: API 키가 유효하고 계정 정보 조회가 가능하면 True, 그렇지 않으면 False
        """
        try:
            # API 키가 없으면 False
            if not self._has_api_keys():
                self.logger.debug("API 키 검증 실패: API 키 없음")
                return False
            
            # 계정 정보 조회를 통해 API 키 유효성 검증
            # get_account_info()는 내부적으로 재시도 로직과 오류 처리가 포함되어 있음
            account_info = self.get_account_info()
            
            # 계정 정보가 정상적으로 조회되면 True
            # total_wallet_balance가 None이 아니면 유효한 응답으로 간주
            if account_info and isinstance(account_info, dict) and account_info.get('total_wallet_balance') is not None:
                self.logger.debug("API 키 검증 성공")
                return True
            
            self.logger.debug("API 키 검증 실패: 계정 정보 조회 실패")
            return False
            
        except Exception as e:
            self.logger.error(f"API 키 검증 중 오류 발생: {e}")
            return False

    def get_account_info(self) -> Dict:
        """계좌 정보 조회 (강화된 재시도 로직 및 연결 검증)"""
        # 키가 없으면 조용히 빈 값 반환 (로그 소음 억제)
        if not self._has_api_keys():
            self.logger.debug("계좌 정보 조회 건너뜀: API 키 없음")
            return {}
        max_retries = 5  # 3 → 5로 증가
        retry_delay = 2.0  # 1초 → 2초로 증가

        for attempt in range(max_retries):
            try:
                self.logger.info(f"계좌 정보 조회 시도 {attempt + 1}/{max_retries}")

                # 🔥 연결 상태 사전 확인
                if not self.test_connection():
                    self.logger.warning(f"연결 상태 불안정 (시도 {attempt + 1})")
                    time.sleep(retry_delay * 2)
                    continue

                # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
                ts = self.get_synced_timestamp()
                rw = self.config.recv_window
                account_info = self.client.futures_account(timestamp=ts, recvWindow=rw)

                # 🔥 응답 데이터 검증
                if not account_info or 'totalWalletBalance' not in account_info:
                    self.logger.warning(f"잘못된 응답 데이터 (시도 {attempt + 1})")
                    time.sleep(retry_delay)
                    continue

                result = {
                    'total_wallet_balance': float(account_info['totalWalletBalance']),
                    'total_unrealized_profit': float(account_info['totalUnrealizedProfit']),
                    'total_margin_balance': float(account_info['totalMarginBalance']),
                    'available_balance': float(account_info['availableBalance']),
                    'total_position_initial_margin': float(account_info['totalPositionInitialMargin']),
                    'total_open_order_initial_margin': float(account_info['totalOpenOrderInitialMargin']),
                    'total_cross_wallet_balance': float(account_info['totalCrossWalletBalance']),
                    'total_cross_un_pnl': float(account_info['totalCrossUnPnl']),
                    'update_time': account_info['updateTime']
                }

                self.logger.info("계좌 정보 조회 성공")
                return result

            except BinanceAPIException as e:
                self.logger.error(f"바이낸스 API 오류 (시도 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {}
                time.sleep(retry_delay * (attempt + 1))  # 점진적 대기 시간 증가

            except requests.exceptions.Timeout as e:
                self.logger.error(f"타임아웃 오류 (시도 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {}
                time.sleep(retry_delay * 3)  # 타임아웃 시 더 오래 대기

            except Exception as e:
                self.logger.error(f"계좌 정보 조회 오류 (시도 {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {}
                time.sleep(retry_delay * (attempt + 1))  # 점진적 대기 시간 증가

        return {}

    def get_balance(self) -> Dict:
        """잔고 조회"""
        # 키가 없으면 조용히 빈 값 반환
        if not self._has_api_keys():
            self.logger.debug("잔고 조회 건너뜀: API 키 없음")
            return {}
        try:
            # 동기화된 타임스탬프 + recvWindow 적용(-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window
            account_info = self.client.futures_account(timestamp=ts, recvWindow=rw)
            balances = {}

            for asset in account_info['assets']:
                try:
                    # 안전한 숫자 변환 (문자열, None, 빈 값 처리)
                    wallet_balance = float(asset.get('walletBalance', 0) or 0)
                    if wallet_balance > 0:
                        balances[asset['asset']] = {
                            'wallet_balance': wallet_balance,
                            'unrealized_profit': float(asset.get('unrealizedProfit', 0) or 0),
                            'margin_balance': float(asset.get('marginBalance', 0) or 0),
                            'available_balance': float(asset.get('availableBalance', 0) or 0)
                        }
                except (ValueError, TypeError) as e:
                    self.logger.warning(f"자산 {asset.get('asset', 'unknown')} 잔고 변환 오류: {e}, 데이터: {asset}")
                    continue

            return balances

        except Exception as e:
            self.logger.error(f"잔고 조회 오류: {e}")
            return {}

    def get_current_price(self, symbol: str) -> float:
        """현재가 조회"""
        try:
            # 🔥 방어적 심볼 정규화 적용
            symbol = self._normalize_symbol_safe(symbol)
            if not self.is_valid_symbol(symbol):
                # 한번만 디버그 출력
                if symbol and symbol not in self._valid_symbols:
                    self.logger.debug(f"🚫 현재가 조회 건너뜀 (유효하지 않은 심볼): {symbol}")
                return 0.0
            # 캐시 확인
            cache_key = f"price_{symbol}"
            if cache_key in self.price_cache:
                cached_price, timestamp = self.price_cache[cache_key]
                if (datetime.now() - timestamp).total_seconds() < self.cache_timeout:
                    return cached_price

            # API 호출
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])

            # 캐시 업데이트
            self.price_cache[cache_key] = (price, datetime.now())

            return price

        except Exception as e:
            if "Invalid symbol" in str(e):
                # 중복 에러 억제
                self._invalid_symbols.add(symbol)
                self.logger.debug(f"🚨 {symbol}: 유효하지 않은 심볼 - 현재가 조회 건너뜀")
            else:
                self.logger.error(f"현재가 조회 오류: {e}")
            return 0.0

    def get_latest_ticker(self, symbol: str) -> Optional[Dict]:
        """최신 티커 데이터 조회 (WebSocket 매니저 위임)"""
        try:
            symbol = self._normalize_symbol_safe(symbol)
            if not self.is_valid_symbol(symbol):
                return None

            # WebSocket 매니저가 있으면 위임
            if hasattr(self, 'websocket_manager') and self.websocket_manager:
                return self.websocket_manager.get_latest_ticker(symbol)

            # 마지막 폴백: REST API로 가격 조회
            price = self.get_current_price(symbol)
            return {'price': price, 'timestamp': time.time()} if price else None

        except Exception as e:
            self.logger.error(f"get_latest_ticker 오류 ({symbol}): {e}")
            return None

    def get_current_price_ws(self, symbol: str) -> float:
        """웹소켓 기반 현재가 조회 (API 제한 회피)"""
        try:
            # 🔥 방어적 심볼 정규화 적용
            symbol = self._normalize_symbol_safe(symbol)
            if not self.is_valid_symbol(symbol):
                self.log_event('system', f"🚫 {symbol}: 유효하지 않은 심볼 - 현재가 조회 건너뜀", level='WARNING')
                return 0.0

            # 먼저 WS 시도 → 실패 시 REST 폴백
            try:
                # 🔥 WebSocket 보장: ensure_ws_for 메서드 호출
                self.ensure_ws_for(symbol)
                if hasattr(self, "websocket_manager") and self.websocket_manager:
                    ticker_data = self.websocket_manager.get_latest_ticker(symbol)
                    if ticker_data and isinstance(ticker_data, dict) and 'price' in ticker_data:
                        price = float(ticker_data['price'])
                        self.log_event('system', f"[WebSocket] ✅ {symbol} 가격 조회 성공: {price}", level='DEBUG')
                        return price
                    else:
                        self.log_event('system', f"[WebSocket] ⚠️ {symbol} ticker_data 없음: {ticker_data}", level='WARNING')
                else:
                    self.log_event('system', f"[WebSocket] ⚠️ {symbol} websocket_manager 없음", level='WARNING')
            except Exception as e:
                self.log_event('system', f"[WebSocket] ❌ {symbol} WS 실패, REST 폴백: {e}", level='WARNING')

            # REST 폴백
            rest_price = self.get_current_price(symbol)
            self.log_event('system', f"[REST] 🔄 {symbol} REST 가격 조회 결과: {rest_price}", level='DEBUG')
            return rest_price

        except Exception as e:
            self.log_event('system', f"[ERROR] ❌ {symbol} 웹소켓 현재가 조회 오류: {e}", level='ERROR')
            # 폴백: REST API 사용
            try:
                rest_price = self.get_current_price(symbol)
                self.log_event('system', f"[REST] 🔄 {symbol} 예외 후 REST 폴백 결과: {rest_price}", level='DEBUG')
                return rest_price
            except Exception as e2:
                self.log_event('system', f"[ERROR] ❌ {symbol} REST 폴백도 실패: {e2}", level='ERROR')
                return 0.0

    def ensure_ws_for(self, symbol: str) -> bool:
        """WebSocket 연결 보장 (BinanceWebSocketManager 위임)"""
        try:
            if hasattr(self, "websocket_manager") and self.websocket_manager:
                return self.websocket_manager.ensure_ws_for(symbol)
            else:
                self.log_event('system', f"[WebSocket] ⚠️ {symbol} websocket_manager 없음", level='WARNING')
                return False
        except Exception as e:
            self.log_event('system', f"[WebSocket] ❌ {symbol} ensure_ws_for 실패: {e}", level='ERROR')
            return False

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[List]:
        """K라인 데이터 조회 (analyzer.py 호환용)"""
        try:
            # 🔥 방어적 심볼 정규화 적용
            symbol = self._normalize_symbol_safe(symbol)
            if not self.is_valid_symbol(symbol):
                return []

            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )

            # 형식 보정: 리스트가 아니거나 내부가 리스트가 아니면 빈 리스트 반환
            if not isinstance(klines, list):
                return []
            if klines and not isinstance(klines[0], list):
                return []
            return klines  # type: ignore[return-value]

        except Exception as e:
            if "Invalid symbol" in str(e):
                self.logger.debug(f"🚨 {symbol}: 유효하지 않은 심볼 - K라인 데이터 조회 불가")
            else:
                self.logger.error(f"K라인 데이터 조회 오류: {e}")
            return []

    def get_multiple_klines(self, symbols: List[str], interval: str, limit: int) -> Dict[str, List[List]]:
        """여러 심볼의 K라인 데이터를 일괄 조회 (API 최적화)"""
        try:
            klines_data = {}

            # 🔥 바이낸스 API는 개별 심볼만 지원하므로 병렬 처리로 최적화
            import concurrent.futures
            import threading

            def fetch_klines(symbol):
                try:
                    symbol = self._normalize_symbol_safe(symbol)
                    if not self.is_valid_symbol(symbol):
                        return symbol, []

                    klines = self.client.futures_klines(
                        symbol=symbol,
                        interval=interval,
                        limit=limit
                    )

                    # 형식 검증
                    if not isinstance(klines, list) or (klines and not isinstance(klines[0], list)):
                        return symbol, []

                    return symbol, klines

                except Exception as e:
                    if "Invalid symbol" in str(e):
                        self.logger.debug(f"🚨 {symbol}: 유효하지 않은 심볼 - K라인 데이터 조회 불가")
                    else:
                        self.logger.error(f"K라인 데이터 조회 오류 ({symbol}): {e}")
                    return symbol, []

            # 🔥 병렬 처리로 API 호출 최적화 (최대 10개 동시 처리)
            max_workers = min(10, len(symbols))
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_symbol = {executor.submit(fetch_klines, symbol): symbol for symbol in symbols}

                for future in concurrent.futures.as_completed(future_to_symbol):
                    symbol, klines = future.result()
                    if klines:
                        klines_data[symbol] = klines

            self.logger.info(f"✅ 일괄 K라인 조회 완료: {len(klines_data)}/{len(symbols)}개 성공")
            return klines_data

        except Exception as e:
            self.logger.error(f"일괄 K라인 조회 오류: {e}")
            return {}

    def get_order_book(self, symbol: str, limit: int = 20) -> Dict:
        """호가창 조회"""
        try:
            order_book = self.client.futures_order_book(
                symbol=symbol,
                limit=limit
            )

            # 🔥 응답 데이터 검증 및 안전한 접근
            if not order_book or not isinstance(order_book, dict):
                self.logger.warning(f"⚠️ {symbol}: 호가창 응답 데이터 형식 오류")
                return {}

            # 필수 키 존재 확인
            required_keys = ['bids', 'asks', 'lastUpdateId']
            if not all(key in order_book for key in required_keys):
                self.logger.warning(f"⚠️ {symbol}: 호가창 응답에 필수 키 누락")
                return {}

            # symbol 키가 없으면 파라미터로 전달받은 symbol 사용
            response_symbol = order_book.get('symbol', symbol)

            return {
                'symbol': response_symbol,
                'bids': [[float(price), float(qty)] for price, qty in order_book['bids']],
                'asks': [[float(price), float(qty)] for price, qty in order_book['asks']],
                'last_update_id': order_book['lastUpdateId']
            }

        except Exception as e:
            self.logger.error(f"호가창 조회 오류: {e}")
            return {}

    def get_positions(self) -> List[Position]:
        """포지션 조회"""
        # 키가 없으면 조용히 빈 리스트 반환
        if not self._has_api_keys():
            self.logger.debug("포지션 조회 건너뜀: API 키 없음")
            return []
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window
            positions = self.client.futures_position_information(timestamp=ts, recvWindow=rw)
            position_list = []

            for pos in positions:
                if float(pos['positionAmt']) != 0:  # 포지션이 있는 경우만
                    position = Position(
                        symbol=pos['symbol'],
                        side="LONG" if float(pos['positionAmt']) > 0 else "SHORT",
                        size=abs(float(pos['positionAmt'])),
                        entry_price=float(pos['entryPrice']),
                        mark_price=float(pos['markPrice']),
                        unrealized_pnl=float(pos['unRealizedProfit']),
                        liquidation_price=float(pos['liquidationPrice']),
                        leverage=int(pos['leverage']),
                        margin_type=pos['marginType']
                    )
                    position_list.append(position)

            return position_list

        except Exception as e:
            self.logger.error(f"포지션 조회 오류: {e}")
            return []

    def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """최근 거래 내역 조회 (실현 PnL 포함)"""
        # 키가 없으면 조용히 빈 리스트 반환
        if not self._has_api_keys():
            self.logger.debug("최근 거래 내역 조회 건너뜀: API 키 없음")
            return []
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            if symbol:
                # 특정 심볼의 거래 내역
                trades = self.client.futures_account_trades(
                    symbol=symbol,
                    limit=limit,
                    timestamp=ts,
                    recvWindow=rw
                )
            else:
                # 전체 거래 내역
                trades = self.client.futures_account_trades(
                    limit=limit,
                    timestamp=ts,
                    recvWindow=rw
                )

            # 실현 PnL 정보 포함하여 반환
            trade_list = []
            for trade in trades:
                trade_info = {
                    'id': trade.get('id'),
                    'order_id': trade.get('orderId'),
                    'symbol': trade['symbol'],
                    'side': trade['side'],
                    'quantity': float(trade['qty']),
                    'price': float(trade['price']),
                    'realized_pnl': float(trade.get('realizedPnl', 0)),
                    'commission': float(trade.get('commission', 0)),
                    'commission_asset': trade.get('commissionAsset', ''),
                    'time': trade['time']
                }
                trade_list.append(trade_info)

            return trade_list

        except Exception as e:
            # Invalid symbol 반복 억제
            if 'Invalid symbol' in str(e):
                sym = symbol if 'symbol' in locals() else ''
                if sym and sym not in self._recent_trade_invalid_symbol_warned:
                    self.logger.warning(f"최근 거래 내역 조회 Invalid symbol - 최초 1회 경고: {sym}")
                    self._recent_trade_invalid_symbol_warned.add(sym)
                else:
                    self.logger.debug(f"최근 거래 내역 조회 Invalid symbol (억제됨): {sym}")
            else:
                self.logger.error(f"최근 거래 내역 조회 오류: {e}")
            return []

    def get_open_orders(self, symbol: str) -> List[Dict]:
        """미체결 주문 조회"""
        # 키가 없으면 조용히 빈 리스트 반환
        if not self._has_api_keys():
            self.logger.debug("미체결 주문 조회 건너뜀: API 키 없음")
            return []
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            if symbol:
                orders = self.client.futures_get_open_orders(symbol=symbol, timestamp=ts, recvWindow=rw)
            else:
                orders = self.client.futures_get_open_orders(timestamp=ts, recvWindow=rw)
            return orders if isinstance(orders, list) else []

        except Exception as e:
            self.logger.error(f"미체결 주문 조회 오류: {e}")
            return []

    def get_open_algo_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """🔥 Algo Order 조회 (TP/SL 주문 검증용)
        
        Args:
            symbol: 심볼 (선택사항, None이면 모든 심볼)
        
        Returns:
            Algo Order 리스트
        """
        if not self._has_api_keys():
            self.log_event('order', "Algo Order 조회 건너뜀: API 키 없음", level='DEBUG')
            return []
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            
            # GET /fapi/v1/openAlgoOrders
            result = self._get_futures_signed("/fapi/v1/openAlgoOrders", params)
            
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "code" in result:
                self.log_event('order', f"Algo Order 조회 오류: {result}", level='ERROR')
                return []
            else:
                return []
        except Exception as e:
            self.log_event('order', f"Algo Order 조회 오류: {e}", level='ERROR')
            return []

    def _get_futures_signed(self, path: str, params: dict) -> dict:
        """GET 요청을 위한 서명된 요청 전송"""
        params = dict(params or {})
        params.setdefault("timestamp", self.get_synced_timestamp())
        params.setdefault("recvWindow", getattr(self.config, "recv_window", 5000))
        
        qs, sig = self._build_signed_query(params)
        url = f"{self._futures_base_url()}{path}?{qs}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.config.api_key}
        
        if self._should_log_debug():
            self.logger.debug(f"[FUTURES_SIGNED_GET] path={path} qs={qs} sig={sig[:16]}...")
        
        try:
            resp = requests.get(url, headers=headers, timeout=getattr(self.config, "timeout", 30))
            try:
                return resp.json()
            except Exception:
                return {"code": resp.status_code, "msg": resp.text}
        except Exception as e:
            return {"code": -1, "msg": f"REQUEST_FAILED: {e}"}

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """레버리지 설정"""
        # 키가 없으면 조용히 False 반환
        if not self._has_api_keys():
            self.logger.debug(f"레버리지 설정 건너뜀: API 키 없음 ({symbol}, {leverage}x)")
            return False
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            result = self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage,
                timestamp=ts,
                recvWindow=rw
            )
            self.logger.info(f"{symbol} 레버리지 설정: {leverage}x")
            return True

        except Exception as e:
            self.logger.error(f"레버리지 설정 오류: {e}")
            return False

    def set_margin_type(self, symbol: str, margin_type: str) -> bool:
        """마진 타입 설정 (ISOLATED/CROSSED)"""
        # 키가 없으면 조용히 False 반환
        if not self._has_api_keys():
            self.logger.debug(f"마진 타입 설정 건너뜀: API 키 없음 ({symbol}, {margin_type})")
            return False
        try:
            # 동기화된 타임스탬프 + recvWindow 적용(-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window
            result = self.client.futures_change_margin_type(
                symbol=symbol,
                marginType=margin_type,
                timestamp=ts,
                recvWindow=rw
            )
            self.logger.info(f"{symbol} 마진 타입 설정: {margin_type}")
            return True

        except Exception as e:
            self.logger.error(f"마진 타입 설정 오류: {e}")
            return False

    def place_order(self, order_request: OrderRequest) -> Dict:
        """주문 실행"""
        # 키가 없으면 조용히 SKIPPED 반환
        if not self._has_api_keys():
            self.logger.debug(f"주문 실행 건너뜀: API 키 없음 ({order_request.symbol} {order_request.side} {order_request.quantity})")
            return {'status': 'SKIPPED', 'error': 'NO_API_KEYS'}
        try:
            # 입력 정규화: 대소문자 및 별칭 방어 (case-insensitive)
            try:
                # side 정규화: BUY/SELL
                if hasattr(order_request, 'side') and isinstance(order_request.side, str):
                    order_request.side = order_request.side.upper()
                # order_type 정규화: MARKET/LIMIT/STOP_MARKET/TAKE_PROFIT_MARKET
                if hasattr(order_request, 'order_type') and isinstance(order_request.order_type, str):
                    ot = order_request.order_type.strip().upper()
                    # 허용 별칭을 표준 키로 매핑
                    alias_map = {
                        'STOP': 'STOP_MARKET',
                        'TAKE_PROFIT': 'TAKE_PROFIT_MARKET',
                        'TP_MARKET': 'TAKE_PROFIT_MARKET',
                        'SL_MARKET': 'STOP_MARKET',
                    }
                    order_request.order_type = alias_map.get(ot, ot)
            except Exception:
                # 정규화 실패는 무시하고 원본 값으로 진행
                pass

            # 수량/가격 보정: stepSize/tickSize + precision + minNotional 여유
            try:
                precisions = self.get_symbol_precisions(order_request.symbol)
                q_prec = int(precisions.get('quantity_precision', 0))
            except Exception:
                q_prec = 0
            def _fmt_qty(q: float) -> str:
                try:
                    if q_prec > 0:
                        fmt = f"{{:.{q_prec}f}}"
                        return fmt.format(float(q))
                    return str(q)
                except Exception:
                    return str(q)

            # 1) 심볼 필터 조회
            filters = {}
            try:
                filters = self.get_symbol_filters(order_request.symbol) or {}
            except Exception:
                filters = {}
            step_size = float(filters.get('stepSize') or 0)
            tick_size = float(filters.get('tickSize') or 0)
            min_qty = float(filters.get('minQty') or 0)
            min_notional = float(filters.get('minNotional') or 0)

            # 2) 수량 stepSize 내림 보정
            qty = float(order_request.quantity)
            if step_size and step_size > 0:
                try:
                    import math as _math
                    qty = _math.floor(qty / step_size) * step_size
                except Exception:
                    pass
            if min_qty and qty < min_qty:
                qty = min_qty

            # 3) 가격 tickSize 내림 보정 (지정가/트리거가 있을 때)
            price_param = order_request.price
            if price_param and tick_size and tick_size > 0:
                try:
                    import math as _math
                    price_param = _math.floor(float(price_param) / tick_size) * tick_size
                except Exception:
                    pass

            # 4) MIN_NOTIONAL 보정 비활성화 (Optimizer에서 이미 처리됨)
            # 🔥 단일 권위 원칙: Optimizer에서 MIN_NOTIONAL 보정 완료
            # 필요시 아래 주석을 해제하여 거래소 측 보정 활성화 가능
            # ENABLE_BROKER_SIDE_NOTIONAL_FIX = False
            ENABLE_BROKER_SIDE_NOTIONAL_FIX = False

            if ENABLE_BROKER_SIDE_NOTIONAL_FIX:
                try:
                    if min_notional and float(min_notional) > 0:
                        # 시장가일 경우 현재가, 지정가 주문은 지정가 사용
                        cur_price = float(price_param or 0)
                        if not cur_price:
                            cur_price = float(self.get_current_price(order_request.symbol) or 0)
                        if cur_price and cur_price > 0:
                            notional = qty * cur_price
                            if notional < float(min_notional):
                                import math as _math
                                required = (float(min_notional) * 1.005) / cur_price  # 소폭 여유 0.5%
                                if step_size and step_size > 0:
                                    qty = _math.ceil(required / step_size) * step_size
                                else:
                                    qty = required
                                if min_qty and qty < min_qty:
                                    qty = min_qty
                                self.logger.debug(f"[{order_request.symbol}] 🔧 거래소 측 MIN_NOTIONAL 보정: {qty}")
                except Exception:
                    pass

            order_params = {
                'symbol': order_request.symbol,
                'side': order_request.side,
                'type': order_request.order_type,
                # Binance API는 문자열 파라미터를 권장하므로 문자열로 변환 + precision 반영
                'quantity': _fmt_qty(qty)
            }

            if price_param:
                order_params['price'] = str(price_param)

            if order_request.stop_price:
                order_params['stopPrice'] = str(order_request.stop_price)

            if order_request.order_type != 'MARKET':
                order_params['timeInForce'] = order_request.time_in_force

            # 주문 실행
            if order_request.order_type == 'MARKET':
                result = self.client.futures_create_order(**order_params)
            elif order_request.order_type == 'LIMIT':
                result = self.client.futures_create_order(**order_params)
            elif order_request.order_type == 'STOP_MARKET':
                result = self.client.futures_create_order(**order_params)
            elif order_request.order_type == 'TAKE_PROFIT_MARKET':
                result = self.client.futures_create_order(**order_params)
            else:
                raise ValueError(f"지원하지 않는 주문 타입: {order_request.order_type}")

            self.logger.info(f"주문 실행 성공: {order_request.symbol} {order_request.side} {order_request.quantity}")

            return {
                'status': 'FILLED' if result['status'] == 'FILLED' else 'PENDING',
                'order_id': result['orderId'],
                'avg_price': float(result['avgPrice']) if result['avgPrice'] else 0.0,
                'executed_qty': float(result['executedQty']),
                'cum_quote': float(result['cumQuote']) if result['cumQuote'] else 0.0
            }

        except BinanceAPIException as e:
            self.logger.error(f"바이낸스 API 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}
        except BinanceOrderException as e:
            self.logger.error(f"주문 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}
        except Exception as e:
            self.logger.error(f"주문 실행 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """주문 취소"""
        # 키가 없으면 조용히 False 반환
        if not self._has_api_keys():
            self.logger.debug(f"주문 취소 건너뜀: API 키 없음 ({symbol}, {order_id})")
            return False
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            result = self.client.futures_cancel_order(
                symbol=symbol,
                orderId=order_id,
                timestamp=ts,
                recvWindow=rw
            )
            self.logger.info(f"주문 취소 성공: {symbol} {order_id}")
            return True

        except Exception as e:
            self.logger.error(f"주문 취소 오류: {e}")
            return False

    def cancel_all_orders(self, symbol: str) -> bool:
        """모든 주문 취소"""
        # 키가 없으면 조용히 False 반환
        if not self._has_api_keys():
            self.logger.debug(f"모든 주문 취소 건너뜀: API 키 없음 ({symbol})")
            return False
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            result = self.client.futures_cancel_all_open_orders(symbol=symbol, timestamp=ts, recvWindow=rw)
            # 🔥 실제 취소 결과 확인
            if result and result.get('code') == 200:
                self.logger.info(f"모든 주문 취소 성공: {symbol}")
                return True
            else:
                self.logger.warning(f"모든 주문 취소 실패: {symbol} - 결과: {result}")
                return False

        except Exception as e:
            self.logger.error(f"모든 주문 취소 오류: {e}")
            return False

    # 신규: 실거래 편의를 위한 보조 메서드들
    def get_symbol_precisions(self, symbol: str) -> Dict:
        """심볼 정밀도 조회(pricePrecision, quantityPrecision)"""
        try:
            info = self.client.futures_exchange_info()
            for s in info.get('symbols', []):
                if s.get('symbol') == symbol:
                    return {
                        'price_precision': int(s.get('pricePrecision', 0)),
                        'quantity_precision': int(s.get('quantityPrecision', 0))
                    }
        except Exception as e:
            self.logger.error(f"정밀도 조회 오류: {e}")
        return {'price_precision': 0, 'quantity_precision': 0}

    def get_position_info(self, symbol: str) -> Optional[Dict]:
        """해당 심볼 포지션 단건 조회(없으면 None)"""
        # 키가 없으면 조용히 None 반환
        if not self._has_api_keys():
            self.logger.debug(f"포지션 단건 조회 건너뜀: API 키 없음 ({symbol})")
            return None
        try:
            # 🔥 동기화된 타임스탬프 + recvWindow 적용 (-1021 예방)
            ts = self.get_synced_timestamp()
            rw = self.config.recv_window

            arr = self.client.futures_position_information(symbol=symbol, timestamp=ts, recvWindow=rw)
            if isinstance(arr, list) and arr:
                return arr[0]
        except Exception as e:
            self.logger.error(f"포지션 단건 조회 오류: {e}")
        return None

    def ensure_single_position_mode(self) -> bool:
        """단일 포지션 모드 보장(dualSidePosition=False)"""
        # 키가 없으면 조용히 성공으로 간주(실거래 모드가 아니므로 흐름 유지 목적)
        if not self._has_api_keys():
            self.logger.debug("포지션 모드 확인/변경 건너뜀: API 키 없음")
            return True
        try:
            mode = self.client.futures_get_position_mode()
            is_dual = mode.get('dualSidePosition', False)
            if is_dual:
                try:
                    self.client.futures_change_position_mode(dualSidePosition=False)
                    self.logger.info("포지션 모드 단일(BOTH)로 전환")
                except Exception as e:
                    # 이미 단일 모드거나 변경 불필요 메시지 무시
                    if "No need to change position side" not in str(e):
                        raise
            return True
        except Exception as e:
            self.logger.error(f"포지션 모드 확인/변경 오류: {e}")
            return False

    def _futures_base_url(self) -> str:
        """Futures API base URL 반환"""
        if getattr(self.config, "testnet", False):
            return "https://testnet.binancefuture.com"
        return "https://fapi.binance.com"

    def _format_param_value(self, v):
        """파라미터 값을 Binance API 형식으로 변환"""
        if v is None:
            return ""
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, float):
            # 부동소수점 오차 제거: 먼저 적절한 정밀도로 반올림
            # 일반적으로 Binance는 소수점 8자리까지 허용하지만, 
            # 실제로는 tickSize나 pricePrecision에 맞춰야 함
            # 여기서는 부동소수점 오차를 제거하기 위해 10자리로 반올림 후 포맷팅
            rounded = round(v, 10)
            s = format(rounded, ".10f").rstrip("0").rstrip(".")
            return s if s else "0"
        return str(v)

    def _build_signed_query(self, params: dict):
        """서명된 query string 생성"""
        items = []
        for k, v in (params or {}).items():
            if k is None:
                continue
            ks = str(k)
            if ks == "signature":
                continue
            vs = self._format_param_value(v)
            if vs == "":
                continue
            items.append((ks, vs))

        items.sort(key=lambda x: x[0])
        query_string = urlencode(items, doseq=True)  # quote_plus
        secret = (self.config.secret_key or "").encode("utf-8")
        signature = hmac.new(secret, query_string.encode("utf-8"), hashlib.sha256).hexdigest()
        return query_string, signature

    def _post_futures_signed(self, path: str, params: dict):
        """서명된 POST 요청 전송"""
        params = dict(params or {})
        params.setdefault("timestamp", self.get_synced_timestamp())
        params.setdefault("recvWindow", getattr(self.config, "recv_window", 5000))

        qs, sig = self._build_signed_query(params)
        url = f"{self._futures_base_url()}{path}?{qs}&signature={sig}"
        headers = {"X-MBX-APIKEY": self.config.api_key}

        if self._should_log_debug():
            self.logger.debug(f"[FUTURES_SIGNED_POST] path={path} qs={qs} sig={sig[:16]}...")

        try:
            resp = requests.post(url, headers=headers, timeout=getattr(self.config, "timeout", 30))
            try:
                return resp.json()
            except Exception:
                return {"code": resp.status_code, "msg": resp.text}
        except Exception as e:
            return {"code": -1, "msg": f"REQUEST_FAILED: {e}"}

    def place_futures_order(
        self,
        symbol: str,
        side: str,
        order_type: str = 'MARKET',
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        stop_price: Optional[float] = None,
        time_in_force: str = 'GTC',
        reduce_only: Optional[bool] = None,
        close_position: Optional[bool] = None,
        working_type: Optional[str] = None,
        position_side: Optional[str] = None,  # 'LONG' or 'SHORT' (헤지 모드용)
    ) -> Dict:
        """선물 주문 편의 메서드 (Binance API 공식 규칙 준수)"""

        # --- API key 검사 ---
        if not self._has_api_keys():
            self.logger.debug(f"선물 주문 건너뜀: API 키 없음 ({symbol} {side} {order_type} {quantity})")
            return {'status': 'SKIPPED', 'error': 'NO_API_KEYS'}

        try:
            # Normalize order_type
            ot = order_type.strip().upper()
            alias_map = {
                'STOP': 'STOP_MARKET',
                'TAKE_PROFIT': 'TAKE_PROFIT_MARKET',
                'TP_MARKET': 'TAKE_PROFIT_MARKET',
                'SL_MARKET': 'STOP_MARKET',
            }
            order_type = alias_map.get(ot, ot)

            # 조건부 주문 타입 확인 (라우팅 결정용)
            conditional_order_types = ['STOP', 'STOP_MARKET', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'TRAILING_STOP_MARKET']
            is_conditional_order = order_type in conditional_order_types

            params: Dict[str, Any] = {
                'symbol': symbol,
                'side': side,
                'type': order_type,
            }

            # --- closePosition 검증 ---
            if close_position:
                if order_type not in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                    self.logger.error(f"[{symbol}] ❌ closePosition=True는 STOP_MARKET 또는 TAKE_PROFIT_MARKET에서만 사용 가능 (현재: {order_type})")
                    return {'status': 'ERROR', 'error': 'INVALID_ORDER_TYPE_FOR_CLOSE_POSITION'}
            
            # --- reduceOnly vs closePosition conflict ---
            if reduce_only and close_position:
                self.logger.error(f"[{symbol}] ❌ closePosition=True와 reduceOnly는 동시 사용 불가 (Binance API 규칙)")
                return {'status': 'ERROR', 'error': 'REDUCE_ONLY_AND_CLOSE_POSITION_CONFLICT'}

            # --- quantity 처리 (일반 주문만, 조건부 주문은 Algo Order API에서 별도 처리) ---
            if not is_conditional_order and not close_position:
                if quantity is None:
                    self.logger.error(f"[{symbol}] ❌ quantity가 None입니다 (closePosition=False). 수량은 필수입니다.")
                    return {'status': 'ERROR', 'error': 'QUANTITY_REQUIRED'}

                # stepSize/minQty/precision 보정
                filters = self.get_symbol_filters(symbol) or {}
                step_size = float(filters.get('stepSize') or 0)
                min_qty = float(filters.get('minQty') or 0)
                qty = float(quantity)

                if step_size > 0:
                    qty = math.ceil(qty / step_size) * step_size
                qty = max(qty, min_qty)

                # precision
                info = self.client.futures_exchange_info()
                sym_info = next((s for s in info.get('symbols', []) if s['symbol'] == symbol), None)
                if sym_info and isinstance(sym_info.get('quantityPrecision'), int):
                    prec = sym_info['quantityPrecision']
                    qty = float(format(qty, f'.{prec}f'))

                params['quantity'] = str(qty)

            # --- closePosition 키 추가 ---
            # 🔥 Binance API 규칙: closePosition은 불리언 값이어야 함 (문자열 'true'가 아님)
            if close_position:
                params['closePosition'] = True

            # --- reduceOnly 키 추가 (closePosition과 충돌하지 않음) ---
            if reduce_only is not None:
                params['reduceOnly'] = 'true' if reduce_only else 'false'

            # --- stopPrice / workingType ---
            if stop_price is not None:
                params['stopPrice'] = str(stop_price)
            if working_type:
                params['workingType'] = working_type

            # --- positionSide (헤지 모드용) ---
            if position_side:
                params['positionSide'] = position_side

            # --- price/timeInForce ---
            if price is not None:
                params['price'] = str(price)
                params['timeInForce'] = time_in_force
            elif order_type not in ['MARKET', 'STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                params['timeInForce'] = time_in_force

            # --- 동기화된 타임스탬프 추가 ---
            params['timestamp'] = self.get_synced_timestamp()

            # --- 실제 주문 실행 ---
            # 🔥 2025-12-09 이후 Binance 정책 변경: 조건부 주문은 /fapi/v1/algoOrder로 전송 필수
            conditional_order_types = ['STOP', 'STOP_MARKET', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET', 'TRAILING_STOP_MARKET']
            
            if is_conditional_order:
                if stop_price is None:
                    self.logger.error(f"[{symbol}] ❌ 조건부 주문({order_type})에는 stop_price(=triggerPrice)가 필수입니다.")
                    return {'status': 'ERROR', 'error': 'TRIGGER_PRICE_REQUIRED'}

                algo_params = {
                    "symbol": symbol,
                    "side": side,
                    "type": order_type,
                    "algoType": "CONDITIONAL",
                    "triggerPrice": stop_price,
                }

                if working_type:
                    algo_params["workingType"] = working_type
                if position_side:
                    algo_params["positionSide"] = position_side

                if close_position:
                    algo_params["closePosition"] = True
                else:
                    if quantity is None:
                        self.logger.error(f"[{symbol}] ❌ 조건부 주문({order_type}) closePosition=False 인 경우 quantity가 필수입니다.")
                        return {'status': 'ERROR', 'error': 'QUANTITY_REQUIRED'}
                    algo_params["quantity"] = float(quantity)

                if reduce_only is not None and not close_position:
                    algo_params["reduceOnly"] = bool(reduce_only)

                result = self._post_futures_signed("/fapi/v1/algoOrder", algo_params)

                if isinstance(result, dict) and ("code" in result) and int(result.get("code", 0)) != 0:
                    self.logger.error(f"[{symbol}] ❌ AlgoOrder 실패: {result}")
                    return {'status': 'ERROR', 'error': f"APIError(code={result.get('code')}): {result.get('msg')}"}

                self.logger.info(f"[{symbol}] ✅ AlgoOrder 생성 성공: {result}")
                
                # Algo Order 응답 파싱 (algoId → order_id 매핑)
                algo_id = result.get('algoId') or result.get('orderId')
                if algo_id:
                    return {
                        'status': 'PENDING',  # Algo Order는 생성 시점에 PENDING
                        'order_id': algo_id,  # algoId를 order_id로 매핑
                        'order': result,  # 전체 응답 보존
                        'avg_price': 0.0,
                        'executed_qty': 0.0,
                        'cum_quote': 0.0,
                    }
                else:
                    return {'status': 'ERROR', 'error': f"AlgoOrder 생성 실패: {result}"}
            else:
                # 일반 주문: 기존 방식 사용 (POST /fapi/v1/order)
                result = self.client.futures_create_order(**params)

                # 응답 파싱 (일반 주문 응답 처리)
                status = result.get('status', 'NEW')
                avg_price = float(result.get('avgPrice') or 0.0)
                executed_qty = float(result.get('executedQty') or 0.0)
                cum_quote = float(result.get('cumQuote') or 0.0)

                # 최종 거래 파라미터 로깅
                if not close_position and quantity is not None and avg_price > 0:
                    final_notional = executed_qty * avg_price
                    self.logger.info(f"[{symbol}] ✅ 최종 거래 파라미터: 수량={executed_qty}, 가격={avg_price}, 거래금액={final_notional:.2f} USDT")

                return {
                    'status': 'FILLED' if status == 'FILLED' else 'PENDING',
                    'order_id': result.get('orderId'),
                    'order': result,  # 전체 응답 보존 (호환성)
                    'avg_price': avg_price,
                    'executed_qty': executed_qty,
                    'cum_quote': cum_quote,
                }

        except BinanceAPIException as e:
            self.logger.error(f"바이낸스 API 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}

        except BinanceOrderException as e:
            self.logger.error(f"주문 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}

        except Exception as e:
            self.logger.error(f"주문 실행 오류: {e}")
            return {'status': 'ERROR', 'error': str(e)}

    def is_order_success(self, order_result: Optional[Dict[str, Any]]) -> bool:
        """바이낸스 주문 결과를 기반으로 성공 여부를 통일된 기준으로 판별"""
        try:
            if not order_result:
                return False
            
            # Algo Order 응답 처리 (algoId 또는 order_id가 있으면 성공)
            order_id = order_result.get('order_id') or order_result.get('algoId')
            if order_id:
                # Algo Order는 생성 시점에 PENDING 상태이고 executed_qty=0이므로
                # order_id/algoId가 있으면 성공으로 판단
                return True
            
            # 일반 주문 응답 처리
            status = str(order_result.get('status', '')).upper()
            executed_qty = float(order_result.get('executed_qty', 0) or 0.0)
            
            if status == 'SUCCESS':
                return True
            if status == 'FILLED':
                return True
            if status in {'PARTIALLY_FILLED', 'NEW', 'PENDING'} and executed_qty > 0:
                return True
            
            # PENDING 상태이고 order_id가 있으면 성공 (Algo Order 대응)
            if status == 'PENDING' and order_id:
                return True
                
            return False
        except Exception:
            return False

    def place_tp_sl_orders(
        self,
        symbol: str,
        position_side: str,  # 'LONG' or 'SHORT'
        take_profit: float,
        stop_loss: float,
        quantity: Optional[float] = None,
        price_precision: Optional[int] = None,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """안전장치용 TP/SL 오더 발주(TAKE_PROFIT_MARKET, STOP_MARKET)"""
        # 🔥 디버깅: 메서드 호출 확인 (log_event 사용)
        self.log_event('order', f"[{symbol}] 🔍 place_tp_sl_orders() 호출됨 - TP={take_profit}, SL={stop_loss}, position_side={position_side}")
        
        # 키가 없으면 조용히 (None, None) 반환
        if not self._has_api_keys():
            self.log_event('order', f"TP/SL 주문 건너뜀: API 키 없음 ({symbol} {position_side})", level='DEBUG')
            return None, None
        try:
            # 🔥 price_precision이 없으면 자동으로 조회
            if price_precision is None:
                try:
                    exchange_info = self.client.futures_exchange_info()
                    symbol_info = next((s for s in exchange_info.get('symbols', []) if s['symbol'] == symbol), None)
                    if symbol_info and 'pricePrecision' in symbol_info:
                        price_precision = symbol_info['pricePrecision']
                        self.log_event('order', f"[{symbol}] 🔧 자동 price_precision 조회: {price_precision}")
                except Exception as e:
                    self.log_event('order', f"[{symbol}] price_precision 자동 조회 실패: {e}", level='WARNING')
                    price_precision = 6  # 기본값

            # 🔥 가격 정밀도 적용 (tickSize 우선, 없으면 pricePrecision 사용)
            filters = self.get_symbol_filters(symbol) or {}
            tick_size = float(filters.get('tickSize') or 0)
            
            if tick_size > 0:
                # tickSize에 맞춰 조정 (가장 가까운 tickSize 배수로)
                tp_price = round(take_profit / tick_size) * tick_size
                sl_price = round(stop_loss / tick_size) * tick_size
                
                # 🔥 스냅 후 가격이 0 이하인지 검증 (저가 코인 대응)
                if tp_price <= 0 or sl_price <= 0:
                    self.log_event('order', f"[{symbol}] ❌ tickSize 스냅 후 가격이 0 이하: TP={tp_price}, SL={sl_price}, 원본 TP={take_profit}, SL={stop_loss}, tickSize={tick_size}", level='ERROR')
                    # 원본 가격을 다시 사용하되, 최소값 보장
                    tp_price = max(take_profit, tick_size) if take_profit > 0 else tick_size
                    sl_price = max(stop_loss, tick_size) if stop_loss > 0 else tick_size
                    # 다시 스냅 적용
                    tp_price = round(tp_price / tick_size) * tick_size
                    sl_price = round(sl_price / tick_size) * tick_size
                
                self.log_event('order', f"[{symbol}] 🔧 tickSize 적용: TP {take_profit} → {tp_price}, SL {stop_loss} → {sl_price} (tickSize={tick_size})")
            elif price_precision is not None and price_precision > 0:
                # tickSize가 없으면 pricePrecision 사용
                tp_price = round(take_profit, price_precision)
                sl_price = round(stop_loss, price_precision)
                
                # 🔥 반올림 후 가격이 0 이하인지 검증
                if tp_price <= 0 or sl_price <= 0:
                    self.log_event('order', f"[{symbol}] ❌ precision 반올림 후 가격이 0 이하: TP={tp_price}, SL={sl_price}, 원본 TP={take_profit}, SL={stop_loss}, precision={price_precision}", level='ERROR')
                    # 원본 가격을 최소값으로 보장
                    min_price = 10 ** (-price_precision)  # 최소 단위
                    tp_price = max(take_profit, min_price) if take_profit > 0 else min_price
                    sl_price = max(stop_loss, min_price) if stop_loss > 0 else min_price
                    tp_price = round(tp_price, price_precision)
                    sl_price = round(sl_price, price_precision)
                
                self.log_event('order', f"[{symbol}] 🔧 가격 정밀도 적용: TP {take_profit} → {tp_price}, SL {stop_loss} → {sl_price} (precision={price_precision})")
            else:
                tp_price = take_profit
                sl_price = stop_loss
                
                # 🔥 최소값 검증 (스냅 없이도 0 이하는 방지)
                if tp_price <= 0 or sl_price <= 0:
                    self.log_event('order', f"[{symbol}] ❌ TP/SL 가격이 0 이하: TP={tp_price}, SL={sl_price}", level='ERROR')
                    tp_price = max(tp_price, 0.0001) if tp_price > 0 else 0.0001
                    sl_price = max(sl_price, 0.0001) if sl_price > 0 else 0.0001

            close_side = 'SELL' if position_side == 'LONG' else 'BUY'

            # 포지션 모드 확인 (헤지 모드일 때는 positionSide 필요)
            try:
                mode = self.client.futures_get_position_mode()
                is_dual = mode.get('dualSidePosition', False)
            except Exception:
                is_dual = False  # 기본값: 단일 포지션 모드

            tp_params = {
                'symbol': symbol,
                'side': close_side,
                'order_type': 'TAKE_PROFIT_MARKET',
                'stop_price': tp_price,
                'close_position': True,  # 🔥 closePosition=True 사용 (reduceOnly 제거)
                'working_type': 'MARK_PRICE',
            }
            sl_params = {
                'symbol': symbol,
                'side': close_side,
                'order_type': 'STOP_MARKET',
                'stop_price': sl_price,
                'close_position': True,  # 🔥 closePosition=True 사용 (reduceOnly 제거)
                'working_type': 'MARK_PRICE',
            }
            
            # 헤지 모드일 때 positionSide 추가
            if is_dual:
                tp_params['position_side'] = position_side
                sl_params['position_side'] = position_side
                self.log_event('order', f"[{symbol}] 🔧 헤지 모드 감지: positionSide={position_side} 추가")
            else:
                self.log_event('order', f"[{symbol}] 🔧 단일 포지션 모드: positionSide 미사용")
            # 🔥 closePosition=True 사용 시 수량 미전송 (전량 청산)
            # Binance API 규칙: closePosition=True일 때 quantity 파라미터를 전송하면 안 됨
            # 따라서 quantity 자동 조회 로직도 불필요함
            self.log_event('order', f"[{symbol}] 🔧 TP/SL closePosition=True 사용 (수량 미전송, Binance API 규칙 준수)")

            # 🔥 1단계: 기존 TP/SL 주문 확인 및 취소 (-4130 오류 방지)
            try:
                # 일반 주문 조회
                open_orders = self.get_open_orders(symbol=symbol)
                # Algo Order 조회
                open_algo_orders = self.get_open_algo_orders(symbol=symbol)
                
                # 🔥 디버깅: 조회 결과 로깅
                self.log_event('order', f"[{symbol}] 🔍 주문 조회 결과 - 일반 주문: {len(open_orders)}개, Algo Order: {len(open_algo_orders)}개")
                
                # Algo Order 상세 정보 로깅 (타입 확인용)
                if open_algo_orders:
                    for idx, algo_order in enumerate(open_algo_orders):
                        # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                        order_type_raw = algo_order.get('orderType')
                        type_raw = algo_order.get('type')
                        algo_type = order_type_raw or type_raw or 'N/A'
                        algo_id = algo_order.get('algoId') or algo_order.get('orderId', 'N/A')
                        # 🔥 실제 필드 값 확인을 위한 상세 로깅
                        self.log_event('order', f"[{symbol}] 🔍 Algo Order #{idx+1}: orderType(원본)={order_type_raw}, type(원본)={type_raw}, algoId={algo_id}")
                        self.log_event('order', f"[{symbol}] 🔍 Algo Order #{idx+1} 전체데이터: {algo_order}")
                
                # TP/SL 주문 필터링 (일반 주문)
                tp_orders_to_cancel = [o for o in open_orders if o.get('type') in ('TAKE_PROFIT', 'TAKE_PROFIT_MARKET')]
                sl_orders_to_cancel = [o for o in open_orders if o.get('type') in ('STOP', 'STOP_MARKET')]
                
                # 🔥 Algo Order에서 TP/SL 필터링 (orderType 필드 사용)
                for algo_order in open_algo_orders:
                    # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                    algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                    if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT'):
                        tp_orders_to_cancel.append(algo_order)
                    elif algo_type in ('STOP_MARKET', 'STOP'):
                        sl_orders_to_cancel.append(algo_order)
                
                # 기존 TP/SL 주문 취소
                if tp_orders_to_cancel or sl_orders_to_cancel:
                    self.log_event('order', f"[{symbol}] 🔧 기존 TP/SL 주문 취소 시작 (TP: {len(tp_orders_to_cancel)}개, SL: {len(sl_orders_to_cancel)}개)")
                    
                    # 일반 주문 취소 (Algo Order 제외)
                    for order in tp_orders_to_cancel + sl_orders_to_cancel:
                        # Algo Order는 별도 처리하므로 제외 (algoId가 있으면 Algo Order)
                        if 'algoId' in order:
                            continue
                        if 'orderId' in order:
                            try:
                                order_id = order.get('orderId')
                                self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
                                self.log_event('order', f"[{symbol}] ✅ 기존 TP/SL 주문 취소 완료: {order_id} ({order.get('type')})")
                            except Exception as e:
                                # -2011: Order does not exist (이미 취소됨)
                                if '-2011' not in str(e):
                                    self.log_event('order', f"[{symbol}] ⚠️ 기존 TP/SL 주문 취소 실패: {e}", level='WARNING')
                    
                    # Algo Order 취소 (별도 처리)
                    for algo_order in open_algo_orders:
                        # 🔥 Binance Algo Order API는 'type' 대신 'orderType' 필드 사용
                        algo_type = (algo_order.get('orderType') or algo_order.get('type', '')).upper()
                        if algo_type in ('TAKE_PROFIT_MARKET', 'TAKE_PROFIT', 'STOP_MARKET', 'STOP'):
                            algo_id = algo_order.get('algoId') or algo_order.get('orderId')
                            if algo_id:
                                try:
                                    # DELETE /fapi/v1/algoOrder
                                    params = {
                                        'symbol': symbol,
                                        'algoId': algo_id,
                                        'timestamp': self.get_synced_timestamp(),
                                        'recvWindow': self.config.recv_window
                                    }
                                    qs, sig = self._build_signed_query(params)
                                    url = f"{self._futures_base_url()}/fapi/v1/algoOrder?{qs}&signature={sig}"
                                    headers = {"X-MBX-APIKEY": self.config.api_key}
                                    import requests
                                    resp = requests.delete(url, headers=headers, timeout=self.config.timeout)
                                    result = resp.json()
                                    if isinstance(result, dict) and result.get('code') == 200:
                                        self.log_event('order', f"[{symbol}] ✅ 기존 Algo Order 취소 완료: {algo_id} ({algo_type})")
                                    else:
                                        # -2011: Order does not exist (이미 취소됨)
                                        if result.get('code') != -2011:
                                            self.log_event('order', f"[{symbol}] ⚠️ 기존 Algo Order 취소 실패: {result}", level='WARNING')
                                except Exception as e:
                                    # -2011: Order does not exist (이미 취소됨)
                                    if '-2011' not in str(e):
                                        self.log_event('order', f"[{symbol}] ⚠️ 기존 Algo Order 취소 실패: {e}", level='WARNING')
                    
                    # 취소 완료 대기 (타이밍 이슈 방지)
                    import time
                    time.sleep(0.5)
                    self.log_event('order', f"[{symbol}] ✅ 기존 TP/SL 주문 취소 완료")
                else:
                    self.log_event('order', f"[{symbol}] 기존 TP/SL 주문 없음", level='DEBUG')
            except Exception as e:
                self.log_event('order', f"[{symbol}] ⚠️ 기존 TP/SL 주문 확인/취소 중 오류 (계속 진행): {e}", level='WARNING')
            
            # 🔥 2단계: TP 가격 방향 및 거리 검증 (-2021 오류 방지)
            try:
                current_price = self.get_current_price(symbol)
                if current_price and current_price > 0:
                    min_distance = max(tick_size / current_price if tick_size > 0 else 0.001, 0.001)  # 최소 0.1%
                    
                    if position_side == 'LONG':
                        # LONG: TP는 현재가보다 높아야 함
                        if tp_price <= current_price:
                            # 🔥 TP가 현재가보다 낮거나 같으면 즉시 트리거됨 (방향 검증)
                            self.log_event('order', f"[{symbol}] ⚠️ TP 가격이 현재가보다 낮거나 같음: TP={tp_price}, 현재가={current_price} (LONG 포지션)", level='WARNING')
                            # TP 가격을 현재가보다 최소 거리만큼 높임
                            tp_price = current_price * (1 + min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                tp_price = round(tp_price / tick_size) * tick_size
                            else:
                                tp_price = round(tp_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 TP 가격 방향 조정: {take_profit} → {tp_price}")
                        else:
                            # 방향은 맞지만 거리가 너무 가까운지 확인
                            tp_distance_pct = abs((tp_price - current_price) / current_price) if current_price > 0 else 0
                            if tp_distance_pct < min_distance:
                                self.log_event('order', f"[{symbol}] ⚠️ TP 가격이 현재가와 너무 가까움: TP={tp_price}, 현재가={current_price}, 거리={tp_distance_pct*100:.4f}%, 최소={min_distance*100:.4f}%", level='WARNING')
                                # TP 가격을 현재가보다 최소 거리만큼 떨어뜨림
                                tp_price = current_price * (1 + min_distance)
                                # tickSize 스냅 재적용
                                if tick_size > 0:
                                    tp_price = round(tp_price / tick_size) * tick_size
                                else:
                                    tp_price = round(tp_price, price_precision)
                                self.log_event('order', f"[{symbol}] 🔧 TP 가격 거리 조정: {take_profit} → {tp_price}")
                    else:  # SHORT
                        # SHORT: TP는 현재가보다 낮아야 함
                        if tp_price >= current_price:
                            # 🔥 TP가 현재가보다 높거나 같으면 즉시 트리거됨 (방향 검증)
                            self.log_event('order', f"[{symbol}] ⚠️ TP 가격이 현재가보다 높거나 같음: TP={tp_price}, 현재가={current_price} (SHORT 포지션)", level='WARNING')
                            # TP 가격을 현재가보다 최소 거리만큼 낮춤
                            tp_price = current_price * (1 - min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                tp_price = round(tp_price / tick_size) * tick_size
                            else:
                                tp_price = round(tp_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 TP 가격 방향 조정: {take_profit} → {tp_price}")
                        else:
                            # 방향은 맞지만 거리가 너무 가까운지 확인
                            tp_distance_pct = abs((tp_price - current_price) / current_price) if current_price > 0 else 0
                            if tp_distance_pct < min_distance:
                                self.log_event('order', f"[{symbol}] ⚠️ TP 가격이 현재가와 너무 가까움: TP={tp_price}, 현재가={current_price}, 거리={tp_distance_pct*100:.4f}%, 최소={min_distance*100:.4f}%", level='WARNING')
                                # TP 가격을 현재가보다 최소 거리만큼 떨어뜨림
                                tp_price = current_price * (1 - min_distance)
                                # tickSize 스냅 재적용
                                if tick_size > 0:
                                    tp_price = round(tp_price / tick_size) * tick_size
                                else:
                                    tp_price = round(tp_price, price_precision)
                                self.log_event('order', f"[{symbol}] 🔧 TP 가격 거리 조정: {take_profit} → {tp_price}")
                    
                    # 조정된 TP 가격으로 tp_params 업데이트
                    tp_params['stop_price'] = tp_price
            except Exception as e:
                self.log_event('order', f"[{symbol}] ⚠️ TP 가격 거리 검증 중 오류 (계속 진행): {e}", level='WARNING')

            # 🔥 3단계: SL 가격과 현재 가격 거리 검증 (-2021 오류 방지)
            try:
                current_price = self.get_current_price(symbol)
                if current_price and current_price > 0:
                    if position_side == 'LONG':
                        # LONG: SL은 현재가보다 낮아야 함
                        sl_distance_pct = abs((sl_price - current_price) / current_price) if current_price > 0 else 0
                        min_distance = max(tick_size / current_price if tick_size > 0 else 0.001, 0.001)  # 최소 0.1%
                        
                        if sl_price >= current_price:
                            # SL이 현재가보다 높거나 같으면 즉시 트리거됨
                            self.log_event('order', f"[{symbol}] ⚠️ SL 가격이 현재가보다 높거나 같음: SL={sl_price}, 현재가={current_price}", level='WARNING')
                            # SL 가격을 현재가보다 최소 거리만큼 낮춤
                            sl_price = current_price * (1 - min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                sl_price = round(sl_price / tick_size) * tick_size
                            else:
                                sl_price = round(sl_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 SL 가격 조정: {stop_loss} → {sl_price}")
                        elif sl_distance_pct < min_distance:
                            # SL이 현재가와 너무 가까움
                            self.log_event('order', f"[{symbol}] ⚠️ SL 가격이 현재가와 너무 가까움: SL={sl_price}, 현재가={current_price}, 거리={sl_distance_pct*100:.4f}%, 최소={min_distance*100:.4f}%", level='WARNING')
                            # SL 가격을 현재가보다 최소 거리만큼 낮춤
                            sl_price = current_price * (1 - min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                sl_price = round(sl_price / tick_size) * tick_size
                            else:
                                sl_price = round(sl_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 SL 가격 조정: {stop_loss} → {sl_price}")
                    else:  # SHORT
                        # SHORT: SL은 현재가보다 높아야 함
                        sl_distance_pct = abs((sl_price - current_price) / current_price) if current_price > 0 else 0
                        min_distance = max(tick_size / current_price if tick_size > 0 else 0.001, 0.001)  # 최소 0.1%
                        
                        if sl_price <= current_price:
                            # SL이 현재가보다 낮거나 같으면 즉시 트리거됨
                            self.log_event('order', f"[{symbol}] ⚠️ SL 가격이 현재가보다 낮거나 같음: SL={sl_price}, 현재가={current_price}", level='WARNING')
                            # SL 가격을 현재가보다 최소 거리만큼 높임
                            sl_price = current_price * (1 + min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                sl_price = round(sl_price / tick_size) * tick_size
                            else:
                                sl_price = round(sl_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 SL 가격 조정: {stop_loss} → {sl_price}")
                        elif sl_distance_pct < min_distance:
                            # SL이 현재가와 너무 가까움
                            self.log_event('order', f"[{symbol}] ⚠️ SL 가격이 현재가와 너무 가까움: SL={sl_price}, 현재가={current_price}, 거리={sl_distance_pct*100:.4f}%, 최소={min_distance*100:.4f}%", level='WARNING')
                            # SL 가격을 현재가보다 최소 거리만큼 높임
                            sl_price = current_price * (1 + min_distance)
                            # tickSize 스냅 재적용
                            if tick_size > 0:
                                sl_price = round(sl_price / tick_size) * tick_size
                            else:
                                sl_price = round(sl_price, price_precision)
                            self.log_event('order', f"[{symbol}] 🔧 SL 가격 조정: {stop_loss} → {sl_price}")
                    
                    # 조정된 SL 가격으로 sl_params 업데이트
                    sl_params['stop_price'] = sl_price
            except Exception as e:
                self.log_event('order', f"[{symbol}] ⚠️ SL 가격 거리 검증 중 오류 (계속 진행): {e}", level='WARNING')

            tp_order = self.place_futures_order(**tp_params)
            sl_order = self.place_futures_order(**sl_params)

            # 🔥 TP/SL 설정 결과 로깅
            tp_success = self.is_order_success(tp_order)
            sl_success = self.is_order_success(sl_order)

            if tp_success and sl_success:
                # orderId 추출 (Algo Order는 algoId 사용)
                tp_order_id = tp_order.get('order_id') or (tp_order.get('order', {}) or {}).get('orderId') or (tp_order.get('order', {}) or {}).get('algoId')
                sl_order_id = sl_order.get('order_id') or (sl_order.get('order', {}) or {}).get('orderId') or (sl_order.get('order', {}) or {}).get('algoId')
                self.log_event('order', f"[{symbol}] ✅ TP/SL 설정 완료: TP={tp_price:.6f}, SL={sl_price:.6f}")
                self.log_event('order', f"[{symbol}]   - TP Order ID: {tp_order_id or 'N/A'}")
                self.log_event('order', f"[{symbol}]   - SL Order ID: {sl_order_id or 'N/A'}")
            elif tp_success and not sl_success:
                self.log_event('order', f"[{symbol}] ⚠️ TP만 설정됨: TP={tp_price:.6f}, SL 실패", level='WARNING')
                self.log_event('order', f"[{symbol}]   - SL 오류: {sl_order.get('error', 'Unknown')}", level='WARNING')
            elif not tp_success and sl_success:
                self.log_event('order', f"[{symbol}] ⚠️ SL만 설정됨: SL={sl_price:.6f}, TP 실패", level='WARNING')
                self.log_event('order', f"[{symbol}]   - TP 오류: {tp_order.get('error', 'Unknown')}", level='WARNING')
            else:
                self.log_event('order', f"[{symbol}] ❌ TP/SL 설정 실패", level='ERROR')
                self.log_event('order', f"[{symbol}]   - TP 오류: {tp_order.get('error', 'Unknown') if tp_order else 'None'}", level='ERROR')
                self.log_event('order', f"[{symbol}]   - SL 오류: {sl_order.get('error', 'Unknown') if sl_order else 'None'}", level='ERROR')

            return tp_order, sl_order
        except Exception as e:
            self.log_event('order', f"[{symbol}] ❌ TP/SL 주문 발주 예외: {e}", level='ERROR')
            import traceback
            self.log_event('order', f"[{symbol}] 상세 오류: {traceback.format_exc()}", level='ERROR')
            return None, None

    def get_order_status(self, symbol: str, order_id: int) -> Dict:
        """주문 상태 조회"""
        # 키가 없으면 조용히 빈 값 반환
        if not self._has_api_keys():
            self.logger.debug(f"주문 상태 조회 건너뜀: API 키 없음 ({symbol}, {order_id})")
            return {}
        try:
            order = self.client.futures_get_order(
                symbol=symbol,
                orderId=order_id
            )

            return {
                'order_id': order['orderId'],
                'symbol': order['symbol'],
                'side': order['side'],
                'type': order['type'],
                'status': order['status'],
                'price': float(order['price']),
                'quantity': float(order['origQty']),
                'executed_qty': float(order['executedQty']),
                'avg_price': float(order['avgPrice']) if order['avgPrice'] else 0.0,
                'time': order['time'],
                'update_time': order['updateTime']
            }

        except Exception as e:
            self.logger.error(f"주문 상태 조회 오류: {e}")
            return {}

    def get_trade_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """거래 내역 조회"""
        # 키가 없으면 조용히 빈 리스트 반환
        if not self._has_api_keys():
            self.logger.debug(f"거래 내역 조회 건너뜀: API 키 없음 ({symbol})")
            return []
        try:
            trades = self.client.futures_account_trades(symbol=symbol)

            trade_history = []
            for trade in trades[-limit:]:  # 최근 거래만
                trade_history.append({
                    'id': trade['id'],
                    'order_id': trade.get('orderId'),
                    'symbol': trade['symbol'],
                    'side': trade['side'],
                    'price': float(trade['price']),
                    'quantity': float(trade['qty']),
                    'quote_qty': float(trade['quoteQty']),
                    'commission': float(trade['commission']),
                    'commission_asset': trade.get('commissionAsset', ''),
                    'time': trade['time']
                })

            return trade_history

        except Exception as e:
            if 'Invalid symbol' in str(e):
                sym = symbol if 'symbol' in locals() else ''
                if sym and sym not in self._recent_trade_invalid_symbol_warned:
                    self.logger.warning(f"거래 내역 조회 Invalid symbol - 최초 1회 경고: {sym}")
                    self._recent_trade_invalid_symbol_warned.add(sym)
                else:
                    self.logger.debug(f"거래 내역 조회 Invalid symbol (억제됨): {sym}")
            else:
                self.logger.error(f"거래 내역 조회 오류: {e}")
            return []

    def start_websocket_stream(self, symbols: List[str]):
        """WebSocket 스트림 시작"""
        try:
            # 매니저 스레드 상태는 내부에서 처리되므로 여기서는 초기화 진입만 수행
            if not symbols:
                self.logger.warning("WebSocket 시작 요청에 심볼이 비어있습니다.")
                return

            # 최신 방식: 개별 심볼 구독 or 일괄 초기화
            # initialize_market_data가 병렬 처리 및 안정화 로직을 포함하므로 우선 사용
            try:
                initialized = self.websocket_manager.initialize_market_data(symbols)
                self.logger.info(f"WebSocket 초기화 완료: {initialized}")
            except AttributeError:
                # 구버전 호환: 개별 구독으로 대체
                ok_count = 0
                for s in symbols:
                    if self.websocket_manager.subscribe_symbol(s):
                        ok_count += 1
                self.logger.info(f"WebSocket 구독 완료: {ok_count}/{len(symbols)}")

        except Exception as e:
            self.logger.error(f"WebSocket 스트림 시작 오류: {e}")

    def stop_websocket_stream(self):
        """WebSocket 스트림 중지"""
        try:
            self.websocket_manager.stop()

            self.logger.info("WebSocket 스트림 중지")

        except Exception as e:
            self.logger.error(f"WebSocket 스트림 중지 오류: {e}")

    def add_price_callback(self, callback):
        """가격 콜백 함수 추가"""
        self.price_callbacks.append(callback)

    def add_kline_callback(self, callback):
        """K라인 콜백 함수 추가"""
        self.kline_callbacks.append(callback)

    def add_trade_callback(self, callback):
        """거래 콜백 함수 추가"""
        self.trade_callbacks.append(callback)

    def remove_price_callback(self, callback):
        """가격 콜백 함수 제거"""
        if callback in self.price_callbacks:
            self.price_callbacks.remove(callback)

    def remove_kline_callback(self, callback):
        """K라인 콜백 함수 제거"""
        if callback in self.kline_callbacks:
            self.kline_callbacks.remove(callback)

    def remove_trade_callback(self, callback):
        """거래 콜백 함수 제거"""
        if callback in self.trade_callbacks:
            self.trade_callbacks.remove(callback)

    def get_24hr_ticker(self, symbol: str) -> Optional[Dict]:
        """24시간 티커 통계 조회"""
        try:
            # 🔥 방어적 심볼 정규화 적용
            normalized_symbol = self._normalize_symbol_safe(symbol)
            if normalized_symbol != symbol:
                self.logger.debug(f"심볼 정규화: {symbol} -> {normalized_symbol}")

            # 🔥 올바른 메서드명 사용
            ticker = self.client.futures_ticker(symbol=normalized_symbol)
            return ticker
        except Exception as e:
            self.log_event('system', f"24시간 티커 조회 실패 ({symbol}): {e}", level='ERROR')
            return None

    def get_exchange_info(self) -> Dict:
        """거래소 정보 조회 (PERPETUAL 계약만 필터링)"""
        try:
            exchange_info = self.client.futures_exchange_info()

            # PERPETUAL 계약만 필터링
            filtered_symbols = []
            for symbol in exchange_info['symbols']:
                if (symbol['status'] == 'TRADING' and
                    symbol.get('contractType') == 'PERPETUAL'):
                    filtered_symbols.append({
                        'symbol': symbol['symbol'],
                        'status': symbol['status'],
                        'base_asset': symbol['baseAsset'],
                        'quote_asset': symbol['quoteAsset'],
                        'price_precision': symbol['pricePrecision'],
                        'quantity_precision': symbol['quantityPrecision'],
                        'contract_type': symbol.get('contractType', 'UNKNOWN')
                    })

            self.logger.info(f"PERPETUAL 계약 필터링 완료: {len(filtered_symbols)}개 심볼")

            return {
                'timezone': exchange_info['timezone'],
                'server_time': exchange_info['serverTime'],
                'symbols': filtered_symbols
            }

        except Exception as e:
            self.logger.error(f"거래소 정보 조회 오류: {e}")
            return {}

    def get_24h_ticker(self, symbol: str) -> Optional[Dict]:
        """개별 심볼 24시간 티커 데이터 조회"""
        try:
            ticker = self.client.futures_ticker(symbol=symbol)
            return ticker
        except Exception as e:
            self.logger.error(f"{symbol} 24h 티커 조회 오류: {e}")
            return None

    def get_futures_ticker(self) -> List[Dict]:
        """선물 티커 정보 조회 (코인 선택용)"""
        try:
            tickers = self.client.futures_ticker()
            if isinstance(tickers, dict):
                return [tickers]
            return tickers or []
        except Exception as e:
            self.logger.error(f"선물 티커 조회 오류: {e}")
            return []

    # ---- 방어적 심볼 정규화 ----
    def _normalize_symbol_safe(self, symbol: str) -> str:
        """
        방어적 심볼 정규화:
        - 대문자화, 공백 제거, 슬래시 제거
        - USDT/USDC/FDUSD/TUSD/BUSD 접미사가 2번 이상 붙은 경우 1번으로 축소
        - 접미사가 없으면 기본 USDT 부착 (시스템이 USDT 마진 기준일 때)
        - 딜리버리 선물(BTCUSDT_240627) 형태는 원본 유지
        """
        QUOTES = ("USDT", "USDC", "FDUSD", "TUSD", "BUSD")

        # 0) 기본 전처리
        s = str(symbol or "").strip().upper().replace("/", "").replace(" ", "")

        # 1) 딜리버리 선물 심볼은 그대로 통과
        # ex) BTCUSDT_240627, ETHUSDT_240927 등
        if "_" in s:
            return s

        # 2) 접미사가 2회 이상 반복되면 1회로 축소 (while로 여러 번 반복 처리)
        #    ex) DOTUSDTUSDTUSDT -> DOTUSDT
        original_symbol = symbol
        changed = True
        while changed:
            changed = False
            for q in QUOTES:
                duo = q + q
                if s.endswith(duo):
                    s = s[:-len(q)]
                    changed = True

        # 디버그 로깅 (변경된 경우만, 스팸 방지)
        if original_symbol != s:
            # 로그 스팸 방지: 동일 메시지 연속 출력 제한
            log_key = f"symbol_fix_{original_symbol}_{s}"
            if not hasattr(self, '_symbol_fix_logged'):
                self._symbol_fix_logged = set()
            if log_key not in self._symbol_fix_logged:
                self.logger.debug(f"[symbol-fix] {original_symbol} -> {s}")
                self._symbol_fix_logged.add(log_key)

        # 3) 이미 견고한 접미사가 붙어 있으면 그대로 사용
        if any(s.endswith(q) for q in QUOTES):
            return s

        # 4) 접미사가 없으면 기본 USDT 부착
        return s + "USDT"

    # ---- 추가 래퍼: 기존 코드 호환을 위한 헬퍼들 ----
    def get_ticker(self, symbol: str) -> Dict:
        """24시간 티커(선물) 단일 심볼 래퍼. 기존 코드 호환용 키 유지.
        반환 예: {'symbol', 'lastPrice', 'priceChangePercent', 'volume', 'quoteVolume', ...}
        """
        try:
            # 🔥 방어적 심볼 정규화 적용
            normalized_symbol = self._normalize_symbol_safe(symbol)
            if normalized_symbol != symbol:
                self.logger.debug(f"심볼 정규화: {symbol} -> {normalized_symbol}")

            data = self.client.futures_ticker(symbol=normalized_symbol)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            self.logger.error(f"24h 티커 조회 오류({symbol}): {e}")
            return {}

    def get_historical_klines(self, symbol: str, interval: str, start_str: str) -> List[List]:
        """히스토리컬 K라인(선물) 래퍼. '7 days ago UTC' 등 단순 문자열 지원.
        기본은 일봉/분 단위 모두 지원. 반환 포맷은 futures_klines와 동일.
        """
        try:
            # python-binance에 futures_historical_klines가 있는 경우 우선 사용
            if hasattr(self.client, 'futures_historical_klines'):
                try:
                    kl = self.client.futures_historical_klines(symbol=symbol, interval=interval, start_str=start_str)
                    return kl or []
                except Exception:
                    pass
            # 간단 파서: '<N> days ago UTC'
            start_time = None
            try:
                s = (start_str or '').lower().strip()
                if 'day' in s and 'ago' in s:
                    import re
                    m = re.search(r'(\d+)\s*day', s)
                    if m:
                        days = int(m.group(1))
                        from datetime import datetime, timedelta
                        start_dt = datetime.utcnow() - timedelta(days=days)
                        start_time = int(start_dt.timestamp() * 1000)
            except Exception:
                start_time = None
            if start_time is None:
                # 폴백: 7일
                from datetime import datetime, timedelta
                start_time = int((datetime.utcnow() - timedelta(days=7)).timestamp() * 1000)
            klines = self.client.futures_klines(symbol=symbol, interval=interval, startTime=start_time)
            return klines if isinstance(klines, list) else []
        except Exception as e:
            self.logger.error(f"히스토리컬 K라인 조회 오류({symbol}): {e}")
            return []

    def futures_funding_rate(self, symbol: str, limit: int = 1) -> List[Dict]:
        """펀딩비 히스토리 래퍼"""
        try:
            data = self.client.futures_funding_rate(symbol=symbol, limit=limit)
            if isinstance(data, dict):
                return [data]
            return data or []
        except Exception as e:
            self.logger.error(f"펀딩비 조회 오류({symbol}): {e}")
            return []

    def futures_open_interest(self, symbol: str) -> Dict:
        try:
            data = self.client.futures_open_interest(symbol=symbol)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            self.logger.error(f"미체결약정 조회 오류({symbol}): {e}")
            return {}

    def futures_open_interest_hist(self, symbol: str, period: str = '5m', limit: int = 30) -> List[Dict]:
        try:
            data = self.client.futures_open_interest_hist(symbol=symbol, period=period, limit=limit)
            if isinstance(data, dict):
                return [data]
            return data or []
        except Exception as e:
            self.logger.error(f"미체결약정 히스토리 조회 오류({symbol}): {e}")
            return []

    def futures_global_longshort_ratio(self, symbol: str, period: str = '5m', limit: int = 1) -> List[Dict]:
        """글로벌 롱/숏 비율(계정) 조회.
        - python-binance 메서드명이 환경마다 다를 수 있으므로 getattr로 시도 후, 실패 시 REST 폴백.
        """
        try:
            # 1) 다양한 메서드명 시도
            for name in (
                'futures_global_longshort_ratio',
                'futures_global_long_short_account_ratio',
                'futures_global_long_short_position_ratio',
            ):
                fn = getattr(self.client, name, None)
                if callable(fn):
                    try:
                        data = fn(symbol=symbol, period=period, limit=limit)
                        if isinstance(data, dict):
                            return [data]
                        if isinstance(data, list):
                            return data
                        return []
                    except Exception:
                        pass
            # 2) REST 폴백
            import requests as _rq
            url = 'https://fapi.binance.com/futures/data/globalLongShortAccountRatio'
            params = {'symbol': symbol, 'period': period, 'limit': limit}
            r = _rq.get(url, params=params, timeout=10)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, dict):
                    return [js]
                if isinstance(js, list):
                    return js
                return []
            self.logger.error(f"글로벌 롱/숏 REST 오류({symbol}): {r.status_code} {r.text[:120]}")
            return []
        except Exception as e:
            self.logger.error(f"글로벌 롱/숏 비율 조회 오류({symbol}): {e}")
            return []

    def futures_top_longshort_ratio(self, symbol: str, period: str = '5m', limit: int = 1) -> List[Dict]:
        """상위 트레이더 롱/숏 비율 조회.
        - 메서드명 차이/미지원 환경을 대비해 REST 폴백 포함.
        """
        try:
            # 1) 다양한 메서드명 시도
            for name in (
                'futures_top_longshort_ratio',
                'futures_top_long_short_account_ratio',
                'futures_top_long_short_position_ratio',
            ):
                fn = getattr(self.client, name, None)
                if callable(fn):
                    try:
                        data = fn(symbol=symbol, period=period, limit=limit)
                        if isinstance(data, dict):
                            return [data]
                        if isinstance(data, list):
                            return data
                        return []
                    except Exception:
                        pass
            # 2) REST 폴백
            import requests as _rq
            url = 'https://fapi.binance.com/futures/data/topLongShortAccountRatio'
            params = {'symbol': symbol, 'period': period, 'limit': limit}
            r = _rq.get(url, params=params, timeout=10)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, dict):
                    return [js]
                if isinstance(js, list):
                    return js
                return []
            self.logger.error(f"상위 롱/숏 REST 오류({symbol}): {r.status_code} {r.text[:120]}")
            return []
        except Exception as e:
            self.logger.error(f"상위 트레이더 롱/숏 비율 조회 오류({symbol}): {e}")
            return []

    def futures_taker_longshort_ratio(self, symbol: str, period: str = '5m', limit: int = 1) -> List[Dict]:
        """테이커 롱/숏 비율 조회"""
        try:
            # 1) 다양한 메서드명 시도
            for name in (
                'futures_taker_longshort_ratio',
                'futures_taker_long_short_ratio',
                'futures_taker_buy_sell_ratio',
            ):
                fn = getattr(self.client, name, None)
                if callable(fn):
                    try:
                        data = fn(symbol=symbol, period=period, limit=limit)
                        if isinstance(data, dict):
                            return [data]
                        if isinstance(data, list):
                            return data
                        return []
                    except Exception:
                        pass
            # 2) REST 폴백
            import requests as _rq
            url = 'https://fapi.binance.com/futures/data/takerlongshortRatio'
            params = {'symbol': symbol, 'period': period, 'limit': limit}
            r = _rq.get(url, params=params, timeout=10)
            if r.status_code == 200:
                js = r.json()
                if isinstance(js, dict):
                    return [js]
                if isinstance(js, list):
                    return js
                return []
            self.logger.error(f"테이커 롱/숏 REST 오류({symbol}): {r.status_code} {r.text[:120]}")
            return []
        except Exception as e:
            self.logger.error(f"테이커 롱/숏 비율 조회 오류({symbol}): {e}")
            return []

    def get_all_24h_tickers(self) -> List[Dict]:
        """선물 24h 티커 통계 전체 조회(시장 레짐 분석용)"""
        try:
            data = self.client.futures_ticker()
            if isinstance(data, dict):
                return [data]
            return data or []
        except Exception as e:
            self.logger.error(f"24h 티커 전체 조회 오류: {e}")
            return []

    def get_connection_status(self) -> Dict:
        """연결 상태 정보"""
        return {
            'is_connected': self.websocket_manager._connected,
            'testnet': self.config.testnet,
            'websocket_active': self.websocket_manager.ws_thread and self.websocket_manager.ws_thread.is_alive(),
            'last_check': datetime.now()
        }

    def get_symbol_filters(self, symbol: str) -> Optional[Dict[str, Any]]:
        """심볼의 거래소 필터 정보 조회 (minQty, stepSize 등)"""
        try:
            if not hasattr(self, 'client') or not self.client:
                self.logger.warning("Binance client가 초기화되지 않음")
                # 🔥 dict 형식 보장 (키는 채움, 값은 None)
                return {
                    'minQty': None, 'maxQty': None, 'stepSize': None,
                    'minNotional': None, 'minPrice': None, 'maxPrice': None, 'tickSize': None
                }

            # Exchange Info API 호출
            exchange_info = self.client.futures_exchange_info()

            # 해당 심볼 찾기
            for symbol_info in exchange_info['symbols']:
                if symbol_info['symbol'] == symbol:
                    filters = {}

                    # 필터 정보 추출
                    for filter_info in symbol_info['filters']:
                        filter_type = filter_info['filterType']
                        if filter_type == 'LOT_SIZE':
                            filters['minQty'] = float(filter_info['minQty'])
                            filters['maxQty'] = float(filter_info['maxQty'])
                            filters['stepSize'] = float(filter_info['stepSize'])
                        elif filter_type == 'MIN_NOTIONAL':
                            # 🔥 선물: 'notional', 스팟: 'minNotional' 모두 허용
                            mn = filter_info.get('notional', filter_info.get('minNotional'))
                            if mn is not None:
                                filters['minNotional'] = float(mn)
                        elif filter_type == 'PRICE_FILTER':
                            filters['minPrice'] = float(filter_info['minPrice'])
                            filters['maxPrice'] = float(filter_info['maxPrice'])
                            filters['tickSize'] = float(filter_info['tickSize'])

                    # 🔥 Optimizer가 기대하는 평탄화된 키로 변환
                    result = {
                        'minQty': filters.get('minQty'),
                        'stepSize': filters.get('stepSize'),
                        'tickSize': filters.get('tickSize'),
                        'minNotional': filters.get('minNotional'),
                        'quantityPrecision': symbol_info.get('quantityPrecision'),
                        'pricePrecision': symbol_info.get('pricePrecision')
                    }

                    self.logger.info(f"[{symbol}] 거래소 필터 조회 성공: {result}")
                    return result

            self.logger.warning(f"[{symbol}] 심볼을 찾을 수 없음")
            # 🔥 None 반환 (Optimizer가 명확하게 실패로 인식)
            return None

        except Exception as e:
            self.logger.error(f"[{symbol}] 거래소 필터 조회 실패: {e}")
            # 🔥 None 반환 (Optimizer가 명확하게 실패로 인식)
            return None

    def get_symbol_info_direct(self, symbol: str) -> Optional[Dict[str, Any]]:
        """🔥 심볼 정보 직접 조회 (autotrade.py 스타일로 단순화)"""
        try:
            # 🔥 1단계: 캐시 확인 (autotrade.py 스타일)
            if not hasattr(self, '_symbol_info_cache'):
                self._symbol_info_cache = {}

            if symbol in self._symbol_info_cache:
                cached_info = self._symbol_info_cache[symbol]
                # 캐시 유효성 확인 (1시간)
                if time.time() - cached_info.get('cache_time', 0) < 3600:
                    self.logger.info(f"[{symbol}] ✅ 캐시된 심볼 정보 사용")
                    return cached_info['data']
                else:
                    # 만료된 캐시 삭제
                    del self._symbol_info_cache[symbol]

            # 🔥 2단계: client 객체 확인
            self.logger.info(f"[{symbol}] 🔍 get_symbol_info_direct 시작")
            if not hasattr(self, 'client') or not self.client:
                self.logger.warning(f"[{symbol}] ❌ client 객체가 없음")
                return None

            # 🔥 3단계: futures_exchange_info() 호출 (autotrade.py와 동일)
            try:
                exchange_info = self.client.futures_exchange_info()
                self.logger.info(f"[{symbol}] ✅ futures_exchange_info() 성공: {len(exchange_info.get('symbols', []))}개 심볼")
            except Exception as e:
                self.logger.error(f"[{symbol}] ❌ futures_exchange_info() 실패: {e}")
                # 🔥 -1021 타임스탬프 드리프트 감지 시 재시도
                if "1021" in str(e) or "timestamp" in str(e).lower():
                    self.logger.warning(f"[{symbol}] ⚠️ 시계 불일치 감지 - 시간 동기화 후 재시도")
                    try:
                        self._sync_server_time()
                        time.sleep(1)
                        exchange_info = self.client.futures_exchange_info()
                        self.logger.info(f"[{symbol}] ✅ 재시도 성공")
                    except Exception as retry_e:
                        self.logger.error(f"[{symbol}] ❌ 재시도 실패: {retry_e}")
                        return None
                else:
                    return None

            # 🔥 4단계: 심볼 검색 (autotrade.py와 동일)
            symbol_info = None
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    symbol_info = s
                    break

            if not symbol_info:
                self.logger.error(f"[{symbol}] ❌ 심볼 정보 조회 실패 - exchange_info에 {symbol} 없음")
                return None

            self.logger.info(f"[{symbol}] ✅ 심볼 정보 찾음: {symbol_info['symbol']}")

            # 🔥 5단계: 필터 정보 추출 (autotrade.py와 동일)
            processed_info = {
                'minQty': None,
                'stepSize': None,
                'tickSize': None,
                'quantityPrecision': symbol_info.get('quantityPrecision'),
                'pricePrecision': symbol_info.get('pricePrecision'),
                'minNotional': None
            }

            # 필터 정보 추출
            for filter_info in symbol_info['filters']:
                filter_type = filter_info['filterType']
                if filter_type == 'LOT_SIZE':
                    processed_info['minQty'] = float(filter_info['minQty'])
                    processed_info['stepSize'] = float(filter_info['stepSize'])
                elif filter_type == 'MIN_NOTIONAL':
                    # 🔥 선물: 'notional', 스팟: 'minNotional' 모두 허용
                    mn = filter_info.get('notional', filter_info.get('minNotional'))
                    if mn is not None:
                        processed_info['minNotional'] = float(mn)
                elif filter_type == 'PRICE_FILTER':
                    processed_info['tickSize'] = float(filter_info['tickSize'])

            # 🔥 6단계: 캐시에 저장 및 반환 (autotrade.py 스타일)
            self._symbol_info_cache[symbol] = {
                'data': processed_info,
                'cache_time': time.time()
            }

            self.logger.info(f"[{symbol}] ✅ 심볼 정보 조회 성공 및 캐싱 완료")
            return processed_info

        except Exception as e:
            self.logger.error(f"[{symbol}] ❌ 예상치 못한 오류: {e}")
            # 🔥 autotrade.py와 동일하게 None 반환
            return None

    def calculate_precise_quantity(self, symbol: str, target_value: float) -> Optional[float]:
        """정확한 정밀도로 수량 계산: 심볼 필터(stepSize, quantityPrecision)와 현재가 기반"""
        try:
            symbol_info = self.get_symbol_info_direct(symbol)
            if not symbol_info:
                return None

            step_size = float(symbol_info.get('stepSize') or 0)  # 증분
            qty_precision = int(symbol_info.get('quantityPrecision') or 6)
            current_price = float(self.get_current_price(symbol) or 0)
            if current_price <= 0:
                return None

            # 목표 USDT 값으로 수량 계산
            quantity = target_value / current_price

            # step_size에 맞게 보정 (보수적으로 floor)
            if step_size > 0:
                quantity = math.floor(quantity / step_size) * step_size

            # 정밀도 반영
            formatted_quantity = float(format(quantity, f'.{qty_precision}f'))

            self.logger.info(f"[{symbol}] 정밀도 수량 계산: {target_value:.2f} USDT → {formatted_quantity} (stepSize: {step_size}, precision: {qty_precision})")
            return formatted_quantity

        except Exception as e:
            self.logger.error(f"[{symbol}] 정밀도 수량 계산 실패: {e}")
            return None

    def unsubscribe_all_safely(self):
        """
        - 구독 중인 모든 stream을 해제
        - 스레드/타이머가 있다면 join 또는 안전 플래그 set 후 정지
        - 내부 latest_ticker 등 캐시는 남겨도 됨(정지 기준만 명확히)
        """
        try:
            self.logger.info("🔄 WebSocket 안전 종료 시작...")

            if hasattr(self, "websocket_manager") and self.websocket_manager:
                # 모든 구독 해제 (가능한 경우)
                try:
                    fn_unsub = getattr(self.websocket_manager, 'unsubscribe_all', None)
                    if callable(fn_unsub):
                        fn_unsub()
                        self.logger.debug("WebSocket 매니저: unsubscribe_all 호출 완료")
                    else:
                        self.logger.debug("WebSocket 매니저: unsubscribe_all 미지원 → stop()로 대체")
                except Exception as e:
                    self.logger.debug(f"unsubscribe_all 호출 중 예외(무시): {e}")

                # WebSocket 매니저 정지
                if hasattr(self.websocket_manager, 'stop'):
                    self.websocket_manager.stop()

                self.logger.info("✅ WebSocket 매니저 정지 완료")
            else:
                self.logger.warning("⚠️ WebSocket 매니저 없음 - 건너뜀")

            # 구독된 심볼 목록 정리
            self.subscribed_symbols.clear()
            self.logger.info("✅ 구독 심볼 목록 정리 완료")

            self.logger.info("✅ WebSocket 안전 종료 완료")

        except Exception as e:
            self.logger.warning(f"⚠️ WS safe-unsubscribe error: {e}")
