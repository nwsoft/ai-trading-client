#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
바이낸스 API 키 유효성 검증 스크립트
직접 API 키를 입력하여 유효성을 확인합니다.
"""

import sys
import os
import json
import time
from datetime import datetime

# 프로젝트 루트를 Python 경로에 추가
sys.path.append('.')

try:
    from api.binance_client import BinanceClient, BinanceConfig
except ImportError as e:
    print(f"❌ 모듈 import 실패: {e}")
    print("   현재 디렉토리에서 실행해주세요: python3 api_check.py")
    sys.exit(1)


class APIChecker:
    """API 키 유효성 검증 클래스"""
    
    def __init__(self, api_key=None, secret_key=None):
        """초기화"""
        self.api_key = api_key
        self.secret_key = secret_key
        self.results = {
            'api_key_valid': False,
            'spot_access': False,
            'futures_access': False,
            'account_access': False,
            'futures_account_access': False,
            'ip_restricted': False,
            'errors': []
        }
    
    def get_api_keys_from_input(self):
        """사용자로부터 API 키 입력받기"""
        print("\n🔑 바이낸스 API 키를 입력해주세요")
        print("=" * 50)
        
        # API 키 입력
        while True:
            api_key = input("API Key: ").strip()
            if api_key:
                self.api_key = api_key
                break
            print("❌ API Key를 입력해주세요")
        
        # Secret 키 입력
        while True:
            secret_key = input("Secret Key: ").strip()
            if secret_key:
                self.secret_key = secret_key
                break
            print("❌ Secret Key를 입력해주세요")
        
        print("✅ API 키 입력 완료")
        return self.api_key, self.secret_key
    
    def get_api_keys_from_file(self, settings_path=None):
        """설정 파일에서 API 키 읽기 (선택사항)"""
        if not settings_path:
            settings_path = self._find_settings_file()
        
        if not settings_path or not os.path.exists(settings_path):
            return None, None
        
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            
            api_key = settings.get('binance_api_key', '')
            secret_key = settings.get('binance_secret_key', '')
            
            if api_key and secret_key:
                print(f"✅ 설정 파일에서 API 키 로드: {settings_path}")
                return api_key, secret_key
            
        except Exception as e:
            print(f"❌ 설정 파일 로드 실패: {e}")
        
        return None, None
    
    def _find_settings_file(self):
        """설정 파일 경로 찾기"""
        possible_paths = [
            'data/nwsoft/config/settings.json',
            'config/settings.json',
            'settings.json'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def get_api_keys(self):
        """API 키 가져오기 (입력 또는 파일에서)"""
        # 1. 먼저 설정 파일에서 시도
        api_key, secret_key = self.get_api_keys_from_file()
        
        if api_key and secret_key:
            self.api_key = api_key
            self.secret_key = secret_key
            return api_key, secret_key
        
        # 2. 설정 파일이 없으면 사용자 입력 받기
        return self.get_api_keys_from_input()
    
    def check_api_validity(self, api_key, secret_key):
        """API 키 유효성 검증"""
        print(f"\n🔍 바이낸스 API 키 유효성 검증")
        print("=" * 60)
        print(f"API Key: {api_key[:10]}...{api_key[-10:]}")
        print(f"Secret Key: {secret_key[:10]}...{secret_key[-10:]}")
        print("=" * 60)
        
        try:
            # 바이낸스 설정 생성
            config = BinanceConfig(api_key=api_key, secret_key=secret_key, testnet=False)
            
            # 바이낸스 클라이언트 생성
            client = BinanceClient(config)
            
            # 1. 서버 시간 조회 (IP 제한 없음)
            self._check_server_time(client)
            
            # 2. 현물 거래소 정보 조회 (IP 제한 없음)
            self._check_spot_exchange(client)
            
            # 3. 선물 거래소 정보 조회 (IP 제한 있을 수 있음)
            self._check_futures_exchange(client)
            
            # 4. API 키 권한 확인 (IP 제한 있을 수 있음)
            self._check_api_permissions(client)
            
            # 5. 선물 계정 정보 조회 (IP 제한 있을 수 있음)
            self._check_futures_account(client)
            
            return True
            
        except Exception as e:
            print(f"❌ API 키 검증 실패: {e}")
            self.results['errors'].append(str(e))
            return False
    
    def _check_server_time(self, client):
        """서버 시간 조회"""
        try:
            server_time = client.client.get_server_time()
            local_time = int(time.time() * 1000)
            time_diff = abs(server_time['serverTime'] - local_time)
            
            print("✅ 서버 시간 조회 성공: API 키가 유효합니다")
            print(f"   서버 시간: {server_time['serverTime']}")
            print(f"   로컬 시간과 차이: {time_diff}ms")
            
            self.results['api_key_valid'] = True
            
        except Exception as e:
            print(f"❌ 서버 시간 조회 실패: {e}")
            self.results['errors'].append(f"서버 시간 조회 실패: {e}")
    
    def _check_spot_exchange(self, client):
        """현물 거래소 정보 조회"""
        try:
            exchange_info = client.client.get_exchange_info()
            symbol_count = len(exchange_info.get('symbols', []))
            timezone = exchange_info.get('timezone', 'N/A')
            
            print("✅ 현물 거래소 정보 조회 성공")
            print(f"   거래 가능한 심볼 수: {symbol_count}")
            print(f"   서버 타임존: {timezone}")
            
            self.results['spot_access'] = True
            
        except Exception as e:
            print(f"❌ 현물 거래소 정보 조회 실패: {e}")
            self.results['errors'].append(f"현물 거래소 조회 실패: {e}")
    
    def _check_futures_exchange(self, client):
        """선물 거래소 정보 조회"""
        try:
            futures_exchange_info = client.client.futures_exchange_info()
            symbol_count = len(futures_exchange_info.get('symbols', []))
            
            print("✅ 선물 거래소 정보 조회 성공")
            print(f"   선물 심볼 수: {symbol_count}")
            
            self.results['futures_access'] = True
            
        except Exception as e:
            print(f"❌ 선물 거래소 정보 조회 실패: {e}")
            if "IP" in str(e) or "permissions" in str(e):
                print("   → IP 제한으로 인한 실패일 수 있습니다")
                self.results['ip_restricted'] = True
            self.results['errors'].append(f"선물 거래소 조회 실패: {e}")
    
    def _check_api_permissions(self, client):
        """API 키 권한 확인"""
        try:
            account_info = client.client.get_account()
            
            print("✅ API 키 권한 확인 성공")
            print(f"   거래 가능: {account_info.get('canTrade', False)}")
            print(f"   출금 가능: {account_info.get('canWithdraw', False)}")
            print(f"   입금 가능: {account_info.get('canDeposit', False)}")
            print(f"   계정 타입: {account_info.get('accountType', 'N/A')}")
            
            self.results['account_access'] = True
            
        except Exception as e:
            print(f"❌ API 키 권한 확인 실패: {e}")
            if "IP" in str(e) or "permissions" in str(e):
                print("   → IP 제한으로 인한 실패일 수 있습니다")
                self.results['ip_restricted'] = True
            self.results['errors'].append(f"API 권한 확인 실패: {e}")
    
    def _check_futures_account(self, client):
        """선물 계정 정보 조회"""
        try:
            futures_account = client.client.futures_account()
            
            print("✅ 선물 계정 정보 조회 성공")
            print(f"   총 자산: {futures_account.get('totalWalletBalance', 0)} USDT")
            print(f"   사용 가능: {futures_account.get('availableBalance', 0)} USDT")
            print(f"   미실현 손익: {futures_account.get('totalUnrealizedProfit', 0)} USDT")
            
            self.results['futures_account_access'] = True
            
        except Exception as e:
            print(f"❌ 선물 계정 정보 조회 실패: {e}")
            if "IP" in str(e) or "permissions" in str(e):
                print("   → IP 제한으로 인한 실패일 수 있습니다")
                self.results['ip_restricted'] = True
            self.results['errors'].append(f"선물 계정 조회 실패: {e}")
    
    def print_summary(self):
        """결과 요약 출력"""
        print(f"\n📋 최종 결론")
        print("=" * 60)
        
        # API 키 유효성
        if self.results['api_key_valid']:
            print("✅ API 키는 유효합니다 (서버 시간 조회 성공)")
        else:
            print("❌ API 키가 유효하지 않습니다")
        
        # 접근 권한
        if self.results['spot_access']:
            print("✅ 현물 거래소 접근 가능")
        else:
            print("❌ 현물 거래소 접근 불가")
        
        if self.results['futures_access']:
            print("✅ 선물 거래소 접근 가능")
        else:
            print("❌ 선물 거래소 접근 불가")
        
        if self.results['account_access']:
            print("✅ 계정 정보 조회 가능")
        else:
            print("❌ 계정 정보 조회 불가")
        
        if self.results['futures_account_access']:
            print("✅ 선물 계정 정보 조회 가능")
        else:
            print("❌ 선물 계정 정보 조회 불가")
        
        # IP 제한 상태
        if self.results['ip_restricted']:
            print("⚠️  IP 제한으로 인해 일부 기능이 제한될 수 있습니다")
            print("💡 IP 제한을 해제하면 모든 기능이 정상 작동할 것입니다")
        else:
            print("✅ IP 제한 없음")
        
        # 오류 목록
        if self.results['errors']:
            print(f"\n❌ 발생한 오류 ({len(self.results['errors'])}개):")
            for i, error in enumerate(self.results['errors'], 1):
                print(f"   {i}. {error}")
        
        print("=" * 60)
    
    def run(self):
        """전체 검증 실행"""
        print("🚀 바이낸스 API 키 유효성 검증 시작")
        print(f"⏰ 실행 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. API 키 가져오기 (파일에서 먼저 시도, 없으면 입력받기)
        api_key, secret_key = self.get_api_keys()
        if not api_key or not secret_key:
            return False
        
        # 2. API 키 유효성 검증
        if not self.check_api_validity(api_key, secret_key):
            return False
        
        # 3. 결과 요약
        self.print_summary()
        
        return True


def main():
    """메인 함수"""
    print("=" * 60)
    print("🔍 바이낸스 API 키 유효성 검증 도구")
    print("=" * 60)
    
    # 사용자에게 입력 방식 선택
    print("\n📋 API 키 입력 방식을 선택해주세요:")
    print("1. 직접 입력 (수동)")
    print("2. 설정 파일에서 자동 로드")
    print("3. 자동 감지 (설정 파일이 있으면 사용, 없으면 입력)")
    
    while True:
        choice = input("\n선택 (1-3): ").strip()
        if choice in ['1', '2', '3']:
            break
        print("❌ 1, 2, 3 중에서 선택해주세요")
    
    # API 체커 생성
    checker = APIChecker()
    
    # 선택에 따른 처리
    if choice == '1':
        # 직접 입력
        api_key, secret_key = checker.get_api_keys_from_input()
        if not api_key or not secret_key:
            print("❌ API 키 입력이 취소되었습니다")
            sys.exit(1)
    elif choice == '2':
        # 설정 파일에서 로드
        api_key, secret_key = checker.get_api_keys_from_file()
        if not api_key or not secret_key:
            print("❌ 설정 파일에서 API 키를 찾을 수 없습니다")
            print("   직접 입력을 선택해주세요")
            api_key, secret_key = checker.get_api_keys_from_input()
            if not api_key or not secret_key:
                print("❌ API 키 입력이 취소되었습니다")
                sys.exit(1)
    else:
        # 자동 감지 (기본 동작)
        pass
    
    # 검증 실행
    success = checker.run()
    
    if success:
        print("\n✅ 검증 완료")
        sys.exit(0)
    else:
        print("\n❌ 검증 실패")
        sys.exit(1)


if __name__ == "__main__":
    main()
